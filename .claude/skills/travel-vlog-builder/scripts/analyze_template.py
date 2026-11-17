"""analyze_template - MEASURE reference videos instead of guessing: cut rhythm, cold-open length, frame sheets.

usage:  python -I -X utf8 analyze_template.py [--project <folder>] <video> [<video> ...] [--threshold 0.30] [--every 2.0]
                                               [--max-minutes 15]

Per video: finds cuts with ffmpeg's scene detection on a small copy, then prints and saves
  duration, number of cuts, shot length median / mean / 10th-90th percentile, for the opening (first 45 s) and the rest;
  an estimated cold open (an opening stretch cut clearly faster than the body) and a per-30-second pacing table.
Frame sheets for studying structure and graphics (one frame every --every seconds, time as label, 6 columns):
  <work>/templates/<name>_sheet_01.jpg, _02 ...  -> open them with the Read tool and note: opening style, titles,
  caption position and size, labels, stickers, maps, how chapters begin and end.
Numbers: <work>/templates/<name>.json. A final line combines all videos; copy it into PROGRESS.md.
Dissolves and fast camera moves confuse scene detection, so treat the numbers as approximate (the threshold is printed).
"""
import json
import os
import re
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont

import vk


def stats(xs):
    if not xs:
        return None
    s = sorted(xs)
    return dict(n=len(s), median=round(statistics.median(s), 2), mean=round(sum(s) / len(s), 2),
                p10=round(s[int(0.1 * (len(s) - 1))], 2), p90=round(s[int(0.9 * (len(s) - 1))], 2))


def analyze(cfg, path, thr, every, max_min):
    name = re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(os.path.basename(path))[0])[:50]
    out_dir = os.path.join(cfg["work"], "templates")
    os.makedirs(out_dir, exist_ok=True)
    dur = min(vk.probe(path)["dur"], max_min * 60)
    r = subprocess.run(["ffmpeg", "-v", "info", "-t", f"{dur:.2f}", "-i", path, "-an", "-vf",
                        f"scale=320:-2,fps=12.5,select='gt(scene,{thr})',showinfo", "-f", "null", "-"], capture_output=True, text=True)
    cuts = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    cuts = [c for k, c in enumerate(cuts) if k == 0 or c - cuts[k - 1] > 0.25]
    edges = [0.0] + cuts + [dur]
    shots = [(a, b - a) for a, b in zip(edges, edges[1:]) if b - a > 0.05]
    body = [l for t, l in shots if t >= 45]
    opening = [l for t, l in shots if t < 45]
    cold = None
    ref = statistics.median(body) if len(body) >= 5 else (statistics.median([l for _, l in shots[len(shots) // 2:]]) if len(shots) >= 8 else None)
    if ref:      # cold open = the opening run whose rolling median (4 shots) stays clearly below the body's pace
        for k in range(len(shots) - 3):
            if statistics.median([l for _, l in shots[k:k + 4]]) > 0.7 * ref:
                if k >= 3 and shots[k][0] <= 90:
                    cold = round(shots[k][0], 1)
                break
    windows = []
    for w0 in range(0, int(dur), 30):
        ls = [l for t, l in shots if w0 <= t < w0 + 30]
        windows.append(dict(t=w0, shots=len(ls), median=round(statistics.median(ls), 2) if ls else None))
    # frame sheets
    tmp = os.path.join(out_dir, name + "_frames")
    os.makedirs(tmp, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", f"{dur:.2f}", "-i", path, "-an", "-vf", f"fps=1/{every},scale=320:-2",
                    "-q:v", "4", os.path.join(tmp, "f_%05d.jpg")], capture_output=True)
    files = sorted(f for f in os.listdir(tmp) if f.endswith(".jpg"))
    font = ImageFont.truetype(vk.font_path("SANS_B"), 15)
    sheets = []
    for k in range(0, len(files), 60):
        ims = [Image.open(os.path.join(tmp, f)) for f in files[k:k + 60]]
        cw, chh = 320, max(i.height for i in ims) + 20
        sh = Image.new("RGB", (6 * cw, ((len(ims) + 5) // 6) * chh), "black")
        d = ImageDraw.Draw(sh)
        for j, im in enumerate(ims):
            x, y = (j % 6) * cw, (j // 6) * chh
            sh.paste(im, (x, y))
            t = (k + j) * every + every / 2
            d.text((x + 4, y + chh - 19), f"{int(t // 60)}:{t % 60:04.1f}", fill="white", font=font)
        p = os.path.join(out_dir, f"{name}_sheet_{k // 60 + 1:02d}.jpg")
        sh.save(p, quality=85)
        sheets.append(p)
    for f in files:
        os.remove(os.path.join(tmp, f))
    os.rmdir(tmp)
    res = dict(file=path, duration=round(dur, 1), threshold=thr, cuts=len(cuts), all=stats([l for _, l in shots]), opening=stats(opening),
               body=stats(body), cold_open_end=cold, windows=windows, sheets=sheets)
    with open(os.path.join(out_dir, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(f"{name}: {dur:.0f}s  cuts {len(cuts)}  shot median {res['all']['median']}s mean {res['all']['mean']}s  "
          f"opening(45s) median {res['opening']['median'] if res['opening'] else '-'}s  body median {res['body']['median'] if res['body'] else '-'}s  "
          f"cold open ends {cold if cold else 'not found'}  sheets {len(sheets)}  (approximate, threshold {thr})")
    return res


def main():
    cfg = vk.load()
    a = sys.argv[1:]
    opt = {}
    for k in ("--threshold", "--every", "--max-minutes"):
        if k in a:
            i = a.index(k)
            opt[k] = float(a[i + 1])
            del a[i:i + 2]
    if not a:
        sys.exit(__doc__)
    res = [analyze(cfg, p, opt.get("--threshold", 0.30), opt.get("--every", 2.0), opt.get("--max-minutes", 15)) for p in a]
    bodies = [r["body"]["median"] for r in res if r["body"]]
    colds = [r["cold_open_end"] for r in res if r["cold_open_end"]]
    print(f"templates: videos={len(res)} body shot median={round(statistics.median(bodies), 2) if bodies else '-'}s "
          f"cold open={round(statistics.median(colds), 1) if colds else '-'}s  sheets in {os.path.join(cfg['work'], 'templates')}")


if __name__ == "__main__":
    main()
