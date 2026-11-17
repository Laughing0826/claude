"""sheet - contact sheets: many pictures (or video frames) with labels on one JPEG.

Purpose
  This is how the model "watches" its own work: build a sheet, open it with the Read tool, judge by eye.
  Use it to pick photos, to check rendered shots and overlays, and to compare before / after.

Usage (command line)
  python -I -X utf8 sheet.py [--project <folder>] <out.jpg> <cols> <cell_w> @list.txt [--rows N]
      list.txt holds one cell per line:   <image path>::<label>       (blank lines and # comments are skipped;
                                                                       without ::<label> the file name is the label)
      a video works too: its middle frame is shown, or the frame at a time in seconds:   <video path>@3.5::<label>
      --rows N splits a long list into pages of N rows: out_01.jpg, out_02.jpg ...
  example:  python -I -X utf8 sheet.py --project D:\\Trip D:\\Trip\\_work\\picks_sheet.jpg 3 690 @D:\\Trip\\_work\\picks.txt
  A sheet is read comfortably up to about 2100 px wide and 4 rows (3 columns of 690). Use --rows 4 for more.

Usage (import)
  import sheet
  info = sheet.make_sheet(items, out, cols=3, cell_w=690)   # items = [(image_path, label), ...]
                                                            # -> {"out", "cells", "rows", "size", "missing": [paths]}
  sheet.frame_at(video, seconds, out_jpg, width=None)       # one video frame as JPEG, returns out_jpg
  img = sheet.grab(video, seconds)                          # the same frame as a PIL RGB image (no file written)

Inputs   pictures in any format style.open_image reads (RAW files show their embedded preview), videos ffmpeg reads.
Outputs  one JPEG (quality 88): black background, every picture scaled to cell_w wide keeping its shape, the
         label in small white text under it; a row is as high as its tallest picture. A file that cannot be
         read gets a red "MISSING" cell, so the sheet still shows which one. Prints "sheet: out=... cells=N
         rows=N size=WxH missing=N" per sheet; exit code 1 if anything was missing.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

import io
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

import style

VIDEO_EXT = (".mp4", ".mov", ".m4v", ".mts", ".m2ts", ".avi", ".mkv", ".mxf", ".webm")
_GAP = 8                    # black space between cells
_BG = (72, 72, 72)          # what shows through transparent video (overlays) in a grabbed frame


def grab(video, seconds):
    """The frame of video at the given time as a PIL RGB image. A time past the end gives the last frame.
    Transparent video (ProRes 4444 overlays) is shown on mid grey."""
    if not os.path.isfile(video):
        raise FileNotFoundError(f"video not found: {video}")
    info = vk.probe(video)
    end = max(0.0, info["dur"] - 2.0 / (info["fps"] or 25.0))
    err = ""
    for t in (max(0.0, float(seconds)), end, max(0.0, info["dur"] - 0.5), 0.0):   # later tries only if no frame came back
        try:
            r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1", "-f", "image2pipe",
                                "-c:v", "png", "-compression_level", "1", "-pix_fmt", "rgba", "pipe:1"], capture_output=True)
        except FileNotFoundError:
            raise RuntimeError("ffmpeg not found on PATH")
        if r.stdout:
            im = Image.open(io.BytesIO(r.stdout))
            im.load()
            if im.mode == "RGBA" and im.getextrema()[3][0] < 255:
                im = Image.alpha_composite(Image.new("RGBA", im.size, _BG + (255,)), im)
            return im.convert("RGB")
        err = r.stderr.decode("utf-8", "replace").strip()[-200:]
    raise RuntimeError(f"no frame could be read from {video} at {seconds}s. {err}")


def frame_at(video, seconds, out_jpg, width=None):
    """Save the frame of video at the given time as a JPEG (quality 92), optionally scaled to width. Returns out_jpg."""
    im = grab(video, seconds)
    if width and width != im.width:
        im = im.resize((int(width), max(1, round(im.height * int(width) / im.width))), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(out_jpg)), exist_ok=True)
    im.save(out_jpg, "JPEG", quality=92)
    return out_jpg


def _load(path):
    """Picture for one cell: an image file, a video (middle frame) or 'video@seconds'."""
    m = re.match(r"^(.*)@(\d+(?:\.\d+)?)$", path)
    if m and m.group(1).lower().endswith(VIDEO_EXT) and not os.path.exists(path):
        return grab(m.group(1), float(m.group(2)))
    if path.lower().endswith(VIDEO_EXT):
        return grab(path, vk.probe(path)["dur"] / 2)
    return style.open_image(path, fast=True)


def _fit(text, font, width):
    """text, shortened with an ellipsis until it fits the cell."""
    if font.getlength(text) <= width:
        return text
    while len(text) > 1 and font.getlength(text + "…") > width:
        text = text[:-1]
    return text + "…"


def make_sheet(items, out, cols=3, cell_w=690):
    """Write a contact sheet of items = [(image_path, label), ...] to out. See the module docstring for the layout.
    Returns {"out", "cells", "rows", "size": (w, h), "missing": [paths that could not be read]}."""
    items = [(str(p), "" if l is None else str(l)) for p, l in items]
    cols, cell_w = int(cols), int(cell_w)
    if not items:
        raise ValueError("make_sheet: no items")
    if cols < 1 or cell_w < 40:
        raise ValueError(f"make_sheet: cols must be >= 1 and cell_w >= 40, got {cols} and {cell_w}")
    cols = min(cols, len(items))
    fsize = max(13, round(cell_w * 0.032))
    font = ImageFont.truetype(vk.font_path("SANS_B"), fsize)
    label_h = fsize + 12
    cells, missing = [], []
    for path, label in items:
        try:
            im = _load(path)
            im = im.resize((cell_w, max(1, round(im.height * cell_w / im.width))), Image.LANCZOS, reducing_gap=3.0)
        except Exception as ex:                                     # keep going: the sheet must show which file is the problem
            missing.append(path)
            print(f"sheet: MISSING {path}: {ex}", file=sys.stderr, flush=True)
            im = Image.new("RGB", (cell_w, round(cell_w * 9 / 16)), (70, 0, 0))
            d = ImageDraw.Draw(im)
            d.text((cell_w / 2, im.height / 2), "MISSING", font=font, fill=(255, 90, 90), anchor="mm")
            d.text((cell_w / 2, im.height / 2 + fsize + 6), _fit(os.path.basename(path), font, cell_w - 16), font=font, fill=(255, 160, 160), anchor="mm")
        cells.append((im, label))
    rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
    heights = [max(im.height for im, _ in row) for row in rows]
    W = cols * cell_w + (cols + 1) * _GAP
    H = _GAP + sum(h + label_h + _GAP for h in heights)
    sheet = Image.new("RGB", (W, H), "black")
    draw = ImageDraw.Draw(sheet)
    y = _GAP
    for row, rh in zip(rows, heights):
        for c, (im, label) in enumerate(row):
            x = _GAP + c * (cell_w + _GAP)
            sheet.paste(im, (x, y + (rh - im.height) // 2))         # shorter pictures sit in the middle of the row
            draw.text((x + 2, y + rh + 4), _fit(label, font, cell_w - 4), font=font, fill="white")
        y += rh + label_h + _GAP
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out, "JPEG", quality=88)
    return {"out": out, "cells": len(cells), "rows": len(rows), "size": (W, H), "missing": missing}


def main():
    vk.load()
    args = list(sys.argv[1:])
    per_page = None
    if "--rows" in args:
        i = args.index("--rows")
        per_page = args[i + 1:i + 2]
        del args[i:i + 2]
    try:
        if len(args) != 4 or (per_page is not None and (not per_page or int(per_page[0]) < 1)):
            raise ValueError("usage: sheet.py [--project <folder>] <out.jpg> <cols> <cell_w> @list.txt [--rows N]")
        out, cols, cell_w = style.in_project(args[0]), int(args[1]), int(args[2])
        if not out.lower().endswith((".jpg", ".jpeg")):
            raise ValueError(f"the sheet must be a .jpg file, got {out}")
        items = [(p, os.path.basename(p) if l is None else l) for p, l in style.read_list(args[3])]
        if not items:
            raise ValueError(f"the list {args[3]} is empty")
        n = cols * int(per_page[0]) if per_page else len(items)
        pages = [items[i:i + n] for i in range(0, len(items), n)]
        stem, ext = os.path.splitext(out)
        missing = 0
        for k, page in enumerate(pages, 1):
            r = make_sheet(page, out if len(pages) == 1 else f"{stem}_{k:02d}{ext}", cols, cell_w)
            missing += len(r["missing"])
            print(f"sheet: out={r['out']} cells={r['cells']} rows={r['rows']} size={r['size'][0]}x{r['size'][1]} missing={len(r['missing'])}")
            if r["size"][1] > 2.2 * r["size"][0]:
                print("sheet: note - this sheet is very tall and will be hard to read; split it with --rows 4", file=sys.stderr)
    except Exception as ex:
        sys.exit(f"sheet: ERROR {ex}")
    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
