"""score_photos - shortlist photos from thousands: sharpness and exposure scores, best frame per burst, sheets to look at.

usage:  python -I -X utf8 score_photos.py [--project <folder>] scan <folder> [<folder> ...] [--workers 8]
        python -I -X utf8 score_photos.py [--project <folder>] pick [--per-day 48] [--burst-gap 2.0] [--cols 8]

scan  every photo under the folders (RAW files through their embedded preview, so it is fast):
      -> <work>/scores.csv  (path,when,sharp,mean,clip,thumb,w,h)  and thumbnails in <work>/thumbs/. Resumable.
      sharp = variance of the Laplacian, weighted to the centre of the frame; mean = brightness 0-255;
      clip = share of pixels nearly black or nearly white; when = true capture time in the trip zone.
pick  bursts = consecutive frames less than --burst-gap seconds apart; the sharpest well-exposed frame of each burst
      is kept; per trip day the top --per-day are listed in time order with ids D<day>-<nn>
      -> <work>/cand.csv (id,day,path,thumb,score,burst) and one labelled sheet per day <work>/cand_D<day>.jpg
      Day 1 is project.json "day1" (YYYY-MM-DD), else the earliest capture date.
The script only prepares the sheets. YOU then open every cand_D*.jpg and choose by eye (subject, moment, variety),
write the chosen "path::id" lines to a list file and render them with style.py. The original went
30,528 frames -> 2,293 bursts -> 48 per day reviewed -> 52 chosen.
"""
import csv
import datetime
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import vk
import capture_time
import sheet
import style

EXT = (".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".arw", ".dng", ".nef", ".cr2", ".cr3", ".raf")
COLS = ["path", "when", "sharp", "mean", "clip", "thumb", "w", "h"]


def score(arg):
    path, thumbs = arg
    try:
        im = style.open_image(path, fast=True)
        w, h = im.size
        im.thumbnail((1024, 1024))
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.splitext(path)[0])[-120:] + ".jpg"
        im.save(os.path.join(thumbs, name), quality=82)
        g = np.asarray(im.convert("L")).astype(np.float32)
        lap = g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
        hh, ww = lap.shape
        cen = lap[int(hh * 0.2):int(hh * 0.8), int(ww * 0.2):int(ww * 0.8)]
        sharp = 0.3 * float(lap.var()) + 0.7 * float(cen.var())
        when = capture_time.capture_local(path)[0]
        return [path, when, round(sharp, 1), round(float(g.mean()), 1), round(float(((g < 5) | (g > 250)).mean()), 3), name, w, h]
    except Exception as e:
        print("skip", path, repr(e)[:80])
        return None


def scan(cfg, a):
    folders = [x for x in a if not x.startswith("--")]
    workers = int(a[a.index("--workers") + 1]) if "--workers" in a else 8
    if "--workers" in a:
        folders.remove(str(workers))
    out = os.path.join(cfg["work"], "scores.csv")
    thumbs = os.path.join(cfg["work"], "thumbs")
    os.makedirs(thumbs, exist_ok=True)
    done = set()
    if os.path.exists(out):
        with open(out, encoding="utf-8", newline="") as f:
            done = {r["path"] for r in csv.DictReader(f)}
    todo = [os.path.join(r, f) for d in folders for r, _, fs in os.walk(d) for f in sorted(fs) if f.lower().endswith(EXT)]
    todo = [p for p in todo if p not in done]
    new = not os.path.exists(out)
    n = 0
    with open(out, "a", encoding="utf-8", newline="") as f, ThreadPoolExecutor(workers) as ex:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        for r in ex.map(score, [(p, thumbs) for p in todo]):
            if r:
                w.writerow(r)
                n += 1
    print(f"score_photos scan: new={n} already={len(done)} csv={out}")


def pick(cfg, a):
    def opt(k, d):
        return float(a[a.index(k) + 1]) if k in a else d
    per, gap, cols = int(opt("--per-day", 48)), opt("--burst-gap", 2.0), int(opt("--cols", 8))
    src = os.path.join(cfg["work"], "scores.csv")
    if not os.path.exists(src):
        sys.exit("run `score_photos.py scan <folder>` first")
    with open(src, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["when"]]
    rows.sort(key=lambda r: r["when"])
    T = lambda r: datetime.datetime.strptime(r["when"], "%Y-%m-%d %H:%M:%S")
    bursts, cur = [], []
    for r in rows:
        if cur and (T(r) - T(cur[-1])).total_seconds() >= gap:
            bursts.append(cur)
            cur = []
        cur.append(r)
    if cur:
        bursts.append(cur)
    best = []
    for b in bursts:
        ok = [r for r in b if 35 <= float(r["mean"]) <= 215 and float(r["clip"]) < 0.25] or b
        r = max(ok, key=lambda r: float(r["sharp"]))
        best.append(dict(r, score=float(r["sharp"]), burst=len(b)))
    d1 = datetime.date.fromisoformat(cfg.get("day1") or best[0]["when"][:10]) if best else None
    days = {}
    for r in best:
        days.setdefault((datetime.date.fromisoformat(r["when"][:10]) - d1).days + 1, []).append(r)
    out = []
    thumbs = os.path.join(cfg["work"], "thumbs")
    for day in sorted(days):
        top = sorted(sorted(days[day], key=lambda r: -r["score"])[:per], key=lambda r: r["when"])
        items = []
        for k, r in enumerate(top):
            cid = f"D{day}-{k:02d}"
            out.append([cid, day, r["path"], r["thumb"], round(r["score"]), r["burst"]])
            items.append((os.path.join(thumbs, r["thumb"]), f"{cid} {r['when'][11:16]}"))
        sheet.make_sheet(items, os.path.join(cfg["work"], f"cand_D{day}.jpg"), cols=cols, cell_w=240)
        print(f"day {day}: bursts {len(days[day])} candidates {len(top)} -> cand_D{day}.jpg")
    with open(os.path.join(cfg["work"], "cand.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "day", "path", "thumb", "score", "burst"])
        w.writerows(out)
    print(f"score_photos pick: frames={len(rows)} bursts={len(bursts)} candidates={len(out)} csv={os.path.join(cfg['work'], 'cand.csv')}")


if __name__ == "__main__":
    cfg = vk.load()
    a = sys.argv[1:]
    if not a or a[0] not in ("scan", "pick"):
        sys.exit(__doc__)
    (scan if a[0] == "scan" else pick)(cfg, a[1:])
