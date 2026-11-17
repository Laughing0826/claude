"""prep - render everything the timeline needs from edit_list_<version>.json.

usage:  python -I -X utf8 prep.py [--project <folder>] all [--force]
        python -I -X utf8 prep.py [--project <folder>] test n1,n2,...      (always re-renders those shots)
        python -I -X utf8 prep.py [--project <folder>] prune               (delete renders the current build no longer uses)

Renders, in parallel worker processes:
  <version>/shots/     one H.264 MP4 per shot except kind S (which Resolve takes straight from the source):
                       photos with slow zoom, phone clips fitted/normalised, documentary cuts, collage slides, rewind intro.
                       Every shot carries spare "handle" frames at both ends (head/tail) for transitions.
  <version>/overlays/  transparent ProRes 4444 MOVs: titles, day cards, location tags, name labels, stickers, badges,
                       cinema bars, flight path, route map, vehicle, parade, and one styled caption per subtitle line.
  Subtitles/           <name>_<version>_EN.srt, _<LANG2>.srt and _BILINGUAL.srt (same timings as the caption overlays)
  <version>/build_<version>.json   shots (with media, head, tail), overlays (file, start, dur, track) and subs:
                       the single file the Resolve build scripts read.  `test` writes build_<version>.test.json instead.

File names contain a hash of everything that affects the picture, including this kit's source code, so a re-run renders
only what changed and never reuses a stale file. Overlay tracks: 2 cinema bars, 3 titles and labels, 4 stickers,
5 motion graphics and badges, 6 captions.

ALWAYS run `test` on one shot of each new element and look at frames (preview_frames.py) before `all`.
"""
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import vk
import gfx
import special
from gfx import W, H, FPS, ft

cfg = vk.load()
HD = cfg["HD"]
SH, OV = cfg["shots"], cfg["overlays"]
L2 = bool(cfg.get("lang2"))
TRACK = dict(bars=2, text=3, stk=4, mg=5, cap=6)


def _salt():
    h = hashlib.sha1()
    for f in ("gfx.py", "special.py", "prep.py", "kb.py", "style.py"):
        p = os.path.join(vk.HERE, f)
        if os.path.exists(p):
            with open(p, "rb") as fh:
                h.update(fh.read())
    h.update(json.dumps([cfg.get(k) for k in ("lut", "look", "fonts", "route", "flight", "vehicle", "parade", "badge_label", "lang2", "year")],
                        sort_keys=True, ensure_ascii=False, default=str).encode("utf-8"))
    return h.hexdigest()


SALT = _salt()


def hid(*parts):
    return hashlib.sha1((SALT + json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)).encode("utf-8")).hexdigest()[:8]


def safe(name):
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(name))[:40]


# ================================================================ shots
SHOT_KEYS = ("kind", "ref", "file", "files", "i", "frames", "mv", "dark", "mute", "speed", "z", "c", "photos", "title", "note", "cap", "bg", "clips")


def shot_path(s):
    return os.path.join(SH, f"{safe(s['ref'])}_{hid([s.get(k) for k in SHOT_KEYS])}.mp4")


