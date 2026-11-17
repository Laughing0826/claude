"""gfx - drawing and animation helpers for transparent overlays (ProRes 4444 with alpha).

Every title, label, sticker, caption and motion graphic is drawn with Pillow as RGBA frames and piped to
ffmpeg as ProRes 4444, which DaVinci Resolve reads with its alpha channel. Importable only; no CLI.

Design language (keep it consistent across a video):
  gold gradient serif capitals for titles, a script face for accents, a calligraphy-style face for the
  second language, soft drop shadows, short ease-out entrances (8-14 frames), 8-frame fade-outs.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import vk

_c = vk.load()
W, H, FPS = _c["W"], _c["H"], _c["FPS"]

# font roles (resolved to files by vk.font_path; override in project.json "fonts")
SERIF_B, SERIF, SERIF_I, SERIF_BI = "SERIF_B", "SERIF", "SERIF_I", "SERIF_BI"
SCRIPT, SCRIPT_B, HAND = "SCRIPT", "SCRIPT_B", "HAND"
ZH, ZH_K, SANS_B, MONO = "ZH", "ZH_K", "SANS_B", "MONO"

GOLD, WHITE, CREAM, INK = (236, 196, 120, 255), (255, 255, 255, 255), (255, 236, 196, 255), (62, 44, 28, 255)
GOLD_GRAD = ((255, 240, 186), (216, 160, 72))   # top colour, bottom colour of the gold lettering

_fc = {}


def ft(role, size):
    """Cached font for a role at a pixel size."""
    k = (role, int(size))
    if k not in _fc:
        _fc[k] = ImageFont.truetype(vk.font_path(role), int(size))
    return _fc[k]


def new():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def tw(s, font):
    """Text width in pixels."""
    return ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(s, font=font)


def fit(role, size, s, max_w, step=2, extra=0):
    """Largest font of this role, starting at size, whose text fits max_w (extra = added letter-spacing in total)."""
    f = ft(role, size)
    while tw(s, f) + extra > max_w and f.size > 12:
        f = ft(role, f.size - step)
    return f


def text(img, xy, s, font, fill=WHITE, stroke=0, stroke_fill=(20, 14, 8, 255), shadow=4, grad=None, anchor="la", blur=5):
    """Draw text with a soft drop shadow, optional outline and optional vertical gradient fill.

    grad=(top_rgb, bottom_rgb) gives the gold lettering. shadow=0 disables the shadow (use on paper backgrounds)."""
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((xy[0] + shadow, xy[1] + shadow), s, font=font, fill=(0, 0, 0, 200), anchor=anchor,
                                stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(img)
    if grad is None:
        d.text(xy, s, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=stroke_fill)
    else:
        if stroke:
            d.text(xy, s, font=font, fill=stroke_fill, anchor=anchor, stroke_width=stroke, stroke_fill=stroke_fill)
        m = Image.new("L", img.size, 0)
        ImageDraw.Draw(m).text(xy, s, font=font, fill=255, anchor=anchor)
        bb = m.getbbox()
        if bb:
            g = np.linspace(0, 1, bb[3] - bb[1])[:, None, None]
            col = np.array(grad[0])[None, None, :] * (1 - g) + np.array(grad[1])[None, None, :] * g
            arr = np.zeros((img.size[1], img.size[0], 4), np.uint8)
            arr[bb[1]:bb[3], :, :3] = col.astype(np.uint8)
            arr[..., 3] = np.asarray(m)
            img.alpha_composite(Image.fromarray(arr))
    return img


def spaced(img, xy, s, font, gap, **kw):
    """Letter-spaced text (gap px between glyphs); supports anchor 'la' and 'ma'."""
    x = xy[0]
    if kw.get("anchor") == "ma":
        tot = sum(tw(ch, font) + gap for ch in s) - gap
        x = xy[0] - tot / 2
        kw = dict(kw, anchor="la")
    for ch in s:
        text(img, (x, xy[1]), ch, font, **kw)
        x += tw(ch, font) + gap


def enc_alpha(frames_iter, dst):
    """Encode an iterator of raw RGBA frame bytes (W x H) as ProRes 4444 with alpha.

    -qscale:v 11 keeps files small; without it a 6-second full-frame title was about 120 MB."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "prores_ks", "-profile:v", "4444", "-qscale:v", "11", "-pix_fmt", "yuva444p10le", "-vendor", "apl0", dst],
                         stdin=subprocess.PIPE)
    for fr in frames_iter:
        p.stdin.write(fr)
    p.stdin.close()
    if p.wait():
        raise RuntimeError("ffmpeg failed encoding " + dst)


def crop_layer(img, t0=0, kind="up", ln=8, dist=26):
    """Turn a full-frame RGBA image into an animated layer for render_layers.

    t0 = frame at which it starts to appear, kind = 'up' | 'left' | 'right' | 'fade' (direction it slides in from),
    ln = frames the entrance takes, dist = slide distance in px."""
    bb = img.getbbox()
    if not bb:
        return None
    return dict(a=np.asarray(img.crop(bb)).astype(np.float32), x=bb[0], y=bb[1], t0=t0, kind=kind, ln=ln, dist=dist)


