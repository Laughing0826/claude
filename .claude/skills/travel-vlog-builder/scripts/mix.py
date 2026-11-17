"""mix - mix several music tracks into ONE music bed WAV: crossfades between tracks, dips ("ducking") under speech.

usage:  python -I -X utf8 mix.py [--project <folder>] [<music_plan.json>]        default: <base>/music_plan.json

music_plan.json (paths relative to the project folder):
  {"out": "Music/Trip_v3_music_bed.wav", "lufs": -19, "master": 0.8, "tail_fade": 2.0, "ramp": 0.45,
   "tracks": [
     {"file": "Music/v3/1_Opener.wav", "start": 15.25, "fade_in": 0.25, "fade_out": 2.5, "stop": {"card": "DAY 1", "offset": 1.6}},
     {"file": "Music/v3/2_Safari.wav", "start": {"card": "DAY 1", "offset": -0.4}, "fade_in": 1.0, "fade_out": 2.5},
     {"file": "Music/v3/3_Plains.wav", "start": {"after_prev": -2.6}, "fade_in": 2.5, "fade_out": 2.0, "expect": 137},
     {"file": "Music/v3/4_Home.wav",   "start": "end", "fade_in": 1.0, "fade_out": 0.3}],
   "duck": [{"ref": "V1", "db": -12}, {"shot": 74, "db": -6}, {"t0": 484.5, "t1": 488.1, "db": -6}]}

A time is: seconds; {"card": "<start of a shot's card text>", "offset": s}; {"shot": n, "offset": s};
{"ref": "<catalog id>", "offset": s} (first shot with that ref). For "start" also {"after_prev": s} (relative to the
END of the previous track; negative = overlap) and "end" (the track's end lands on the video's last frame).
"stop" cuts a track early. Ducks cover a whole shot ({"ref"} = first shot with that ref, or every one with "all": true;
{"shot": n}) or explicit t0/t1 seconds; music is lowered by `db` with ramps of `ramp` seconds on both sides.
Every track is loudness-normalised to `lufs`; the sum is multiplied by `master`; the last `tail_fade` seconds fade out.

Timings come from edit_list_<version>.json. Output: the WAV (16-bit stereo 48 kHz, video length + 0.5 s), <out>.json
with the resolved placements, a printed table, and WARNINGS (truncated file vs "expect", silent gaps > 1 s, a track
starting after the end, clipping). Nothing here was ever listened to: report the music as unheard.
"""
import json
import os
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import vk

SR = 48000


