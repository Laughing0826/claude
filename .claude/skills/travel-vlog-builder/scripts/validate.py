"""validate - prove that every rendered file is usable BEFORE building the timeline.

usage:  python -I -X utf8 validate.py [--project <folder>] [--test] [--deep]

Reads <version>/build_<version>.json (or build_<version>.test.json with --test, where only the test-rendered shots
are checked) and checks:
  shots     every pre-rendered shot (all kinds except S): file exists, is larger than 20 kB, has exactly
            head + frames + tail video frames (1 frame of tolerance) and has an audio stream;
            kind S (used straight from the source): the source file exists
  overlays  file exists and is larger than 5 kB; with --deep also: has an alpha channel and at least `dur` frames
  subs      every caption has positive length and does not overlap the next one
Prints one line per problem (MISSING, SMALL, FRAMES, NOAUDIO, SRC MISSING, OV MISSING, OV SMALL, OV ALPHA, OV SHORT,
SUB), then one summary line:
  bad N  shots X rendered Y direct Z  overlays by track {...}  subs S  size G.GG GB
Exit code 1 when bad > 0. Do not build the timeline until this prints `bad 0`.
"""
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk


def check_shot(s):
    out = []
    tag = f"{s['n']} {s['ref']}"
    if s["kind"] == "S":
        if not os.path.exists(s.get("file", "")):
            out.append(f"SRC MISSING {tag} {s.get('file')}")
        return out
    m = s.get("media")
    if not m or not os.path.exists(m):
        return [f"MISSING {tag} {s.get('err') or ''}".rstrip()]
    if os.path.getsize(m) < 20000:
        return [f"SMALL {tag} {os.path.getsize(m)} bytes"]
    n, exp = vk.count_frames(m), s["head"] + s["frames"] + s["tail"]
    if abs(n - exp) > 1:
        out.append(f"FRAMES {tag} has {n} expected {exp}")
    if not vk.probe(m)["audio"]:
        out.append(f"NOAUDIO {tag}")
    return out


def check_overlay(arg):
    o, deep = arg
    f = o["file"]
    if not os.path.exists(f):
        return [f"OV MISSING {f}"]
    if os.path.getsize(f) < 5000:
        return [f"OV SMALL {f}"]
    out = []
    if deep:
        r = vk.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", f], check=False)
        if not r.stdout.strip().startswith("yuva"):
            out.append(f"OV ALPHA {f} pix_fmt {r.stdout.strip()}")
        n = vk.count_frames(f)
        if n < o["dur"]:
            out.append(f"OV SHORT {f} has {n} needs {o['dur']}")
    return out


def main():
    cfg = vk.load()
    args = sys.argv[1:]
    path = cfg["build"].replace(".json", ".test.json") if "--test" in args else cfg["build"]
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Run prep.py first.")
    with open(path, encoding="utf-8") as f:
        B = json.load(f)
    meta = B.get("meta", {})
    shots = [s for s in B["shots"] if not meta.get("partial") or s["n"] in meta.get("rendered", [])]
    problems = []
    with ThreadPoolExecutor(8) as ex:
        for r in ex.map(check_shot, shots):
            problems += r
        for r in ex.map(check_overlay, [(o, "--deep" in args) for o in B["overlays"]]):
            problems += r
    subs = sorted(B.get("subs", []))
    for a, b in zip(subs, subs[1:] + [None]):
        if a[1] <= a[0]:
            problems.append(f"SUB empty caption at frame {a[0]}: {a[2][:40]}")
        if b and a[1] > b[0]:
            problems.append(f"SUB overlap at frame {b[0]}: {a[2][:30]} / {b[2][:30]}")
    for p in problems:
        print(p)
    files = {s["media"] for s in shots if s.get("media") and os.path.exists(s["media"])} | {o["file"] for o in B["overlays"] if os.path.exists(o["file"])}
    size = sum(os.path.getsize(f) for f in files) / 1e9
    tracks = dict(sorted(Counter(o["track"] for o in B["overlays"]).items()))
    print(f"bad {len(problems)}  shots {len(shots)} rendered {sum(1 for s in shots if s.get('media'))} direct {sum(1 for s in shots if s['kind'] == 'S')}  "
          f"overlays by track {tracks}  subs {len(subs)}  size {size:.2f} GB" + ("  (partial test build)" if meta.get("partial") else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