def ease(t):
    """Ease-out cubic, clamped to 0..1."""
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def over(canvas, a, x, y, k=1.0):
    """Alpha-over a float32 RGBA array `a` onto the uint8 RGBA canvas at (x, y) with opacity k (straight alpha)."""
    h, w = a.shape[:2]
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0 or k <= 0:
        return
    s = a[y0 - y:y1 - y, x0 - x:x1 - x]
    d = canvas[y0:y1, x0:x1].astype(np.float32)
    sa = s[..., 3:4] / 255 * k
    da = d[..., 3:4] / 255
    oa = sa + da * (1 - sa)
    rgb = (s[..., :3] * sa + d[..., :3] * da * (1 - sa)) / np.maximum(oa, 1e-6)
    canvas[y0:y1, x0:x1, :3] = np.clip(rgb, 0, 255)
    canvas[y0:y1, x0:x1, 3:4] = np.clip(oa * 255, 0, 255)


def comp(dst_img, src, x, y):
    """alpha_composite that tolerates positions partly or wholly outside the destination image."""
    x, y = int(x), int(y)
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + src.width, dst_img.width), min(y + src.height, dst_img.height)
    if x1 <= x0 or y1 <= y0:
        return
    dst_img.alpha_composite(src.crop((x0 - x, y0 - y, x1 - x, y1 - y)), (x0, y0))


def render_layers(layers, dur, dst, fade_out=8):
    """Render layers (from crop_layer) for `dur` frames: staggered ease-out entrances, common fade-out at the end."""
    layers = [l for l in layers if l]

    def gen():
        for i in range(dur):
            c = np.zeros((H, W, 4), np.uint8)
            go = min(1.0, (dur - i) / fade_out)
            for l in layers:
                t = (i - l["t0"]) / max(l["ln"], 1)
                if t <= 0:
                    continue
                e = ease(t)
                dx = dy = 0
                if l["kind"] == "up":
                    dy = int((1 - e) * l["dist"])
                elif l["kind"] == "left":
                    dx = -int((1 - e) * l["dist"])
                elif l["kind"] == "right":
                    dx = int((1 - e) * l["dist"])
                over(c, l["a"], l["x"] + dx, l["y"] + dy, min(1.0, t * 1.2) * go)
            yield c.tobytes()
    enc_alpha(gen(), dst)


def sticker_from(cut, height, outline=7):
    """Die-cut sticker look: white outline and soft shadow around an RGBA cut-out, resized to the given height."""
    s = height / cut.height
    im = cut.resize((max(2, int(cut.width * s)), height), Image.LANCZOS)
    pad = outline + 14
    c = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
    a = Image.new("L", c.size, 0)
    a.paste(im.getchannel("A"), (pad, pad))
    edge = a.filter(ImageFilter.MaxFilter(outline * 2 + 1)).filter(ImageFilter.GaussianBlur(1))
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    sh.putalpha(edge.point(lambda v: int(v * 0.55)))
    sh = sh.filter(ImageFilter.GaussianBlur(6))
    out = Image.new("RGBA", c.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (4, 6))
    wh = Image.new("RGBA", c.size, (255, 255, 255, 255))
    wh.putalpha(edge)
    out.alpha_composite(wh)
    out.alpha_composite(im, (pad, pad))
    return out


def sprite(name):
    """Open a cut-out sprite (Graphics/mg/cut/<name>.png) as RGBA."""
    p = os.path.join(_c["cut"], name + ".png")
    if not os.path.exists(p):
        raise FileNotFoundError(f"sprite '{name}' not found at {p}; run cut_sheet.py or remove the graphic that needs it")
    return Image.open(p).convert("RGBA")


def pop_frames(img, cx, cy, dur, wobble=0.0):
    """Pop-in animation for stickers and badges: scale 0 -> 1.15 in 5 frames, settle to 1.0 by frame 8, 6-frame fade-out."""
    for i in range(dur):
        sc = (i + 1) / 5 * 1.15 if i < 5 else (1.15 - 0.15 * (i - 4) / 3 if i < 8 else 1.0)
        al = min(1.0, (dur - i) / 6)
        im = img
        if sc != 1.0 or wobble:
            im = img.resize((max(2, int(img.width * sc)), max(2, int(img.height * sc))), Image.BICUBIC)
            if wobble:
                im = im.rotate(wobble * np.sin(i / 5.0), resample=Image.BICUBIC, expand=True)
        c = np.zeros((H, W, 4), np.uint8)
        over(c, np.asarray(im).astype(np.float32), int(cx - im.width / 2), int(cy - im.height / 2), al)
        yield c.tobytes()
