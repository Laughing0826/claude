"""cut_sheet - cut an illustration "sticker sheet" (many drawings on white, in a grid) into transparent sprites.

usage:  python -I -X utf8 cut_sheet.py [--project <folder>] <sheet image> <rows> <cols> <name1,name2,...>
                                        [--out <dir>] [--white 236] [--contact <jpg>] [--allow-missing]
  names are given in reading order (left to right, top to bottom). Sprites go to <project>/Graphics/mg/cut/<name>.png
  (or --out); a contact sheet on green goes to <work>/cut_sheet.jpg. Prints "name w h" per sprite.

How it works (numpy and Pillow only):
  1. background = near-white pixels (min of R,G,B > --white) CONNECTED TO THE IMAGE BORDER. White inside a drawing
     (zebra stripes, a white aircraft, eye highlights) is enclosed, so it stays opaque.
  2. foreground runs are joined into connected pieces; every piece larger than 150 px is given to the grid cell
     holding its centre, and all pieces of a cell form one sprite (a detached tail tuft or twig stays with its animal).
  3. the alpha edge is feathered slightly and the sprite is cropped to its bounding box.
ALWAYS open the contact sheet afterwards: every sprite whole, no neighbour fragments, no holes in white areas.
If drawings touch or a part is missing, try another --white (220-245) or regenerate the sheet with wider margins.

Also importable: cut_sheet(path, names, rows, cols, out_dir, white=236), contact(names, out_dir, out_jpg),
recolor_hue(png, [(h0, h1), ...], hue_to, value_scale=1.0, min_sat=0.35)  (hues in degrees 0-360).
"""
import colorsys
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import vk


def _border_connected(mask):
    """Pixels of `mask` connected to the image border (iterative flood by row/column sweeps; converges in a few passes)."""
    reach = np.zeros_like(mask)
    reach[0], reach[-1], reach[:, 0], reach[:, -1] = mask[0], mask[-1], mask[:, 0], mask[:, -1]
    while True:
        before = reach.sum()
        for _ in range(2):
            # sweep down, up, right, left: carry reach along runs of mask
            for y in range(1, mask.shape[0]):
                reach[y] |= mask[y] & reach[y - 1]
            for y in range(mask.shape[0] - 2, -1, -1):
                reach[y] |= mask[y] & reach[y + 1]
            r = reach.T
            m = mask.T
            for x in range(1, m.shape[0]):
                r[x] |= m[x] & r[x - 1]
            for x in range(m.shape[0] - 2, -1, -1):
                r[x] |= m[x] & r[x + 1]
        if reach.sum() == before:
            return reach


def _components(fg):
    """Label connected foreground (8-connectivity via 1-px horizontal tolerance) with run-length union-find.
    Returns list of dict(area, cx, cy, runs=[(y, x0, x1), ...])."""
    parent = []

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    runs, prev = [], []
    for y in range(fg.shape[0]):
        row = fg[y]
        d = np.diff(np.concatenate([[0], row.view(np.int8), [0]]))
        cur = []
        for x0, x1 in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            i = len(parent)
            parent.append(i)
            runs.append((y, int(x0), int(x1)))
            cur.append((int(x0), int(x1), i))
            for p0, p1, j in prev:
                if p0 <= x1 and p1 >= x0:
                    a, b = find(i), find(j)
                    if a != b:
                        parent[a] = b
        prev = cur
    comps = {}
    for i, (y, x0, x1) in enumerate(runs):
        c = comps.setdefault(find(i), dict(area=0, sx=0.0, sy=0.0, runs=[]))
        n = x1 - x0
        c["area"] += n
        c["sx"] += n * (x0 + x1 - 1) / 2.0
        c["sy"] += n * y
        c["runs"].append((y, x0, x1))
    for c in comps.values():
        c["cx"], c["cy"] = c["sx"] / c["area"], c["sy"] / c["area"]
    return list(comps.values())


