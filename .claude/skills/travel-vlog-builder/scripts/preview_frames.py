"""preview_frames - see the video as the viewer will, without Resolve: shot + every overlay active at that moment.

A model cannot watch video. This composites single frames from the rendered files, tiles them into one contact
sheet and prints its path; open the sheet with the Read tool and judge every element by eye.

usage:  python -I -X utf8 preview_frames.py [--project <folder>] [auto | n1,n2,...] [--test] [--at 0.5] [--cols 3]
                                             [--cell 690] [--out <sheet.jpg>]
  auto        a representative set (default): the first shot of each kind, the first shot with each graphic type
              (title, card, loc, sp, lower, stk, badge, each mg, a caption) and the last shot; at most 18 shots
  n1,n2,...   these shot numbers
  --test      read build_<version>.test.json (after `prep.py test ...`); only rendered shots are shown
  --at        where in the shot, as a fraction 0..1, or several ("0.15,0.5,0.85" -> frames labelled a, b, c).
              Default: a moment when the shot's overlays have finished animating in.
Outputs: <work>/preview/<nnn>_<ref>[a|b|c].jpg and the sheet <work>/preview_sheet.jpg (or --out).
Kind S shots are read from the source clip (with the project LUT if one is set); everything else from the render.
Captions and graphics look exactly as in the final video; transitions and Resolve's stabiliser are not shown.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk
import sheet


def auto_pick(B, only):
    picks, seen = [], set()

    def take(s, tag):
        if tag in seen or len(picks) >= 18 or (only is not None and s["n"] not in only):
            return
        seen.add(tag)
        if s["n"] not in picks:
            picks.append(s["n"])
    for s in B["shots"]:
        take(s, "kind:" + s["kind"])
        for k in ("title", "card", "loc", "sp", "lower", "stk", "badge"):
            if s.get(k):
                take(s, k)
        if s.get("sub") or s.get("subs"):
            take(s, "caption")
        if s.get("mg"):
            take(s, "mg:" + s["mg"])
        if s["kind"] == "C":
            take(s, "collage%d" % len(s.get("files", [])))
    if B["shots"]:
        take(B["shots"][-1], "last")
    return sorted(picks)


def one_frame(cfg, B, s, frac, dst):
    FPS, W, H = cfg["FPS"], cfg["W"], cfg["H"]
    ovs = [o for o in B["overlays"] if o["start"] < s["start"] + s["frames"] and o["start"] + o["dur"] > s["start"]]
    if frac is None:    # a frame where this shot's own overlays are fully in
        own = [o for o in ovs if o.get("shot") == s["n"]] or ovs
        off = max([min(o["start"] - s["start"] + min(45, o["dur"] // 2), s["frames"] - 8) for o in own] + [min(s["frames"] // 2, 60)])
    else:
        off = int(round(frac * (s["frames"] - 1)))
    off = max(0, min(off, s["frames"] - 1))
    F = s["start"] + off
    cwd = None
    if s["kind"] == "S":
        lut = ""
        if cfg.get("lut"):
            cwd = vk.lut_local()
            lut = ",lut3d=look.cube"
        cmd = ["-ss", f"{s['i'] + off / FPS:.3f}", "-i", s["file"]]
        f = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}{lut}[b0]"
    else:
        if not s.get("media") or not os.path.exists(s["media"]):
            return None
        cmd = ["-ss", f"{(s['head'] + off) / FPS:.3f}", "-i", s["media"]]
        f = "[0:v]null[b0]"
    i = 1
    missing = []
    for o in sorted(ovs, key=lambda o: (o["track"], o["start"])):
        if not (o["start"] <= F < o["start"] + o["dur"]):
            continue
        if not os.path.exists(o["file"]):
            missing.append(os.path.basename(o["file"]))
            continue
        cmd += ["-ss", f"{(F - o['start']) / FPS:.3f}", "-i", o["file"]]
        f += f";[b{i - 1}][{i}:v]overlay[b{i}]"
        i += 1
    r = vk.run(["ffmpeg", "-v", "error", "-y"] + cmd + ["-filter_complex", f, "-map", f"[b{i - 1}]", "-frames:v", "1", "-q:v", "3", dst], cwd=cwd, check=False)
    if missing:
        print(f"shot {s['n']}: overlay files missing: {missing}")
    if r.returncode or not os.path.exists(dst):
        print(f"shot {s['n']} {s['ref']}: frame failed: {r.stderr[-200:]}")
        return None
    return dst


def main():
    cfg = vk.load()
    args = sys.argv[1:]

    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default
    path = cfg["build"].replace(".json", ".test.json") if "--test" in args else cfg["build"]
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Run prep.py first.")
    with open(path, encoding="utf-8") as f:
        B = json.load(f)
    meta = B.get("meta", {})
    only = set(meta.get("rendered", [])) | {s["n"] for s in B["shots"] if s["kind"] == "S"} if meta.get("partial") else None
    sel = args[0] if args and not args[0].startswith("--") else "auto"
    if sel != "auto" and not sel.replace(",", "").isdigit():
        sys.exit(__doc__)
    nums = auto_pick(B, only) if sel == "auto" else [int(x) for x in sel.split(",")]
    fracs = [float(x) for x in opt("--at").split(",")] if opt("--at") else [None]
    by_n = {s["n"]: s for s in B["shots"]}
    out_dir = os.path.join(cfg["work"], "preview")
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for n in nums:
        s = by_n.get(n)
        if s is None:
            print(f"shot {n}: not in the build")
            continue
        for k, fr in enumerate(fracs):
            suffix = "abcdefgh"[k] if len(fracs) > 1 else ""
            name = f"{n:03d}_{''.join(c if c.isalnum() or c in '-_' else '_' for c in s['ref'])}{suffix}"
            p = one_frame(cfg, B, s, fr, os.path.join(out_dir, name + ".jpg"))
            if p:
                items.append((p, name))
    if not items:
        print("no frame could be produced")
        return 1
    out = opt("--out", os.path.join(cfg["work"], "preview_sheet.jpg"))
    info = sheet.make_sheet(items, out, cols=int(opt("--cols", "3")), cell_w=int(opt("--cell", "690")))
    print(f"preview: frames={len(items)} sheet={info['out'] if isinstance(info, dict) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
