"""special - the three "special" shot types, each rendered as a finished video shot with handles:

  doc_shot  documentary cut: optional slow motion, a slow push-in or punch-in (close-up crop), main-camera LUT
  rewind    VHS "tape rewind" intro: clips play backwards at speed with tracking noise, REW / date / counter
            on-screen display and a synthesised tape sound, then a clean PLAY on the first clip of the story
  collage   scrapbook slide: 2-4 photos as taped polaroids dropping onto an illustrated paper background,
            with a handwritten-style title label, a sticky date note and a caption strip

Importable only (prep.py calls these). Frames are RGB numpy arrays; everything streams through ffmpeg pipes so
memory stays low even with several worker processes.
"""
import math
import os
import random
import subprocess
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

import vk
import gfx
from gfx import W, H, FPS, ft

_c = vk.load()


# ---------------------------------------------------------------- decoding / encoding
def vf_fit(path, lut=False, pre="", pix="rgb24"):
    """ffmpeg filter chain that fits any clip into the frame.

    Landscape: scale to cover and centre-crop. Portrait (phone): the whole clip is kept, centred over a blurred,
    darkened, enlarged copy of itself, so nothing is cropped away and there are no black bars.
    lut=True appends the project LUT (ffmpeg must then run with cwd=vk.lut_local())."""
    info = vk.probe(path)
    l = ",lut3d=look.cube" if (lut and _c.get("lut")) else ""
    if info["w"] < info["h"]:
        return (pre + f"split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=24:4,eq=brightness=-0.12[bg];"
                f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2{l},format={pix}")
    return pre + f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}{l},format={pix}"


def iter_frames(path, ss, n, lut=False, speed=1.0):
    """Yield exactly n RGB frames (H x W x 3 uint8) at the project frame rate, starting at source second ss.

    speed < 1 slows the source down (0.5 = half speed). Only use it on high-frame-rate sources (50/60 fps);
    a 25/30 fps source has no extra frames to show and would stutter. Short sources are padded with the last frame."""
    pre = (f"setpts={1.0 / speed:.4f}*PTS," if speed != 1.0 else "") + f"fps={FPS},"
    cwd = vk.lut_local() if lut else None
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{max(ss, 0):.3f}", "-i", path, "-filter_complex",
                          "[0:v]" + vf_fit(path, lut, pre) + "[v]", "-map", "[v]", "-frames:v", str(n), "-f", "rawvideo", "-"],
                         stdout=subprocess.PIPE, cwd=cwd)
    size = W * H * 3
    last = None
    got = 0
    while got < n:
        b = p.stdout.read(size)
        if len(b) < size:
            break
        last = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        got += 1
        yield last
    p.stdout.close()
    p.wait()
    if last is None:
        raise RuntimeError(f"no frames decoded from {path} at {ss:.2f}s")
    while got < n:
        got += 1
        yield last


def encoder(dst, audio_args):
    """ffmpeg process taking raw RGB frames on stdin plus one audio input (audio_args) -> H.264 + AAC MP4."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"] + audio_args +
                            ["-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "15", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", dst], stdin=subprocess.PIPE)


def _finish(enc, dst):
    enc.stdin.close()
    if enc.wait():
        raise RuntimeError("ffmpeg failed encoding " + dst)


SILENCE = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]


# ---------------------------------------------------------------- documentary cut
def doc_shot(s, dst, HD=None):
    """Documentary-style cut of a main-camera clip.

    s: file, i (in-point s), frames, speed (1 or 0.5), z=(z0, z1) zoom from start to end (1.0-1.06 = slow push-in on
    a wide; 1.3-1.5 = punch-in close-up), c=(cx, cy) the point the zoom is centred on, as fractions of the frame.
    Punch-ins above 1.25x get gentle sharpening. Sound is the clip's own ambience at normal speed."""
    HD = _c["HD"] if HD is None else HD
    speed = float(s.get("speed", 1))
    n = HD + s["frames"] + HD
    z0, z1 = s.get("z", (1.0, 1.06))
    cx, cy = s.get("c", (0.5, 0.5))
    a_ss = max(s["i"] - HD / FPS, 0)
    audio = ["-ss", f"{a_ss:.3f}", "-t", f"{n / FPS:.3f}", "-i", s["file"], "-af", "aresample=48000"] if vk.probe(s["file"])["audio"] else SILENCE
    enc = encoder(dst, audio)
    for i, f in enumerate(iter_frames(s["file"], s["i"] - HD / FPS * speed, n, lut=True, speed=speed)):
        t = i / max(n - 1, 1)
        z = z0 + (z1 - z0) * t
        x0 = (W - W / z) * cx
        y0 = (H - H / z) * cy
        im = Image.fromarray(f).transform((W, H), Image.AFFINE, (1 / z, 0, x0, 0, 1 / z, y0), resample=Image.BICUBIC)
        if z > 1.25:
            im = im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=25, threshold=0))
        enc.stdin.write(im.tobytes())
    _finish(enc, dst)


