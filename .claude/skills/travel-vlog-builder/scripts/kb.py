"""kb - pre-render a still photo as a video shot with slow camera motion ("Ken Burns").

Purpose
  DaVinci Resolve ignores short still durations and a transition needs spare frames on both sides of a cut,
  so every photo becomes a real clip with exactly the wanted number of frames and a silent audio track.

Usage (single test from the command line)
  python -I -X utf8 kb.py [--project <folder>] <src> <dst> <nframes> [mv] [amt] [--force]
      mv   in | out | left | right | pano      (default in)
      amt  0..1, amount of the photo look (style.apply) baked in   (default 0 = photo as it is)
  example:  python -I -X utf8 kb.py --project D:\\Trip D:\\Trip\\Photos\\D1-08_AFR02432.jpg D:\\Trip\\_work\\kb_test.mp4 75 left 0.45

Usage (import)
  import kb
  kb.render(src, dst, nframes, mv="in", amt=0.0)   # writes dst, returns dst; always renders (the caller skips existing files)
  z, sx = kb.motion(mv, t)                          # the motion contract below, t = frame_index / (nframes - 1)
  x, y  = kb.place(px, py, mv, t)                   # where a point of the z=1 frame is drawn at time t

Inputs   src: any still style.open_image can read (never modified). project.json: width, height, fps, look.
Outputs  dst: MP4, H.264 (libx264 crf 16, preset medium, yuv420p, BT.709), constant frame rate, exactly nframes
         frames of width x height, plus silent stereo 48 kHz AAC of the same length. Prints one summary line
         "kb: ok dst=... frames=N size=WxH fps=F mv=... amt=... secs=..." (or "kb: skipped ..." if dst exists).

MOTION CONTRACT - overlays drawn by other scripts stay registered with the photo only while these hold:
  z = 1 means the picture exactly covers the frame ("cover" fit, centre crop). With t = frame_index / (nframes - 1)
  a point (px, py) of the z=1 frame is drawn at   x = (px - W/2) * z + W/2 + sx * W ,   y = (py - H/2) * z + H/2
    in     z = 1 + 0.09 * t            sx = 0                      (linear, no easing)
    out    z = 1.09 - 0.09 * t         sx = 0
    left   z = 1.09                    sx = +0.045 - 0.09 * t      (picture moves LEFT across the frame)
    right  z = 1.09                    sx = -0.045 + 0.09 * t      (mirror of left)
    pano   picture wider than 1.3 x the frame shape: z = 1 (frame height filled), the view travels the whole
           width left to right, linear. Any other picture: same as right.
  Portrait pictures (taller than wide) are not cropped: the whole photo stands in the centre, fitted to the frame
  height, over a blurred, slightly darkened, enlarged copy of itself - the treatment vertical phone videos get.
  The motion then applies to that composite.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image, ImageFilter

import style

ZOOM = 0.09                 # CONTRACT: total zoom travel. Overlay code repeats this number, never change it here alone.
MOVES = ("in", "out", "left", "right", "pano")
PANO_ASPECT = 1.3           # "pano" pans only pictures at least this much wider than the frame shape
_SUPER = 1.5                # working picture is kept at up to 1.5x frame resolution, so every frame is a clean downscale


def motion(mv, t):
    """(z, sx) at time t in 0..1: zoom factor and the picture's on-screen shift as a fraction of the frame width.
    For "pano" this is the fallback used for pictures that are not wide (same as "right")."""
    if mv == "in":
        return 1.0 + ZOOM * t, 0.0
    if mv == "out":
        return 1.0 + ZOOM - ZOOM * t, 0.0
    if mv == "left":
        return 1.0 + ZOOM, ZOOM / 2 - ZOOM * t
    if mv in ("right", "pano"):
        return 1.0 + ZOOM, -ZOOM / 2 + ZOOM * t
    raise ValueError(f"unknown motion {mv!r}; use one of {', '.join(MOVES)}")


def place(px, py, mv, t):
    """Where the point (px, py) of the z=1 frame (frame pixels) is drawn at time t. For overlays that must follow the photo."""
    cfg = vk.load()
    z, sx = motion(mv, t)
    return (px - cfg["W"] / 2) * z + cfg["W"] / 2 + sx * cfg["W"], (py - cfg["H"] / 2) * z + cfg["H"] / 2


def _blur_fill(fg, cw, ch):
    """Canvas cw x ch: fg (already ch high) centred on a blurred, darkened, enlarged copy of itself."""
    band = fg.width * ch / cw                                       # the centre band of fg that has the frame's shape
    small = fg.resize((max(2, cw // 8), max(2, ch // 8)), Image.BILINEAR, box=(0, (fg.height - band) / 2, fg.width, (fg.height + band) / 2),
                      reducing_gap=2.0)
    # blurred at 1/8 size (cheap), sigma about 2.6% of the frame height like ffmpeg boxblur=24:4 on the phone videos
    bg = small.filter(ImageFilter.GaussianBlur(0.026 * ch / 8)).resize((cw, ch), Image.BICUBIC)
    bg = bg.point(lambda v: max(0, v - 31))                         # same darkening as eq=brightness=-0.12 there
    bg.paste(fg, ((cw - fg.width) // 2, 0))
    return bg


def _working_picture(src, amt, W, H):
    """The picture the camera moves over: look applied, portrait composed, no larger than _SUPER x the frame."""
    img = style.open_image(src)
    iw, ih = img.size
    if ih > iw:                                                     # portrait: build the blurred-sides composite
        s = min(max(ih / H, 1.0), _SUPER)
        cw, ch = round(W * s), round(H * s)
        fg = img.resize((max(1, round(iw * ch / ih)), ch), Image.LANCZOS)
        return _blur_fill(style.apply(fg, amt) if amt > 0 else fg, cw, ch)
    s = min(iw / W, ih / H)                                         # source pixels per frame pixel at z = 1
    if s > _SUPER:                                                  # shrink once, well filtered, instead of on every frame
        img = img.resize((round(iw * _SUPER / s), round(ih * _SUPER / s)), Image.LANCZOS)
    return style.apply(img, amt) if amt > 0 else img


def render(src, dst, nframes, mv="in", amt=0.0):
    """Render src as a moving shot of exactly nframes frames at dst (see the module docstring). Returns dst."""
    cfg = vk.load()
    W, H, FPS = cfg["W"], cfg["H"], cfg["FPS"]
    nframes, amt = int(nframes), min(max(float(amt), 0.0), 1.0)
    if nframes < 1:
        raise ValueError(f"nframes must be at least 1, got {nframes}")
    if W % 2 or H % 2:
        raise ValueError(f"project width and height must be even for H.264, got {W}x{H}")
    motion(mv, 0.0)                                                 # rejects an unknown motion before any work is done
    if os.path.exists(dst) and os.path.exists(src) and os.path.samefile(src, dst):
        raise ValueError(f"dst is the source file itself: {dst}")
    base = _working_picture(src, amt, W, H)
    bw, bh = base.size
    S = min(bw / W, bh / H)                                         # base pixels per frame pixel at z = 1 (cover fit)
    ox, oy = (bw - W * S) / 2, (bh - H * S) / 2                     # the centre crop that z = 1 shows
    pan = bw / S / W - 1.0 if mv == "pano" and bw / bh > PANO_ASPECT * W / H else None

    def frame(i):
        t = i / max(nframes - 1, 1)
        z, sx = (1.0, pan * (0.5 - t)) if pan is not None else motion(mv, t)
        bx, by = S * W / z, S * H / z                               # size of the view in base pixels
        x0 = ox + S * (W / 2 - (W / 2 + sx * W) / z)
        y0 = oy + S * (H / 2 - H / 2 / z)
        x0, y0 = min(max(x0, 0.0), bw - bx), min(max(y0, 0.0), bh - by)   # rounding must never push the view off the picture
        # resize with a float box = separable bicubic resampling at sub-pixel positions (smooth motion, no 1-px jitter)
        return base.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + bx, y0 + by)).tobytes()

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    tmp = dst + ".part.mp4"                                         # finished file appears under its name only when complete
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "pipe:0",
           "-f", "lavfi", "-t", f"{nframes / FPS:.6f}", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:v", "-map", "1:a",
           # RGB -> YUV with the HD matrix and say so in the file; ffmpeg's default is the SD matrix, which shifts colours in Resolve
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
           "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-frames:v", str(nframes),
           "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-movflags", "+faststart", tmp]
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found on PATH")
    err, got = b"", 0
    try:
        threads = min(4, os.cpu_count() or 2)                       # Pillow releases the GIL while resampling
        with ThreadPoolExecutor(threads) as ex:
            for i0 in range(0, nframes, 2 * threads):               # small batches: frames stay in order, memory stays flat
                for buf in ex.map(frame, range(i0, min(nframes, i0 + 2 * threads))):
                    p.stdin.write(buf)
    except OSError:                                                 # broken pipe: ffmpeg died, its own message is reported below
        pass
    except BaseException:                                           # anything else (Ctrl-C included): do not leave ffmpeg waiting for frames
        p.kill()
        raise
    finally:
        try:
            p.stdin.close()
        except OSError:
            pass
        err = p.stderr.read()
        p.wait()
        if p.returncode == 0 and os.path.exists(tmp):
            got = vk.count_frames(tmp)
        if got != nframes and os.path.exists(tmp):
            os.remove(tmp)
    if got != nframes:
        raise RuntimeError(f"kb.render failed for {src}: ffmpeg exit {p.returncode}, {got} of {nframes} frames. {err.decode('utf-8', 'replace')[-300:]}")
    os.replace(tmp, dst)
    return dst


def main():
    cfg = vk.load()
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    if not 3 <= len(args) <= 5:
        sys.exit("usage: kb.py [--project <folder>] <src> <dst> <nframes> [in|out|left|right|pano] [amt 0..1] [--force]")
    try:
        src, nframes = args[0], int(args[2])
        mv, amt = (args[3] if len(args) > 3 else "in"), (float(args[4]) if len(args) > 4 else 0.0)
        dst = style.in_project(args[1])
        if os.path.exists(dst) and not force:
            print(f"kb: skipped dst={dst} (exists; use --force to render again)")
            return
        t0 = time.time()
        render(src, dst, nframes, mv, amt)
    except Exception as ex:
        sys.exit(f"kb: ERROR {ex}")
    print(f"kb: ok dst={dst} frames={nframes} size={cfg['W']}x{cfg['H']} fps={cfg['FPS']} mv={mv} amt={amt:g} secs={time.time() - t0:.1f}")


if __name__ == "__main__":
    main()
