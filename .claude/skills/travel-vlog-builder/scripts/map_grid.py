"""map_grid - draw a labelled coordinate grid on the route map so pin and road positions can be READ BY EYE.

usage:  python -I -X utf8 map_grid.py [--project <folder>] <map image> [<out.jpg>] [--step 100]

Writes <work>/map_grid.jpg (or <out.jpg>): the map resized to the project frame (a note is printed if it was not
already that size) with magenta lines every --step pixels and their coordinates. Open it with the Read tool, read
off the x,y of every stop and of 2-5 points along each road between stops, and put them in project.json "route"
(pins, legs). Automatic detection of red pins was tried in the original project and found one pin of seven;
reading the grid is the reliable way. For a finer reading run again with --step 50.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont

import vk


def main():
    cfg = vk.load()
    a = sys.argv[1:]
    step = 100
    if "--step" in a:
        i = a.index("--step")
        step = int(a[i + 1])
        del a[i:i + 2]
    if not a:
        sys.exit(__doc__)
    out = a[1] if len(a) > 1 else os.path.join(cfg["work"], "map_grid.jpg")
    im = Image.open(a[0]).convert("RGB")
    W, H = cfg["W"], cfg["H"]
    if im.size != (W, H):
        print(f"note: map is {im.size[0]}x{im.size[1]}; resized to {W}x{H} (coordinates are frame pixels). "
              f"Save the map at {W}x{H} so the video uses exactly this picture.")
        im = im.resize((W, H), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(vk.font_path("SANS_B"), 18)
    for x in range(0, W, step):
        d.line((x, 0, x, H), fill=(255, 0, 255), width=1)
        d.text((x + 3, 2), str(x), fill=(255, 0, 255), font=f, stroke_width=2, stroke_fill=(255, 255, 255))
    for y in range(0, H, step):
        d.line((0, y, W, y), fill=(255, 0, 255), width=1)
        d.text((3, y + 2), str(y), fill=(255, 0, 255), font=f, stroke_width=2, stroke_fill=(255, 255, 255))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    im.save(out, quality=92)
    print(f"map_grid: out={out} step={step}")


if __name__ == "__main__":
    main()