# ---------------------------------------------------------------- VHS rewind intro
def _tri(d, x, y, s, left=True, fill=(255, 255, 255, 255)):
    d.polygon([(x + s, y), (x, y + s * 0.6), (x + s, y + s * 1.2)] if left else [(x, y), (x + s, y + s * 0.6), (x, y + s * 1.2)], fill=fill)


def _osd(kind, date, day, counter):
    """Camcorder on-screen display: REW/PLAY top-left, counter top-right, date and day bottom-left, 'SP  VHS' bottom-right."""
    im = gfx.new()
    d = ImageDraw.Draw(im)
    f, f2 = ft(gfx.MONO, 62), ft(gfx.MONO, 46)

    def t(xy, s, font=f):
        d.text((xy[0] + 4, xy[1] + 4), s, font=font, fill=(0, 0, 0, 200))
        d.text(xy, s, font=font, fill=(255, 255, 255, 245))
    if kind == "rew":
        for k in range(2):
            _tri(d, 104 + k * 46 + 4, 84 + 4, 44, True, (0, 0, 0, 200))
            _tri(d, 104 + k * 46, 84, 44, True)
        t((214, 78), "REW")
    else:
        _tri(d, 108 + 4, 84 + 4, 44, False, (0, 0, 0, 200))
        _tri(d, 108, 84, 44, False)
        t((176, 78), "PLAY")
    t((W - 420, 78), counter, f2)
    t((104, H - 180), date, f2)
    t((104, H - 126), day, f2)
    t((W - 360, H - 126), "SP  VHS", f2)
    return np.asarray(im).astype(np.float32)


def _vhs(frame, rng, strength=1.0):
    """Tape look: red/blue channel offset, lowered contrast, scanlines, shifted bright tracking bands, a noise bar near the bottom."""
    f = frame.astype(np.float32)
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    f = np.dstack([np.roll(r, 5, axis=1), g, np.roll(b, -5, axis=1)])
    f = (f - 128) * 0.92 + 128 + 6
    f[::3] *= 0.86
    for _ in range(int(2 * strength) + 1):
        y = rng.randint(0, H - 60)
        hgt = rng.randint(8, 46)
        f[y:y + hgt] = np.roll(f[y:y + hgt], rng.randint(-60, 60), axis=1)
        f[y:y + hgt] += rng.randint(20, 70)
    yb = rng.randint(H - 150, H - 45)          # keep the 40-row bar fully inside the frame
    noise = np.random.randint(0, 255, (40, W, 1)).astype(np.float32)
    f[yb:yb + 40] = f[yb:yb + 40] * 0.4 + noise * 0.6
    return np.clip(f, 0, 255)


def _tape_audio(n_frames, t_play):
    """Synthesised rewind sound (whirr + rising squeal + chirp), silence after t_play except a mechanical click.

    Used because the stock-library tape effect could not be downloaded on the user's plan. It has never been
    auditioned by a person: tell the user it is synthetic and unheard."""
    sr = 48000
    n = int(n_frames / FPS * sr)
    t = np.arange(n) / sr
    rs = np.random.RandomState(3)
    whirr = np.convolve(rs.randn(n), np.ones(24) / 24, "same") * (0.6 + 0.4 * np.sin(2 * np.pi * 31 * t))
    sq = np.sin(2 * np.pi * (900 * t + 220 * np.sin(2 * np.pi * 7 * t) + 300 * t * t / max(t[-1], 1))) * 0.18
    chirp = np.sin(2 * np.pi * np.cumsum(1800 + 1400 * np.sin(2 * np.pi * 13 * t)) / sr) * 0.10
    a = (whirr * 0.5 + sq + chirp) * np.where(t < t_play, 1.0, 0.0) * np.minimum(1, t / 0.15)
    ck = int(t_play * sr)
    m = max(0, min(4000, n - ck))
    a[ck:ck + m] += (np.exp(-np.arange(4000) / 300.0) * np.sin(2 * np.pi * 180 * np.arange(4000) / sr) * 2.5)[:m]
    return np.clip(a * 0.22, -1, 1), sr