def main():
    cfg = vk.load()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    plan_path = args[0] if args else cfg.p("music_plan.json")
    if not os.path.exists(plan_path) or not os.path.exists(cfg["edit_list"]):
        sys.exit(f"need {plan_path} and {cfg['edit_list']}")
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    with open(cfg["edit_list"], encoding="utf-8") as f:
        E = json.load(f)
    FPS = cfg["FPS"]
    end = (E[-1]["start"] + E[-1]["frames"]) / FPS

    def shot_of(a):
        if "card" in a:
            m = [s for s in E if s.get("card") and s["card"][0].startswith(a["card"])]
        elif "shot" in a:
            m = [s for s in E if s["n"] == a["shot"]]
        else:
            m = [s for s in E if s["ref"] == a["ref"]]
        if not m:
            sys.exit(f"music plan: nothing in the edit list matches {a}")
        return m

    def when(a):
        if isinstance(a, (int, float)):
            return float(a)
        return shot_of(a)[0]["start"] / FPS + float(a.get("offset", 0))

    def load(path):
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-af", f"loudnorm=I={plan.get('lufs', -19)}:TP=-2:LRA=12",
                            "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True)
        if r.returncode or not r.stdout:
            sys.exit(f"cannot decode {path}: {r.stderr.decode(errors='replace')[-200:]}")
        return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()

    n = int(end * SR) + SR // 2
    bed = np.zeros((n, 2), np.float32)
    cover = np.zeros(n, bool)
    warns, rows, prev_end = [], [], 0.0
    for t in plan["tracks"]:
        path = t["file"] if os.path.isabs(t["file"]) else cfg.p(t["file"])
        if not os.path.exists(path):
            sys.exit(f"music file missing: {path}")
        a = load(path)
        real = len(a) / SR
        if t.get("expect") and abs(real - t["expect"]) > 1.0:
            warns.append(f"{os.path.basename(path)} is {real:.1f}s but {t['expect']}s was expected (truncated download?)")
        st = t.get("start", 0)
        if st == "end":
            t0 = end - real
        elif isinstance(st, dict) and "after_prev" in st:
            t0 = prev_end + st["after_prev"]
        else:
            t0 = when(st)
        if "stop" in t:
            a = a[:max(0, int((when(t["stop"]) - t0) * SR))]
        if t0 >= end or len(a) == 0:
            warns.append(f"{os.path.basename(path)} starts at {t0:.1f}s, after the video ends ({end:.1f}s), or is cut to nothing")
            continue
        if t0 < 0:
            a, t0 = a[int(-t0 * SR):], 0.0
        k = len(a)
        env = np.ones(k, np.float32)
        fi, fo = min(int(t.get("fade_in", 1.0) * SR), k), min(int(t.get("fade_out", 2.0) * SR), k)
        if fi:
            env[:fi] = np.linspace(0, 1, fi)
        if fo:
            env[-fo:] *= np.linspace(1, 0, fo)
        i0 = int(t0 * SR)
        k = min(k, n - i0)
        bed[i0:i0 + k] += a[:k] * env[:k, None]
        cover[i0:i0 + k] = True
        prev_end = t0 + k / SR
        rows.append(dict(file=os.path.basename(path), start=round(t0, 2), end=round(prev_end, 2), length=round(real, 2)))
    gain = np.ones(n, np.float32)
    ramp = float(plan.get("ramp", 0.45))
    ducks = []
    for d in plan.get("duck", []):
        spans = ([(d["t0"], d["t1"])] if "t0" in d else
                 [(s["start"] / FPS, (s["start"] + s["frames"]) / FPS) for s in (shot_of(d) if d.get("all") else shot_of(d)[:1])])
        for t0, t1 in spans:
            g = 10 ** (d["db"] / 20.0)
            i0, i1, r = max(0, int((t0 - ramp) * SR)), min(n, int((t1 + ramp) * SR)), int(ramp * SR)
            seg = np.full(i1 - i0, g, np.float32)
            r = min(r, len(seg) // 2)
            if r:
                seg[:r] = np.linspace(1, g, r)
                seg[-r:] = np.linspace(g, 1, r)
            gain[i0:i1] = np.minimum(gain[i0:i1], seg)
            ducks.append(dict(t0=round(t0, 2), t1=round(t1, 2), db=d["db"]))
    bed *= gain[:, None]
    tf = int(float(plan.get("tail_fade", 2.0)) * SR)
    if tf:
        bed[-tf:] *= np.linspace(1, 0, tf)[:, None]
    bed *= float(plan.get("master", 0.8))
    peak = float(np.abs(bed).max())
    if peak > 1.0:
        warns.append(f"peak {peak:.2f} exceeds full scale before limiting; lower \"master\" or shorten the overlaps")
    bed = np.clip(bed, -1, 1)
    # gaps: stretches inside the video with no music at all
    edges = np.flatnonzero(np.diff(np.concatenate([[True], cover[:int(end * SR)], [True]]).astype(np.int8)))
    for a0, a1 in zip(edges[::2], edges[1::2]):
        if (a1 - a0) / SR > 1.0:
            warns.append(f"no music from {a0 / SR:.1f}s to {a1 / SR:.1f}s")
    out = plan.get("out") or os.path.join("Music", f"{cfg['name'].replace(' ', '_')}_{cfg['version']}_music_bed.wav")
    out = out if os.path.isabs(out) else cfg.p(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((bed * 32767).astype(np.int16).tobytes())
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump(dict(video_end=end, tracks=rows, ducks=ducks, warnings=warns), f, indent=1, ensure_ascii=False)
    for r in rows:
        print(f"track {r['start']:8.2f} -> {r['end']:8.2f}  ({r['length']:.1f}s file)  {r['file']}")
    for d in ducks:
        print(f"duck  {d['t0']:8.2f} -> {d['t1']:8.2f}  {d['db']} dB")
    for w_ in warns:
        print("WARNING " + w_)
    print(f"mix: out={out} length={n / SR:.2f}s video={end:.2f}s tracks={len(rows)} ducks={len(ducks)} warnings={len(warns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