def do_shot(s, force=False):
    """Render one shot (if needed) and record media, head and tail on it. Errors are recorded in s['err'], never raised."""
    k = s["kind"]
    if k == "S":
        return s
    dst = shot_path(s)
    try:
        if force and os.path.exists(dst):
            os.remove(dst)
        need = not os.path.exists(dst)
        if k in ("A", "P", "M"):
            import kb
            s["head"], s["tail"] = HD, HD
            if need:
                amt = 0.0 if k in ("A", "M") else {0: 0.45, 1: 0.15, 2: 0.0}[s.get("dark", 0)]
                kb.render(s["file"], dst, HD + s["frames"] + HD, s.get("mv", "in"), amt)
        elif k in ("V", "SV"):
            srcdur = s.get("srcdur") or vk.probe(s["file"])["dur"]
            head = min(HD, int(s["i"] * FPS))
            tail = max(0, min(HD, int((srcdur - s["i"] - s["d"]) * FPS) - 1))
            s["head"], s["tail"] = head, tail
            if need:
                tot = head + s["frames"] + tail
                lut = k == "SV" and bool(cfg.get("lut"))
                vf = special.vf_fit(s["file"], lut=lut, pre=f"fps={FPS},", pix="yuv420p")
                cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{s['i'] - head / FPS:.3f}", "-i", s["file"]]
                if s.get("mute") or not vk.probe(s["file"])["audio"]:
                    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex", "[0:v]" + vf + "[v]", "-map", "[v]", "-map", "1:a"]
                else:   # clip sound is loudness-normalised so phone clips and camera clips sit at one level
                    cmd += ["-filter_complex", "[0:v]" + vf + "[v];[0:a]aresample=48000,loudnorm=I=-20:TP=-2:LRA=11[a]", "-map", "[v]", "-map", "[a]"]
                cmd += ["-frames:v", str(tot), "-t", f"{tot / FPS:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                        "-c:a", "aac", "-b:a", "160k", "-ac", "2", dst]
                r = subprocess.run(cmd, capture_output=True, text=True, cwd=vk.lut_local() if lut else None)
                if r.returncode:
                    s["err"] = r.stderr[-300:]
        elif k == "D":
            s["head"], s["tail"] = HD, HD
            if need:
                special.doc_shot(s, dst, HD)
        elif k == "C":
            s["head"], s["tail"] = HD, HD
            if need:
                special.collage(s, dst, HD)
        elif k == "R":
            s["head"], s["tail"] = HD, HD
            if need:
                special.rewind(s, dst, HD)
        else:
            s["err"] = f"unknown kind {k}"
        s["media"] = dst
    except Exception as e:
        s["err"] = repr(e)[:300]
        if os.path.exists(dst):
            os.remove(dst)
    return s


def _force_shot(s):
    return do_shot(s, True)


# ================================================================ overlays
def clean(t):
    """Drop characters outside the Basic Multilingual Plane (emoji): the caption fonts cannot draw them."""
    return re.sub(r"[^\u0000-￿]", "", t).strip()


def scrim(kind):
    """Soft dark patch behind lettering so it stays readable on bright footage."""
    sc = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(sc)
    if kind == "title":
        d.rectangle((0, 250, W, 790), fill=135)
    elif kind == "card":
        d.ellipse((-520, -340, 1320, 560), fill=130)
    elif kind == "lower":
        d.ellipse((-400, 640, 1200, 1100), fill=120)
    sc = sc.filter(ImageFilter.GaussianBlur(70))
    return Image.merge("RGBA", (Image.new("L", sc.size, 0),) * 3 + (sc,))


def text_overlay(s, dst, dur):
    """Title, day card, documentary name title, species label and location tag for one shot, as staggered layers."""
    L = []
    card, loc, sp, title, lower = s.get("card"), s.get("loc"), s.get("sp"), s.get("title"), s.get("lower")
    if title:
        main, l2, small = title[0], title[1], title[2]
        top, tag = (title[3], title[4]) if len(title) >= 5 else ("", "")
        L.append(gfx.crop_layer(scrim("title"), 0, "fade", 10))
        if top:
            a = gfx.new()
            gfx.text(a, (W // 2, 262), top, ft(gfx.SCRIPT_B, 70), fill=gfx.WHITE, anchor="ma")
            L.append(gfx.crop_layer(a, 4, "up", 12))
        f1 = ft(gfx.SERIF_B, 108)
        while gfx.tw(main, f1) + 9 * len(main) > 1760:
            f1 = ft(gfx.SERIF_B, f1.size - 4)
        b = gfx.new()
        gfx.spaced(b, (W // 2, 372), main, f1, 9, grad=gfx.GOLD_GRAD, stroke=2, anchor="ma", shadow=6)
        L.append(gfx.crop_layer(b, 12, "up", 14, 34))
        c = gfx.new()
        ImageDraw.Draw(c).line(((W - 620) / 2, 512, (W + 620) / 2, 512), fill=gfx.GOLD, width=3)
        ImageDraw.Draw(c).regular_polygon((W // 2, 512, 9), 4, rotation=45, fill=gfx.GOLD)
        L.append(gfx.crop_layer(c, 22, "fade", 10))
        if l2:
            d = gfx.new()
            gfx.text(d, (W // 2, 532), l2, gfx.fit(gfx.ZH_K, 70, l2, 1700), grad=gfx.GOLD_GRAD, stroke=1, anchor="ma")
            L.append(gfx.crop_layer(d, 26, "up", 12))
        if tag:
            e = gfx.new()
            gfx.text(e, (W // 2, 636 if l2 else 548), tag, gfx.fit(gfx.SCRIPT, 40, tag, 1700), fill=gfx.WHITE, anchor="ma")
            L.append(gfx.crop_layer(e, 40, "up", 12))
        if small:
            f = gfx.new()
            gfx.spaced(f, (W // 2, 722 if l2 else 634), small, ft(gfx.SERIF, 28), 5, fill=gfx.CREAM, anchor="ma")
            L.append(gfx.crop_layer(f, 52, "fade", 12))
    if card:
        dayw, rest = card[0].split(" · ", 1)                    # "DAY 1", "16 FEB · PLACE — PLACE"
        word, num = (dayw.split() + [""])[:2]
        L.append(gfx.crop_layer(scrim("card"), 0, "fade", 8))
        a = gfx.new()
        gfx.text(a, (92, 62), word.capitalize(), ft(gfx.SCRIPT_B, 84), grad=gfx.GOLD_GRAD, stroke=1)
        gfx.text(a, (92 + gfx.tw(word.capitalize(), ft(gfx.SCRIPT_B, 84)) + 26, 18), num, ft(gfx.SERIF_B, 150), grad=gfx.GOLD_GRAD, stroke=2, shadow=6)
        L.append(gfx.crop_layer(a, 2, "left", 10, 60))
        b = gfx.new()
        ImageDraw.Draw(b).line((96, 202, 700, 202), fill=gfx.GOLD, width=3)
        L.append(gfx.crop_layer(b, 8, "left", 10, 120))
        c = gfx.new()
        fr_ = ft(gfx.SERIF, 34)
        while gfx.tw(rest, fr_) + 3 * len(rest) > 1500 and fr_.size > 18:
            fr_ = ft(gfx.SERIF, fr_.size - 2)
        gfx.spaced(c, (96, 218), rest, fr_, 3, fill=gfx.WHITE)
        L.append(gfx.crop_layer(c, 12, "left", 10, 40))
        if card[1]:
            d = gfx.new()
            gfx.text(d, (96, 268), card[1], gfx.fit(gfx.ZH_K, 50, card[1], 1500), fill=gfx.CREAM)
            L.append(gfx.crop_layer(d, 16, "left", 10, 40))
    if lower:
        L.append(gfx.crop_layer(scrim("lower"), 0, "fade", 10))
        a = gfx.new()
        ImageDraw.Draw(a).line((120, 742, 520, 742), fill=gfx.GOLD, width=2)
        L.append(gfx.crop_layer(a, 14, "left", 14, 160))
        b = gfx.new()
        gfx.spaced(b, (120, 758), lower[0], ft(gfx.SERIF, 56), 12, fill=gfx.WHITE)
        L.append(gfx.crop_layer(b, 18, "up", 14))
        c = gfx.new()
        gfx.text(c, (122, 832), lower[1], ft(gfx.SERIF_I, 34), fill=gfx.GOLD)
        if lower[2]:
            gfx.text(c, (122 + gfx.tw(lower[1], ft(gfx.SERIF_I, 34)) + 36, 826), lower[2], ft(gfx.ZH_K, 42), fill=gfx.CREAM)
        L.append(gfx.crop_layer(c, 26, "up", 14))
    if sp:
        a = gfx.new()
        ImageDraw.Draw(a).rectangle((84, 778, 90, 876 if sp[1] else 836), fill=gfx.GOLD)
        gfx.text(a, (108, 768), sp[0], ft(gfx.SERIF_BI, 48), grad=gfx.GOLD_GRAD, stroke=1)
        if sp[1]:
            gfx.text(a, (108, 830), sp[1], ft(gfx.ZH_K, 44), fill=gfx.WHITE)
        L.append(gfx.crop_layer(a, 2, "left", 9, 40))
    if loc:
        a = gfx.new()
        d = ImageDraw.Draw(a)
        f1, f2 = ft(gfx.SANS_B, 32), ft(gfx.ZH, 28)
        w = max(d.textlength(loc[0], font=f1), d.textlength(loc[1] or "", font=f2)) + 86
        x1, y0 = 1846, 64
        x0 = x1 - w
        hh = 100 if loc[1] else 62
        sh = gfx.new()
        ImageDraw.Draw(sh).rounded_rectangle((x0 + 4, y0 + 6, x1 + 4, y0 + hh + 6), 14, fill=(0, 0, 0, 150))
        a.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
        d = ImageDraw.Draw(a)
        d.rounded_rectangle((x0, y0, x1, y0 + hh), 14, fill=(255, 255, 255, 240))
        cy = y0 + hh // 2
        d.ellipse((x0 + 22, cy - 14, x0 + 50, cy + 14), fill=(214, 64, 52, 255))
        d.ellipse((x0 + 31, cy - 5, x0 + 41, cy + 5), fill=gfx.WHITE)
        d.text((x0 + 66, y0 + 10), loc[0], font=f1, fill=(30, 30, 30, 255))
        if loc[1]:
            d.text((x0 + 66, y0 + 54), loc[1], font=f2, fill=(90, 90, 90, 255))
        L.append(gfx.crop_layer(a, 2, "right", 9, 60))
    gfx.render_layers(L, dur, dst)


def caption_overlay(job):
    """One styled caption: second language on top (white, bold), English below (cream italic), both outlined."""
    dst, en, l2, dur = job
    if os.path.exists(dst):
        return dst
    a = gfx.new()
    if l2:
        gfx.text(a, (W // 2, 952), l2, gfx.fit(gfx.ZH, 50, l2, 1700), fill=gfx.WHITE, stroke=3, stroke_fill=(30, 20, 10, 255), anchor="mm", shadow=3, blur=4)
        gfx.text(a, (W // 2, 1012), en, gfx.fit(gfx.SERIF_I, 36, en, 1700, 1), fill=gfx.CREAM, stroke=2, stroke_fill=(30, 20, 10, 255), anchor="mm", shadow=3, blur=4)
    else:
        gfx.text(a, (W // 2, 996), en, gfx.fit(gfx.SERIF_I, 46, en, 1700, 1), fill=gfx.WHITE, stroke=3, stroke_fill=(30, 20, 10, 255), anchor="mm", shadow=3, blur=4)
    gfx.render_layers([gfx.crop_layer(a, 0, "up", 6, 14)], dur, dst, fade_out=5)
    return dst


def sticker_img(txt):
    """Yellow rounded pop-up sticker, tilted 4 degrees."""
    f = ft(gfx.ZH, 50)
    w = int(gfx.tw(txt, f)) + 64
    h, pad = 104, 40
    im = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((pad + 6, pad + 8, pad + w + 6, pad + h + 8), 22, fill=(0, 0, 0, 150))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((pad, pad, pad + w, pad + h), 22, fill=(255, 214, 10, 255), outline=(30, 30, 30, 255), width=4)
    d.text((pad + 32, pad + 16), txt, font=f, fill=(30, 30, 30, 255))
    return im.rotate(4, resample=Image.BICUBIC, expand=True)


def sticker_overlay(s, dst, dur):
    st = sticker_img(clean(s["stk"]))
    if s.get("card"):
        cx, cy = 1480, 380          # clear of the day card (top left)
    elif s.get("loc"):
        cx, cy = 460, 240           # clear of the location tag (top right)
    else:
        cx, cy = 1470, 235
    cx = min(max(cx, st.width // 2 + 30), W - st.width // 2 - 30)
    gfx.enc_alpha(gfx.pop_frames(st, cx, cy, dur), dst)


def badge_overlay(s, dst, dur):
    """Illustrated sticker with 'Spotted!  #n' under it, right-hand side, popping in with a wobble."""
    st = gfx.sticker_from(gfx.sprite(s["badge"]), 230)
    im = Image.new("RGBA", (max(st.width, 380) + 20, st.height + 96), (0, 0, 0, 0))
    im.alpha_composite(st, ((im.width - st.width) // 2, 0))
    gfx.text(im, (im.width // 2, st.height + 2), f"{cfg['badge_label']}  #{s['badge_no']}", ft(gfx.SCRIPT_B, 46), grad=gfx.GOLD_GRAD, stroke=2, anchor="ma")
    gfx.enc_alpha(gfx.pop_frames(im, 1650, 610 if not s.get("stk") else 660, dur, wobble=3.0), dst)


def letterbox_overlay(dst, dur):
    """Cinema bars (138 px top and bottom = about 2.39:1) easing in and out over 12 frames, for documentary sequences."""
    def gen():
        for i in range(dur):
            k = min(1.0, (i + 1) / 12, (dur - i) / 12)
            h = int(138 * gfx.ease(k))
            c = np.zeros((H, W, 4), np.uint8)
            if h:
                c[:h, :, 3] = 255
                c[H - h:, :, 3] = 255
            yield c.tobytes()
    gfx.enc_alpha(gen(), dst)


def bez(p0, p1, p2, u):
    return ((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0], (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1])


def flight_overlay(dst, dur):
    """Flight-path panel (top left): dotted arc between two cities, a plane sprite flying it, distance/time label."""
    fl = cfg["flight"]
    plane = gfx.sticker_from(gfx.sprite(fl.get("sprite", "plane")), 78, outline=4)
    P0, P1, P2 = (190, 318), (575, 60), (960, 318)
    base = gfx.new()
    sh = gfx.new()
    ImageDraw.Draw(sh).rounded_rectangle((70, 70, 1080, 440), 28, fill=(10, 14, 24, 150))
    base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(3)))
    d = ImageDraw.Draw(base)
    for k in range(0, 61):
        x, y = bez(P0, P1, P2, k / 60)
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(255, 255, 255, 90))
    for p, (en, l2) in ((P0, fl["from"]), (P2, fl["to"])):
        d.ellipse((p[0] - 11, p[1] - 11, p[0] + 11, p[1] + 11), fill=gfx.GOLD, outline=(255, 255, 255, 255), width=3)
        gfx.text(base, (p[0], p[1] + 22), en, ft(gfx.SERIF_B, 28), fill=gfx.WHITE, anchor="ma", shadow=2)
        if l2:
            gfx.text(base, (p[0], p[1] + 58), l2, ft(gfx.ZH_K, 32), fill=gfx.CREAM, anchor="ma", shadow=2)
    if fl.get("label"):
        gfx.text(base, (575, 250), fl["label"], ft(gfx.SCRIPT_B, 38), grad=gfx.GOLD_GRAD, anchor="ma", shadow=2)

    def gen():
        for i in range(dur):
            al = min(1.0, (i + 1) / 8, (dur - i) / 8)
            u = min(max((i - 10) / max(dur - 46, 1), 0), 1)
            u = u * u * (3 - 2 * u)
            fr = base.copy()
            d = ImageDraw.Draw(fr)
            for k in range(0, int(u * 120) + 1):
                x, y = bez(P0, P1, P2, k / 120)
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(255, 226, 150, 255))
            x, y = bez(P0, P1, P2, u)
            x2, y2 = bez(P0, P1, P2, min(u + 0.02, 1.0)) if u < 0.98 else (x + 1, y + 0.6)
            pl = plane.rotate(-math.degrees(math.atan2(y2 - y, x2 - x)), resample=Image.BICUBIC, expand=True)
            gfx.comp(fr, pl, x - pl.width / 2, y - pl.height / 2)
            c = np.zeros((H, W, 4), np.uint8)
            gfx.over(c, np.asarray(fr).astype(np.float32), 0, 0, al)
            yield c.tobytes()
    gfx.enc_alpha(gen(), dst)


def route_overlay(dst, frames):
    """Animated route over the map shot: a line grows leg by leg, reached pins pulse, the vehicle sprite drives the
    line, and a panel counts kilometres and days. The map shot (kind M, mv='in') zooms 1.00 -> 1.09 over its whole
    length including handles; tf() applies the same zoom so the graphics stay glued to the map."""
    rt = cfg["route"]
    pins, legs_pts, kms = rt["pins"], rt["legs"], rt["km"]
    nl = len(legs_pts)
    labels = rt.get("labels") or [f"Day {k + 1}" for k in range(nl)]
    end_label = rt.get("end_label", f"Day {nl + 1}")
    panel = rt.get("panel", [50, 560])                       # top-left of the km counter; keep it off the map's own text
    truck = gfx.sticker_from(gfx.sprite(cfg["vehicle"]), 92, outline=4)
    truck_l = truck.transpose(Image.FLIP_LEFT_RIGHT)
    legs = []
    for pts in legs_pts:
        dense = []
        for a, b in zip(pts, pts[1:]):
            for k in range(20):
                dense.append((a[0] + (b[0] - a[0]) * k / 20, a[1] + (b[1] - a[1]) * k / 20))
        dense.append(tuple(pts[-1]))
        legs.append(dense)
    ntot = HD + frames + HD
    off, dur = 6, frames - 12

    def tf(p, j):
        z = 1 + 0.09 * ((j + off + HD) / max(ntot - 1, 1))
        return ((p[0] - W / 2) * z + W / 2, (p[1] - H / 2) * z + H / 2)

    def gen():
        for i in range(dur):
            al = min(1.0, (i + 1) / 8, (dur - i) / 8)
            u = min(max((i - 8) / max(dur - 34, 1), 0), 1) * nl
            leg = min(int(u), nl - 1)
            fu = u - leg if u < nl else 1.0
            fr = gfx.new()
            d = ImageDraw.Draw(fr)
            trail = []
            for li in range(leg):
                trail += legs[li]
            cur = legs[leg][:max(1, int(fu * (len(legs[leg]) - 1)) + 1)]
            trail += cur
            pts = [tf(p, i) for p in trail]
            if len(pts) > 1:
                d.line(pts, fill=(90, 40, 10, 200), width=13, joint="curve")
                d.line(pts, fill=(255, 214, 110, 255), width=7, joint="curve")
            for k, p in enumerate(pins):
                if k <= leg or u >= nl:
                    x, y = tf(p, i)
                    pulse = (i * 0.25 + k) % 3
                    r = 16 + pulse * 9
                    d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 226, 150, int(220 * (1 - pulse / 3))), width=4)
            pos = tf(cur[-1], i)
            prev = tf(cur[-2], i) if len(cur) > 1 else (pos[0] - 1, pos[1])
            tr = truck if pos[0] >= prev[0] else truck_l
            gfx.comp(fr, tr, pos[0] - tr.width / 2, pos[1] - tr.height + 18 + int(2 * math.sin(i * 0.9)))
            km = sum(kms[:leg]) + kms[leg] * fu if u < nl else sum(kms)
            pan = gfx.new()
            ImageDraw.Draw(pan).rounded_rectangle((panel[0], panel[1], panel[0] + 490, panel[1] + 100), 22, fill=(40, 24, 10, 170))
            fr.alpha_composite(pan)
            gfx.text(fr, (panel[0] + 30, panel[1] + 14), f"{km:,.0f} km", ft(gfx.SERIF_B, 58), grad=gfx.GOLD_GRAD, shadow=2)
            gfx.text(fr, (panel[0] + 330, panel[1] + 32), labels[leg] if u < nl else end_label, ft(gfx.SCRIPT_B, 38), fill=gfx.WHITE, shadow=2)
            c = np.zeros((H, W, 4), np.uint8)
            gfx.over(c, np.asarray(fr).astype(np.float32), 0, 0, al)
            yield c.tobytes()
    gfx.enc_alpha(gen(), dst)


def vehicle_overlay(dst, dur):
    """The vehicle sprite drives across the bottom of the frame, left to right (used over the opening title)."""
    ta = np.asarray(gfx.sticker_from(gfx.sprite(cfg["vehicle"]), 120, outline=5)).astype(np.float32)

    def gen():
        for i in range(dur):
            x = int(-260 + (W + 420) * (i / max(dur - 1, 1)))
            y = 905 + int(3 * math.sin(i * 0.9))
            c = np.zeros((H, W, 4), np.uint8)
            gfx.over(c, ta, x, y, min(1.0, (dur - i) / 6))
            yield c.tobytes()
    gfx.enc_alpha(gen(), dst)


def parade_overlay(dst, dur):
    """All the illustrated sprites hop up along the bottom edge one after another (end card)."""
    items = cfg.get("parade") or [[os.path.splitext(f)[0], 130] for f in sorted(os.listdir(cfg["cut"])) if f.endswith(".png")][:12]
    st = [np.asarray(gfx.sticker_from(gfx.sprite(n), h, outline=4)).astype(np.float32) for n, h in items]
    xs = np.linspace(40, W - 40, len(items) + 1)

    def gen():
        for i in range(dur):
            c = np.zeros((H, W, 4), np.uint8)
            go = min(1.0, (dur - i) / 8)
            for k, a in enumerate(st):
                t = (i - 30 - k * 4) / 9.0
                if t <= 0:
                    continue
                e = gfx.ease(t)
                hh = a.shape[0]
                y = 1052 - hh * e + int(4 * math.sin(i * 0.3 + k)) + (0 if t >= 1 else int(18 * math.sin(t * math.pi)))
                gfx.over(c, a, int((xs[k] + xs[k + 1]) / 2 - a.shape[1] / 2), int(y), min(1.0, t * 1.5) * go)
            yield c.tobytes()
    gfx.enc_alpha(gen(), dst)


def do_overlays(arg):
    """Render every overlay that belongs to one shot. Returns (n, [overlay dicts], error or None)."""
    s, force = arg
    res = []
    n, fr, st0 = s["n"], s["frames"], s["start"]

    def add(name, off, dur, track, fn, *key):
        if dur < 8:
            return
        dst = os.path.join(OV, f"{name}_{hid(name, dur, key)}.mov")
        if force and os.path.exists(dst):
            os.remove(dst)
        if not os.path.exists(dst):
            fn(dst, dur)
        res.append(dict(file=dst, start=st0 + off, dur=dur, track=track, shot=n, name=name))
    try:
        # collage slides draw their own title; every other kind gets text overlays
        if s["kind"] != "C" and any(s.get(k) for k in ("card", "loc", "sp", "title", "lower")):
            off = 8 if s.get("tr") else 3                # wait for an incoming transition to finish
            dur = min(fr - off - 5, 165 if s.get("title") else 115)
            add("text", off, dur, TRACK["text"], lambda dst, dur: text_overlay(s, dst, dur),
                [s.get(k) for k in ("card", "loc", "sp", "title", "lower")])
        if s.get("stk"):
            add("stk", 10, min(fr - 16, 62), TRACK["stk"], lambda dst, dur: sticker_overlay(s, dst, dur), s["stk"], bool(s.get("card")), bool(s.get("loc")))
        if s.get("badge"):
            add("badge", 14, min(fr - 20, 64), TRACK["mg"], lambda dst, dur: badge_overlay(s, dst, dur), s["badge"], s["badge_no"], bool(s.get("stk")))
        mg = s.get("mg")
        if mg == "vehicle":
            add("vehicle", 30, fr - 40, TRACK["mg"], vehicle_overlay)
        if mg == "parade":
            add("parade", 6, fr - 6, TRACK["mg"], parade_overlay)
        if mg == "route":
            add("route", 6, fr - 12, TRACK["mg"], lambda dst, dur: route_overlay(dst, fr), fr)
        if mg == "flight":
            add("flight", 8, s["mg_dur"], TRACK["mg"], flight_overlay)
        if s.get("lb_dur"):
            add("letterbox", 0, s["lb_dur"], TRACK["bars"], letterbox_overlay)
    except Exception as e:
        return n, res, repr(e)[:300]
    return n, res, None


# ================================================================ main
def plan(E):
    """Derived values that span several shots: flight graphic length, cinema bars per documentary run, badge numbers, captions."""
    for s in E:
        if s.get("mg") == "flight":      # the flight panel stays up across this shot and the next ones (mg_span shots, default 3)
            last = E[min(s["n"] + int(s.get("mg_span", 3)) - 1, len(E) - 1)]
            s["mg_dur"] = (last["start"] + last["frames"]) - s["start"] - 8 - 6
    k = 0
    while k < len(E):
        if E[k].get("doc"):
            j = k
            while j + 1 < len(E) and E[j + 1].get("doc") == E[k]["doc"]:
                j += 1
            E[k]["lb_dur"] = E[j]["start"] + E[j]["frames"] - E[k]["start"]
            k = j + 1
        else:
            k += 1
    order = []
    for s in E:
        if s.get("badge"):
            if s["badge"] not in order:
                order.append(s["badge"])
            s["badge_no"] = order.index(s["badge"]) + 1
    subs = []
    for s in E:
        if s.get("sub"):
            en, l2, span = s["sub"]
            last = E[min(s["n"] + span - 1, len(E) - 1)]
            subs.append([s["start"] + 5, last["start"] + last["frames"] - 4, clean(en), clean(l2 or ""), s["n"]])
        for (t0, t1, en, l2) in s.get("subs", []):
            subs.append([s["start"] + round(t0 * FPS), s["start"] + round(t1 * FPS), clean(en), clean(l2 or ""), s["n"]])
    subs.sort()
    for a, b in zip(subs, subs[1:]):      # never show two captions at once
        if a[1] > b[0] - 2:
            a[1] = b[0] - 2
    return subs


def cap_path(x):
    return os.path.join(OV, f"cap_{hid('cap', x[2], x[3], x[1] - x[0])}.mov")


def main():
    args = sys.argv[1:]
    mode = args[0] if args else ""
    if mode not in ("all", "test", "prune"):
        sys.exit(__doc__)
    if (W, H) != (1920, 1080):
        sys.exit("The graphics are laid out for a 1920 x 1080 frame. Keep the project at 1920 x 1080 (upscale at delivery if needed).")
    if not os.path.exists(cfg["edit_list"]):
        sys.exit(f"{cfg['edit_list']} not found. Run build_edl.py first.")
    force = "--force" in args
    os.makedirs(SH, exist_ok=True)
    os.makedirs(OV, exist_ok=True)
    with open(cfg["edit_list"], encoding="utf-8") as f:
        E = json.load(f)
    test = [int(x) for x in args[1].split(",")] if mode == "test" else None
    subs = plan(E)
    if mode == "prune":
        keep = {shot_path(s) for s in E if s["kind"] != "S"} | {cap_path(x) for x in subs}
        if os.path.exists(cfg["build"]):
            with open(cfg["build"], encoding="utf-8") as f:
                keep |= {o["file"] for o in json.load(f)["overlays"]}
        gone = [os.path.join(d, f) for d in (SH, OV) for f in os.listdir(d) if os.path.join(d, f) not in keep]
        for p in gone:
            os.remove(p)
        print(f"pruned {len(gone)} unused files")
        return 0
    work = [s for s in E if test is None or s["n"] in test]
    with ProcessPoolExecutor(int(cfg["workers"])) as ex:
        done = {s["n"]: s for s in ex.map(_force_shot if (test or force) else do_shot, work)}
        E = [done.get(s["n"], s) for s in E]
        ovs = {n: (r, e) for n, r, e in ex.map(do_overlays, [(s, bool(test or force)) for s in E if test is None or s["n"] in test])}
        jobs = [(cap_path(x), x[2], x[3], x[1] - x[0]) for x in subs if test is None or x[4] in test]
        if test or force:
            for j in jobs:
                if os.path.exists(j[0]):
                    os.remove(j[0])
        cap_err = []
        for j, r in zip(jobs, ex.map(_cap_safe, jobs)):
            if r:
                cap_err.append((j[1][:40], r))
    overlays = [dict(file=cap_path(x), start=x[0], dur=x[1] - x[0], track=TRACK["cap"], shot=x[4], name="cap")
                for x in subs if test is None or x[4] in test]
    nerr = len(cap_err)
    for s in E:
        r, e = ovs.get(s["n"], ([], None))
        overlays += r
        if e:
            nerr += 1
            print("OVERLAY ERR", s["n"], s["ref"], e)
        if s.get("err"):
            nerr += 1
            print("SHOT ERR", s["n"], s["ref"], s["err"])
    for t, e in cap_err:
        print("CAPTION ERR", t, e)
    meta = dict(name=cfg["name"], version=cfg["version"], fps=FPS, width=W, height=H, handles=HD, lut=cfg.get("lut"), lang2=cfg.get("lang2"),
                partial=bool(test), rendered=sorted(done), frames=E[-1]["start"] + E[-1]["frames"])
    out = cfg["build"] if test is None else cfg["build"].replace(".json", ".test.json")
    if test is None:
        os.makedirs(cfg["subs"], exist_ok=True)
        slug = safe(cfg["name"])
        l2 = (cfg.get("lang2") or "").upper()
        tracks = [("EN", lambda x: x[2])] + ([(l2, lambda x: x[3]), ("BILINGUAL", lambda x: x[3] + "\n" + x[2])] if L2 else [])
        meta["srt"] = {}
        for lang, fn in tracks:
            p = os.path.join(cfg["subs"], f"{slug}_{cfg['version']}_{lang}.srt")
            with open(p, "w", encoding="utf-8") as o:
                for i, x in enumerate(subs, 1):
                    o.write(f"{i}\n{vk.tc(x[0])} --> {vk.tc(x[1])}\n{fn(x)}\n\n")
            meta["srt"][lang] = p
    with open(out, "w", encoding="utf-8") as f:
        json.dump(dict(meta=meta, shots=E, overlays=overlays, subs=subs), f, ensure_ascii=False, indent=1)
    print("shots", len(E), "rendered", sum(1 for s in E if s.get("media")), "direct", sum(1 for s in E if s["kind"] == "S"),
          "overlays", len(overlays), "subs", len(subs), "errors", nerr)
    print("build", out)
    return 1 if nerr else 0


def _cap_safe(job):
    try:
        caption_overlay(job)
        return None
    except Exception as e:
        return repr(e)[:300]


if __name__ == "__main__":
    sys.exit(main())