def rewind(s, dst, HD=None):
    """VHS rewind intro. s: frames, clips = list of dict(file, i, date, day, lut) in REVERSE story order
    (last day first, ending with the very first clip of the story, which then plays forward as PLAY).

    Layout: HD head frames, then each clip for `per` frames playing backwards at 2.6x with a burst of static at
    each change, then the PLAY hold (clean picture, OSD fades out), then HD tail frames."""
    HD = _c["HD"] if HD is None else HD
    rng = random.Random(7)
    clips = s["clips"]
    per = (s["frames"] - 22) // len(clips)       # frames per rewound clip
    tail = s["frames"] - per * len(clips)        # frames of the PLAY hold (about 22)
    total = per * len(clips)
    audio, sr = _tape_audio(HD + s["frames"] + HD, (HD + total) / FPS)
    wav = dst[:-4] + ".wav"
    with wave.open(wav, "wb") as wv:
        wv.setnchannels(2)
        wv.setsampwidth(2)
        wv.setframerate(sr)
        wv.writeframes((np.repeat(audio[:, None], 2, 1) * 32767).astype(np.int16).tobytes())
    enc = encoder(dst, ["-i", wav])
    k = 0
    for ci, c in enumerate(clips):
        src_n = int(per * 2.6)
        want = set(np.linspace(0, src_n - 1, per).astype(int).tolist())
        keep = [f for j, f in enumerate(iter_frames(c["file"], c["i"], src_n, lut=c.get("lut", False))) if j in want]
        keep = (keep + [keep[-1]] * per)[:per][::-1]
        for j, fr in enumerate(keep):
            f = _vhs(fr, rng, 1.0 if j > 1 else 3.0)
            if j < 2:
                f = f * 0.5 + np.random.randint(0, 255, (H, W, 1)) * 0.5
            mm, ss_ = divmod(int((total - k) * 2.6 / FPS * 60), 60)
            o = _osd("rew", c["date"], c["day"], f"-{mm // 60:01d}:{mm % 60:02d}:{ss_:02d}")
            a = o[..., 3:4] / 255
            out = np.clip(f * (1 - a) + o[..., :3] * a, 0, 255).astype(np.uint8)
            if k == 0:
                for _ in range(HD):
                    enc.stdin.write(out.tobytes())     # head handle = first frame held
            enc.stdin.write(out.tobytes())
            k += 1
    c = clips[-1]
    o = _osd("play", c["date"], c["day"], "0:00:00")
    for j, fr in enumerate(iter_frames(c["file"], c["i"], tail + HD, lut=c.get("lut", False))):
        f = fr.astype(np.float32)
        if j < 6:
            f = _vhs(f, rng, 2.0)
        a = o[..., 3:4] / 255 * (1.0 if j < tail - 6 else max(0.0, (tail - j) / 6))
        enc.stdin.write(np.clip(f * (1 - a) + o[..., :3] * a, 0, 255).astype(np.uint8).tobytes())
    _finish(enc, dst)
    os.remove(wav)


# ---------------------------------------------------------------- scrapbook collage
# per photo: (centre x, centre y, photo width, photo height, resting rotation in degrees), for a 1920 x 1080 frame
LAYOUT = {
    2: [(520, 440, 760, 540, -3), (1390, 400, 700, 500, 3)],
    3: [(500, 420, 760, 540, -4), (1420, 250, 500, 360, 3), (1330, 610, 500, 360, -2)],
    4: [(350, 270, 480, 345, -4), (930, 250, 480, 345, 3), (1520, 290, 480, 345, -2), (660, 650, 500, 350, 2)],
}
TITLE_AT = {2: (960, 800), 3: (470, 796), 4: (1390, 600)}     # centre of the title label
NOTE_AT = {2: (810, 30), 3: (860, 620), 4: (1250, 690)}       # top-left of the sticky note
SX, SY = W / 1920.0, H / 1080.0