def cut_sheet(path, names, rows, cols, out_dir, white=236, min_area=150):
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im)
    h, w = rgb.shape[:2]
    near = rgb.min(axis=2) > white
    fg = ~_border_connected(near)
    fg = np.asarray(Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))) > 0
    grown = np.asarray(Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(9))) > 0   # joins near parts
    cells = {}
    for c in _components(grown):
        if c["area"] < min_area:
            continue
        key = (min(rows - 1, int(c["cy"] / (h / rows))), min(cols - 1, int(c["cx"] / (w / cols))))
        cells.setdefault(key, []).append(c)
    alpha_all = np.asarray(Image.fromarray((fg * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)))
    os.makedirs(out_dir, exist_ok=True)
    res = []
    for (r, c), comps in sorted(cells.items()):
        k = r * cols + c
        if k >= len(names):
            continue
        m = np.zeros((h, w), bool)
        for comp in comps:
            for y, x0, x1 in comp["runs"]:
                m[y, x0:x1] = True
        ys, xs = np.where(m & fg)
        if len(ys) == 0:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        a = np.where(m, alpha_all, 0)[y0:y1, x0:x1]
        Image.fromarray(np.dstack([rgb[y0:y1, x0:x1], a])).save(os.path.join(out_dir, names[k] + ".png"))
        res.append((names[k], int(x1 - x0), int(y1 - y0)))
    return res


def recolor_hue(png, hue_ranges, hue_to, value_scale=1.0, min_sat=0.35):
    """Turn strongly coloured pixels whose hue (degrees) lies in one of hue_ranges to hue_to, e.g. a red tail to green."""
    im = Image.open(png).convert("RGBA")
    a = np.asarray(im).astype(np.float32) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a[..., :3].max(-1), a[..., :3].min(-1)
    d = mx - mn + 1e-9
    hue = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    sat = d / (mx + 1e-9)
    sel = np.zeros(hue.shape, bool)
    for h0, h1 in hue_ranges:
        sel |= (hue >= h0) & (hue <= h1)
    sel &= sat > min_sat
    out = a.copy()
    for y, x in zip(*np.where(sel)):
        out[y, x, :3] = colorsys.hsv_to_rgb(hue_to / 360.0, float(sat[y, x]), float(mx[y, x]) * value_scale)
    Image.fromarray((out * 255).astype(np.uint8)).save(png)


def contact(names, out_dir, out_jpg):
    cw, ch, per = 384, 260, 5
    rows = (len(names) + per - 1) // per
    sheet = Image.new("RGB", (per * cw, rows * ch), (106, 143, 90))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(vk.font_path("SANS_B"), 20)
    for k, n in enumerate(names):
        p = os.path.join(out_dir, n + ".png")
        x, y = (k % per) * cw, (k // per) * ch
        if os.path.exists(p):
            im = Image.open(p).convert("RGBA")
            im.thumbnail((cw - 24, ch - 40))
            sheet.paste(im, (x + (cw - im.width) // 2, y + (ch - 30 - im.height) // 2), im)
        d.text((x + 6, y + ch - 26), n + ("" if os.path.exists(p) else "  MISSING"), fill=(255, 255, 255), font=font)
    os.makedirs(os.path.dirname(out_jpg), exist_ok=True)
    sheet.save(out_jpg, quality=90)


def main():
    cfg = vk.load()
    a = sys.argv[1:]
    pos = []
    i = 0
    opts = {}
    while i < len(a):
        if a[i] in ("--out", "--white", "--contact"):
            opts[a[i]] = a[i + 1]
            i += 2
        elif a[i] == "--allow-missing":
            opts[a[i]] = True
            i += 1
        else:
            pos.append(a[i])
            i += 1
    if len(pos) != 4:
        sys.exit(__doc__)
    path, rows, cols, names = pos[0], int(pos[1]), int(pos[2]), [n.strip() for n in pos[3].split(",")]
    out_dir = opts.get("--out", cfg["cut"])
    res = cut_sheet(path, names, rows, cols, out_dir, int(opts.get("--white", 236)))
    for n, w, h in res:
        print(n, w, h)
    cj = opts.get("--contact", os.path.join(cfg["work"], "cut_sheet.jpg"))
    contact(names, out_dir, cj)
    missing = [n for n in names if n not in [r[0] for r in res]]
    print(f"cut_sheet: sprites={len(res)} of {len(names)} missing={missing} out={out_dir} contact={cj}")
    return 1 if missing and "--allow-missing" not in opts else 0


if __name__ == "__main__":
    sys.exit(main())
