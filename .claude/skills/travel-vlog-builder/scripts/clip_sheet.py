"""clip_sheet - contact sheets of video clips and photos from catalog.csv, so footage can be judged by eye.

A model cannot watch video. Before a clip goes into the edit list, look at frames from it: what is in it, where the
action is, whether it is sharp and steady, and which second to start from (the in-point `i`).

usage:  python -I -X utf8 clip_sheet.py [--project <folder>] videos [--kind S,V] [--every 2.0] [--ids C0016,V79] [--day 2026-02-19]
        python -I -X utf8 clip_sheet.py [--project <folder>] photos [--kind P,A] [--day 2026-02-19] [--per-sheet 48]

videos: one sheet per clip listed (all clips of the kinds when --ids is not given): a frame every --every seconds,
        each labelled "<id> @<seconds>s", 6 columns -> <work>/clips/<id>.jpg ; very long clips are sampled at most 48 times.
        Also prints "<id> <capture time> <duration>s <width>x<height> <fps>" per clip.
photos: thumbnails in capture-time order, labelled "<id> <HH:MM>", 8 columns, --per-sheet per sheet
        -> <work>/photos/<kind>_<date>_<nn>.jpg (one series per day), so a whole day can be scanned in a few images.

Then open the sheets with the Read tool. Note what each usable clip shows and its good in-points in PROGRESS.md
(for example "C0016: two giraffes browsing; wide 4-9 s, tongue close-up from 22 s") before writing the edit list.
"""
import csv
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk
import sheet


def _opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def _catalog(cfg):
    if not os.path.exists(cfg["catalog"]):
        sys.exit(f"{cfg['catalog']} not found. Run inventory.py first.")
    with open(cfg["catalog"], encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["path"] = r["path"] if os.path.isabs(r["path"]) else cfg.p(r["path"])
    return rows


def videos(cfg, args):
    kinds = _opt(args, "--kind", "S,V").split(",")
    every = float(_opt(args, "--every", "2.0"))
    ids = set(_opt(args, "--ids", "").split(",")) - {""}
    day = _opt(args, "--day")
    out_dir = os.path.join(cfg["work"], "clips")
    os.makedirs(out_dir, exist_ok=True)
    rows = [r for r in _catalog(cfg) if (r["id"] in ids if ids else r["kind"] in kinds) and (not day or r["when"].startswith(day))]
    rows.sort(key=lambda r: r["when"])
    made = 0
    for r in rows:
        dur = float(r.get("dur") or 0) or vk.probe(r["path"])["dur"]
        print(f"{r['id']} {r['when']} {dur:.1f}s {r.get('w')}x{r.get('h')} {r.get('fps')}fps")
        out = os.path.join(out_dir, vk_safe(r["id"]) + ".jpg")
        if os.path.exists(out) and "--force" not in args:
            continue
        step = max(every, dur / 48.0)
        times = [round(k * step, 2) for k in range(int(dur / step) + 1) if k * step < dur - 0.05] or [0.0]
        with tempfile.TemporaryDirectory() as td:
            def grab(t):
                p = os.path.join(td, f"{t:08.2f}.jpg")
                try:
                    sheet.frame_at(r["path"], t, p, width=480)
                except Exception:
                    return None
                return (p, f"{r['id']} @{t:g}s") if os.path.exists(p) else None
            with ThreadPoolExecutor(4) as ex:
                items = [x for x in ex.map(grab, times) if x]
            if items:
                sheet.make_sheet(items, out, cols=6, cell_w=320)
                made += 1
    print(f"clips {len(rows)}  sheets written {made}  -> {out_dir}")


def photos(cfg, args):
    kinds = _opt(args, "--kind", "P,A").split(",")
    day = _opt(args, "--day")
    per = int(_opt(args, "--per-sheet", "48"))
    out_dir = os.path.join(cfg["work"], "photos")
    th_dir = os.path.join(out_dir, "thumbs")
    os.makedirs(th_dir, exist_ok=True)
    import style
    rows = [r for r in _catalog(cfg) if r["kind"] in kinds and (not day or r["when"].startswith(day))]
    rows.sort(key=lambda r: (r["kind"], r["when"]))

    def thumb(r):
        p = os.path.join(th_dir, vk_safe(r["id"]) + ".jpg")
        if not os.path.exists(p):
            try:
                im = style.open_image(r["path"])
                im.thumbnail((480, 480))
                im.save(p, quality=80)
            except Exception as e:
                print("skip", r["id"], repr(e)[:80])
                return None
        return (p, f"{r['id']} {r['when'][11:16]}")
    groups = {}
    for r in rows:
        groups.setdefault((r["kind"], r["when"][:10] or "undated"), []).append(r)
    n = 0
    for (kind, date), rs in sorted(groups.items()):
        with ThreadPoolExecutor(6) as ex:
            items = [x for x in ex.map(thumb, rs) if x]
        for k in range(0, len(items), per):
            out = os.path.join(out_dir, f"{kind}_{date}_{k // per + 1:02d}.jpg")
            sheet.make_sheet(items[k:k + per], out, cols=8, cell_w=240)
            n += 1
        print(f"{kind} {date}: {len(items)} photos")
    print(f"photos {len(rows)}  sheets written {n}  -> {out_dir}")


def vk_safe(s):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)


if __name__ == "__main__":
    cfg = vk.load()
    a = sys.argv[1:]
    if not a or a[0] not in ("videos", "photos"):
        sys.exit(__doc__)
    (videos if a[0] == "videos" else photos)(cfg, a)