def _polaroid(path, bw, bh):
    import style
    im = ImageOps.fit(style.open_image(path), (bw, bh), Image.LANCZOS, centering=(0.5, 0.42))
    b, pad = 20, 46
    w, h = bw + 2 * b, bh + 2 * b + 6
    c = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", c.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle((pad + 6, pad + 10, pad + w + 14, pad + h + 18), fill=(40, 25, 10, 130))
    c.alpha_composite(sh.filter(ImageFilter.GaussianBlur(10)))
    back = Image.new("RGBA", c.size, (0, 0, 0, 0))                     # kraft card peeking out behind the print
    ImageDraw.Draw(back).rectangle((pad - 12, pad - 12, pad + w + 12, pad + h + 12), fill=(212, 176, 126, 255))
    c.alpha_composite(back.rotate(-1.6, resample=Image.BICUBIC))
    ImageDraw.Draw(c).rectangle((pad, pad, pad + w, pad + h), fill=(252, 250, 244, 255))
    c.paste(im, (pad + b, pad + b))
    tape = Image.new("RGBA", c.size, (0, 0, 0, 0))
    ImageDraw.Draw(tape).rectangle((c.width // 2 - 78, pad - 22, c.width // 2 + 78, pad + 20), fill=(238, 226, 190, 185))
    c.alpha_composite(tape.rotate(2.5, resample=Image.BICUBIC))
    return c


def _torn_strip():
    """Torn cream paper strip across the bottom that carries the caption."""
    rs = np.random.RandomState(11)
    x0, x1, y0, y1 = int(150 * SX), int(1770 * SX), int(872 * SY), int(1042 * SY)
    m = Image.new("L", (W, H), 0)
    top = [(x, y0 + 6 * math.sin(x / 37.0) + rs.randint(-4, 5)) for x in range(x0, x1 + 1, 9)]
    bot = [(x, y1 + 5 * math.sin(x / 29.0) + rs.randint(-4, 5)) for x in range(x1, x0 - 1, -9)]
    ImageDraw.Draw(m).polygon(top + bot, fill=255)
    im = gfx.new()
    sh = Image.new("RGBA", (W, H), (60, 40, 20, 0))
    sh.putalpha(m.point(lambda v: int(v * 0.45)))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)), (3, 6))
    paper = Image.new("RGBA", (W, H), (252, 248, 236, 244))
    paper.putalpha(m.point(lambda v: int(v * 0.96)))
    im.alpha_composite(paper)
    return im


def _paper_background(seed):
    """Plain kraft-and-cream paper background, used only when no illustrated scrap_bg<n>.png exists."""
    rs = np.random.RandomState(seed)
    base = np.full((H, W, 3), (232, 214, 182), np.float32) + rs.randn(H, W, 1) * 5
    y, x = np.mgrid[0:H, 0:W]
    base *= (1 - 0.18 * (((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2) / 2)[..., None]
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(im)
    d.polygon([(0, 0), (int(W * 0.34), 0), (int(W * 0.26), int(H * 0.2)), (0, int(H * 0.3))], fill=(206, 176, 132, 255))
    d.polygon([(W, H), (int(W * 0.7), H), (int(W * 0.78), int(H * 0.82)), (W, int(H * 0.72))], fill=(206, 176, 132, 255))
    return im.filter(ImageFilter.GaussianBlur(1.2))


def collage(s, dst, HD=None):
    """Scrapbook slide. s: frames, files (2-4 photo paths), title=(en, lang2), note=(line1, line2), cap=(en, lang2), bg (1, 2, ...).

    The first photo is already in place from frame 0 so the incoming transition has something to show; the others
    drop in 9 frames apart (scale 1.28 -> 1, with a little rotation), then the title label and sticky note fade in.
    The caption strip is part of the background."""
    HD = _c["HD"] if HD is None else HD
    files = s["files"]
    if len(files) not in LAYOUT:
        raise ValueError(f"collage needs 2, 3 or 4 photos, got {len(files)}")
    n = HD + s["frames"] + HD
    bgp = os.path.join(_c["mg"], f"scrap_bg{s.get('bg', 1)}.png")
    bg = (Image.open(bgp).convert("RGB").resize((W, H), Image.LANCZOS).convert("RGBA") if os.path.exists(bgp)
          else _paper_background(int(s.get("bg", 1))))
    bg.alpha_composite(_torn_strip())
    en, l2 = s["cap"]
    maxw = int(1540 * SX)
    if l2:
        gfx.text(bg, (W // 2, int(927 * SY)), l2, gfx.fit(gfx.ZH, 44, l2, maxw), fill=gfx.INK, shadow=0, anchor="mm")
        gfx.text(bg, (W // 2, int(989 * SY)), en, gfx.fit(gfx.SERIF_I, 33, en, maxw, 1), fill=(96, 70, 44, 255), shadow=0, anchor="mm")
    else:
        gfx.text(bg, (W // 2, int(957 * SY)), en, gfx.fit(gfx.SERIF_I, 44, en, maxw, 1), fill=gfx.INK, shadow=0, anchor="mm")
    lay = [(int(l[0] * SX), int(l[1] * SY), int(l[2] * SX), int(l[3] * SY), l[4]) for l in LAYOUT[len(files)]]
    # title: a paper label (script English + calligraphy second language). Plain lettering straight on the busy
    # background was illegible in the first test render, hence the label.
    t_en, t_l2 = s["title"]
    f_en, f_l2 = ft(gfx.SCRIPT_B, 54), ft(gfx.ZH_K, 46)
    while gfx.tw(t_en, f_en) + gfx.tw(t_l2, f_l2) > 640 and f_en.size > 20:
        f_en, f_l2 = ft(gfx.SCRIPT_B, f_en.size - 3), ft(gfx.ZH_K, f_l2.size - 2)
    w_en, w_l2 = gfx.tw(t_en, f_en), gfx.tw(t_l2, f_l2)
    lw, lh = int(w_en + w_l2 + (96 if t_l2 else 60)), 104
    lab = Image.new("RGBA", (lw + 60, lh + 60), (0, 0, 0, 0))
    shl = Image.new("RGBA", lab.size, (0, 0, 0, 0))
    ImageDraw.Draw(shl).rounded_rectangle((34, 38, 34 + lw, 38 + lh), 10, fill=(40, 25, 10, 110))
    lab.alpha_composite(shl.filter(ImageFilter.GaussianBlur(6)))
    dl = ImageDraw.Draw(lab)
    dl.rounded_rectangle((30, 30, 30 + lw, 30 + lh), 10, fill=(252, 248, 236, 240), outline=(212, 176, 126, 255), width=3)
    dl.text((60, 30 + lh / 2 - 6), t_en, font=f_en, fill=gfx.INK, anchor="lm")
    if t_l2:
        dl.text((60 + w_en + 36, 30 + lh / 2), t_l2, font=f_l2, fill=(120, 72, 30, 255), anchor="lm")
    lab = lab.rotate(-2, resample=Image.BICUBIC, expand=True)
    tcx, tcy = TITLE_AT[len(files)]
    title = gfx.new()
    title.alpha_composite(lab, (max(0, int(tcx * SX - lab.width / 2)), max(0, int(tcy * SY - lab.height / 2))))
    # sticky note (date / day)
    note = Image.new("RGBA", (300, 170), (0, 0, 0, 0))
    ImageDraw.Draw(note).rectangle((16, 20, 268, 150), fill=(40, 25, 10, 90))
    note = note.filter(ImageFilter.GaussianBlur(5))
    dn = ImageDraw.Draw(note)
    dn.rectangle((10, 10, 262, 140), fill=(255, 232, 128, 255))
    dn.text((136, 52), s["note"][0], font=gfx.fit(gfx.HAND, 50, s["note"][0], 236), fill=(60, 44, 28, 255), anchor="mm")
    dn.text((136, 106), s["note"][1], font=gfx.fit(gfx.HAND, 38, s["note"][1], 236), fill=(120, 72, 30, 255), anchor="mm")
    note = note.rotate(-5, resample=Image.BICUBIC, expand=True)
    nx, ny = int(NOTE_AT[len(files)][0] * SX), int(NOTE_AT[len(files)][1] * SY)
    pols = [_polaroid(f, l[2], l[3]) for f, l in zip(files, lay)]
    enc = encoder(dst, SILENCE)
    for i in range(n):
        fr = bg.copy()
        for k, (p, l) in enumerate(zip(pols, lay)):
            u = 1.0 if k == 0 else (i - (HD + 2 + k * 9)) / 10.0
            if u <= 0:
                continue
            e = gfx.ease(u)
            sc = (1.28 - 0.28 * e) * (1.0 + 0.012 * (i / n))            # drop-in scale, plus a slow drift
            rot = l[4] + (1 - e) * (9 if k % 2 == 0 else -9)
            q = p.resize((int(p.width * sc), int(p.height * sc)), Image.BILINEAR).rotate(rot, resample=Image.BICUBIC, expand=True)
            if e < 1:
                q.putalpha(q.getchannel("A").point(lambda v, e=e: int(v * min(1.0, e * 1.4))))
            gfx.comp(fr, q, l[0] - q.width / 2, l[1] - q.height / 2)
        ut = (i - (HD + 8 + 9 * len(pols))) / 10.0
        if ut > 0:
            a = min(1.0, ut)
            for layer, pos in ((title, (0, 0)), (note, (nx, ny))):
                tl = layer.copy()
                tl.putalpha(tl.getchannel("A").point(lambda v, a=a: int(v * a)))
                gfx.comp(fr, tl, pos[0], pos[1])
        enc.stdin.write(fr.convert("RGB").tobytes())
    _finish(enc, dst)
