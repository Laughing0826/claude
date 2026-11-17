"""style - the photo "look" and robust image opening.

Purpose
  open_image() opens any still the trip produced (JPEG, PNG, HEIC, camera RAW ...) as an upright sRGB picture.
  apply() gives a photo the project's "airy" look: bright open shadows, soft highlights, gentle colour. The
  recipe (LOOK) was copied from the user's own Lightroom edits; project.json "look" overrides single sliders.

Usage (command line)
  python -I -X utf8 style.py [--project <folder>] <outdir> <long_edge_px> @list.txt [--amount 1.0] [--force]
      list.txt holds one photo per line:   <source path>::<id>          (blank lines and # comments are skipped)
      a single photo can be given directly: "<source path>::<id>"  instead of @list.txt
  example:  python -I -X utf8 style.py --project D:\\Trip D:\\Trip\\Photos 3840 @D:\\Trip\\_work\\picks.txt

Usage (import)
  import style
  img = style.open_image(path, fast=False)        # PIL RGB, EXIF orientation applied
  out = style.apply(img, amount=1.0, look=None)   # PIL RGB; amount 0 = original, 1 = full look
  style.look_values(look=None)                    # the recipe actually used (LOOK + project.json "look")
  style.read_list("@list.txt")                    # [(path, tag or None), ...]
  style.in_project(path)                          # absolute path, or ValueError when outside the project folder

Inputs   source photos (read only, never modified); project.json ("look", "utc_offset" through capture_time).
Outputs  <outdir>/<id>_<source stem>.jpg  (JPEG quality 95, long edge <long_edge_px>, never upscaled) and one row
         per id in <project>/_work/styled.csv with the columns id,src,out,when (when = trip-local capture time,
         "" if unknown). Prints one output file name per line, then a summary line "style: styled=N skipped=N
         failed=N csv=<path>". Existing outputs are skipped unless --force. Exit code 1 if any photo failed.

Formats  Pillow formats directly. HEIC/HEIF: pillow_heif if installed, else ffmpeg. RAW (arw, dng, nef, cr2 ...):
         rawpy if installed, else the largest JPEG preview embedded in the file (fast=True prefers the preview,
         which is what contact sheets want).
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

import csv
import io
import re
import struct
import subprocess

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 400_000_000        # stitched panoramas are bigger than Pillow's default safety limit

# The default recipe, Lightroom-style slider values (-100..100). Do not "improve" these numbers: they are the
# user's own edit. A project changes single values with  "look": {"shadows": 60}  in project.json.
LOOK = {"exposure": 0, "temp": 0, "tint": 15, "highlights": -70, "shadows": 85, "whites": 25, "dehaze": 8, "vibrance": 15}

RAW_EXT = (".arw", ".dng", ".nef", ".nrw", ".cr2", ".cr3", ".orf", ".rw2", ".raf", ".pef", ".srw", ".sr2", ".srf",
           ".3fr", ".iiq", ".erf", ".kdc", ".dcr", ".mrw", ".x3f")
HEIF_EXT = (".heic", ".heif", ".hif", ".avif")
CSV_COLS = ["id", "src", "out", "when"]

# How strongly a slider at 100 acts. Tuned by eye so that LOOK at amount 1.0 matches the Lightroom result.
_KS = 1.15      # shadows: gain (1 + _KS) on the darkest tones
_KH = 0.40      # highlights: 0.25 * _KH is taken off the bright tones
_KW = 0.32      # whites: stretch of the very top
_KD = 0.30      # dehaze: black point
_LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)
_EPS = 0.003    # tone mask: luminance variance that counts as an edge. Larger keeps more local contrast but starts to glow at edges
_LOW = 384      # long edge of the low-resolution luminance map the tone mask is computed on
_STRIP = 2_000_000   # pixels processed at a time (keeps memory flat for 60 megapixel files)


# ---------------------------------------------------------------- small shared helpers
def in_project(path):
    """Absolute form of path. Raises ValueError when it is outside the project folder (scripts write nowhere else)."""
    base = os.path.realpath(vk.load()["base"])
    p = os.path.realpath(os.path.abspath(path))
    try:
        inside = os.path.normcase(os.path.commonpath([base, p])) == os.path.normcase(base)
    except ValueError:                      # different drives on Windows
        inside = False
    if not inside:
        raise ValueError(f"output path {p} is outside the project folder {base}; write below the project, for example {vk.load()['work']}")
    return p


def read_list(arg):
    """'@list.txt' (the @ is optional) -> [(path, tag), ...]; tag is None for a line without '::'.

    The split is on the LAST '::' because Windows paths contain ':'. PowerShell's Set-Content / Out-File write a
    BOM or UTF-16, so both are accepted. A relative path that does not exist is also tried next to the list file."""
    p = arg[1:] if arg.startswith("@") else arg
    if not os.path.isfile(p):
        raise FileNotFoundError(f"list file not found: {p}")
    with open(p, "rb") as f:
        raw = f.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("mbcs" if os.name == "nt" else "latin-1")
    here, out = os.path.dirname(os.path.abspath(p)), []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path, sep, tag = line.rpartition("::")
        if not sep:
            path, tag = line, None
        path = path.strip().strip('"')
        if not os.path.isabs(path) and not os.path.exists(path) and os.path.exists(os.path.join(here, path)):
            path = os.path.join(here, path)
        out.append((path, tag.strip() if tag is not None else None))
    return out


# ---------------------------------------------------------------- opening images
_ORIENT = {2: Image.FLIP_LEFT_RIGHT, 3: Image.ROTATE_180, 4: Image.FLIP_TOP_BOTTOM, 5: Image.TRANSPOSE,
           6: Image.ROTATE_270, 7: Image.TRANSVERSE, 8: Image.ROTATE_90}
_MARKER = re.compile(rb"\xff[^\x00\xd0-\xd7\xff]")     # the next real marker inside JPEG entropy-coded data


def _to_rgb(img):
    """Any Pillow mode -> 8-bit RGB in sRGB. Transparency is flattened onto white."""
    if img.mode in ("I;16", "I;16L", "I;16B", "I", "F"):            # 16-bit / float greyscale: scale, do not clip
        a = np.asarray(img, dtype=np.float32)
        top = float(a.max()) if a.size else 1.0
        full = 65535.0 if top > 255 else 255.0 if top > 1.0 else 1.0
        img = Image.fromarray(np.clip(a * (255.0 / full), 0, 255).astype(np.uint8))
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, 255)), img)
    icc = img.info.get("icc_profile")
    if icc and img.mode in ("RGB", "CMYK"):
        # Phones save Display P3 and some cameras Adobe RGB. Read as sRGB those look dull, so convert once here.
        try:
            from PIL import ImageCms
            prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if "srgb" not in (ImageCms.getProfileDescription(prof) or "").lower():
                img = ImageCms.profileToProfile(img, prof, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:                                           # broken or exotic profile: keep the pixels as they are
            pass
    return img if img.mode == "RGB" else img.convert("RGB")


def _tiff_jpegs(buf):
    """([(offset, length), ...], orientation) of the JPEG previews a TIFF-based RAW file points to.

    Walks IFD0, the chain of following IFDs and all SubIFDs (tag 0x014a). A preview is announced either by
    JPEGInterchangeFormat/-Length (0x0201/0x0202), by a single JPEG-compressed strip (CR2, DNG) or by
    Panasonic's JpgFromRaw (0x002e)."""
    if len(buf) < 16 or buf[:2] not in (b"II", b"MM"):
        return [], 1
    e = "<" if buf[:2] == b"II" else ">"
    first = struct.unpack_from(e + "I", buf, 4)[0]
    todo, seen, found, orient = [first], set(), [], 1
    while todo and len(seen) < 64:
        off = todo.pop(0)
        if off in seen or off < 8 or off + 2 > len(buf):
            continue
        seen.add(off)
        n = struct.unpack_from(e + "H", buf, off)[0]
        if off + 2 + 12 * n > len(buf):
            continue
        tags = {}
        for i in range(n):
            p = off + 2 + 12 * i
            tag, typ, cnt = struct.unpack_from(e + "HHI", buf, p)
            size = {1: 1, 3: 2, 4: 4, 7: 1, 13: 4}.get(typ)
            if tag not in (0x002E, 0x0103, 0x0111, 0x0112, 0x0117, 0x014A, 0x0201, 0x0202) or not size or not cnt:
                continue
            vp = p + 8 if size * cnt <= 4 else struct.unpack_from(e + "I", buf, p + 8)[0]
            if tag == 0x002E:
                tags[tag] = [vp, cnt]                               # the value is the JPEG itself
            elif vp + size * min(cnt, 32) <= len(buf):
                code = e + {1: "B", 2: "H", 4: "I"}[size]
                tags[tag] = [struct.unpack_from(code, buf, vp + size * j)[0] for j in range(min(cnt, 32))]
        if 0x0201 in tags and 0x0202 in tags:
            found.append((tags[0x0201][0], tags[0x0202][0]))
        if tags.get(0x0103, [0])[0] in (6, 7) and len(tags.get(0x0111, [])) == 1 and 0x0117 in tags:
            found.append((tags[0x0111][0], tags[0x0117][0]))
        if 0x002E in tags:
            found.append(tuple(tags[0x002E]))
        if off == first and tags.get(0x0112, [1])[0] in _ORIENT:
            orient = tags[0x0112][0]
        todo += tags.get(0x014A, [])
        if off + 6 + 12 * n <= len(buf):
            todo.append(struct.unpack_from(e + "I", buf, off + 2 + 12 * n)[0])
    return found, orient


def _jpeg_end(buf, s):
    """End offset of the JPEG stream that starts at s, or None if the bytes there are not a JPEG.

    Walks the marker segments instead of searching for FFD9, because a preview carries its own thumbnail (a
    complete JPEG inside its EXIF block) whose FFD9 would cut the stream short."""
    n, i = len(buf), s + 2
    while i + 2 <= n and buf[i] == 0xFF:
        m = buf[i + 1]
        if m == 0xD9:
            return i + 2
        if m == 0xFF:
            i += 1
        elif 0xD0 <= m <= 0xD7 or m == 0x01:
            i += 2
        elif m < 0xC0 or i + 4 > n:
            return None
        else:
            i += 2 + ((buf[i + 2] << 8) | buf[i + 3])
            if m == 0xDA:                                           # start of scan: skip the compressed data
                k = _MARKER.search(buf, i)
                if not k:
                    return None
                i = k.start()
    return None


def _scan_jpegs(buf):
    """(offset, length) of every complete top-level JPEG stream in buf (last resort for unknown containers)."""
    found, pos = [], 0
    while True:
        s = buf.find(b"\xff\xd8\xff", pos)
        if s < 0:
            return found
        end = _jpeg_end(buf, s)
        if end:
            found.append((s, end - s))
        pos = end or s + 3


def _largest_jpeg(buf, spans):
    """The decodable JPEG with the most pixels among spans, as a loaded PIL image, or None."""
    sized = []
    for off, ln in set(spans):
        if ln < 64 or off < 0 or off + ln > len(buf) or buf[off:off + 2] != b"\xff\xd8":
            continue
        try:
            w, h = Image.open(io.BytesIO(buf[off:off + ln])).size
            sized.append((w * h, off, ln))
        except Exception:
            pass
    for _, off, ln in sorted(sized, reverse=True):
        try:                                                        # the RAW data itself can be a lossless JPEG: skip what cannot be decoded
            im = Image.open(io.BytesIO(buf[off:off + ln]))
            im.load()
            return im
        except Exception:
            pass
    return None


def _raw_preview(path):
    """Largest embedded JPEG preview of a RAW file, upright, or None."""
    with open(path, "rb") as f:
        buf = f.read()
    spans, orient = _tiff_jpegs(buf)
    im = _largest_jpeg(buf, spans)
    if im is None or max(im.size) < 1000:                           # nothing or only a thumbnail in the IFDs: search the whole file
        big = _largest_jpeg(buf, _scan_jpegs(buf))
        if big is not None and (im is None or big.size[0] * big.size[1] > im.size[0] * im.size[1]):
            im = big
    if im is None:
        return None
    own = im.getexif().get(0x0112, 1)
    # Previews are stored unrotated; the RAW's own Orientation applies unless the preview states one itself.
    im = ImageOps.exif_transpose(im) if own in _ORIENT else (im.transpose(_ORIENT[orient]) if orient in _ORIENT else im)
    return _to_rgb(im)


def _open_raw(path, fast):
    rawpy = None
    try:
        import rawpy
    except ImportError:
        pass
    if fast or rawpy is None:
        im = _raw_preview(path)
        if im is not None:
            return im
    if rawpy is not None:
        try:
            with open(path, "rb") as f, rawpy.imread(f) as raw:    # a file object: LibRaw mishandles non-ASCII Windows paths
                return Image.fromarray(raw.postprocess(use_camera_wb=True, output_bps=8)).convert("RGB")
        except Exception as ex:
            im = None if fast else _raw_preview(path)
            if im is not None:
                return im
            raise ValueError(f"cannot read RAW file {path}: rawpy failed ({ex}) and it holds no JPEG preview")
    raise ValueError(f"cannot read RAW file {path}: it holds no JPEG preview. Install rawpy (pip install rawpy) or export a JPEG.")


def _heif_long_edge(path):
    """Long edge of the main picture of a HEIF file, from its 'ispe' boxes (0 if unknown)."""
    with open(path, "rb") as f:
        head = f.read(4 << 20)
    best, i = 0, head.find(b"ispe")
    while i >= 0 and i + 16 <= len(head):
        w, h = struct.unpack_from(">II", head, i + 8)
        if 0 < w <= 65536 and 0 < h <= 65536 and w * h > best:
            best, edge = w * h, max(w, h)
        i = head.find(b"ispe", i + 4)
    return edge if best else 0


def _ffmpeg_image(path, why):
    """Decode a still with ffmpeg (formats Pillow cannot read). The picture comes back through a pipe: no temp file."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-frames:v", "1", "-f", "image2pipe",
                            "-c:v", "png", "-pix_fmt", "rgb24", "pipe:1"], capture_output=True)
    except FileNotFoundError:
        raise ValueError(f"cannot open image {path}: {why}; ffmpeg is not installed either")
    try:
        im = Image.open(io.BytesIO(r.stdout))
        im.load()
    except Exception:
        tail = (r.stderr.decode("utf-8", "replace").strip().splitlines() or ["no picture decoded"])[0][-160:]
        hint = " Install pillow-heif (pip install pillow-heif)." if path.lower().endswith(HEIF_EXT) else ""
        raise ValueError(f"cannot open image {path}: {why}; ffmpeg cannot either ({tail}).{hint}")
    if path.lower().endswith(HEIF_EXT):
        # Phone HEIC is a grid of tiles. ffmpeg before 7.1 returns a single tile or the thumbnail: refuse that.
        want = _heif_long_edge(path)
        if want and max(im.size) < 0.9 * want:
            raise ValueError(f"cannot open image {path}: this ffmpeg decoded only {im.size[0]}x{im.size[1]} of a {want}px HEIC "
                             f"(tiled HEIC needs ffmpeg 7.1+). Install pillow-heif (pip install pillow-heif).")
    return im.convert("RGB")


def open_image(path, fast=False):
    """Open a still as an upright 8-bit sRGB PIL image (EXIF orientation applied). The file is only read.

    fast=True is for thumbnails: a RAW file then gives its embedded preview even when rawpy is installed.
    Raises FileNotFoundError for a missing file and ValueError (with the reason) for an unreadable one."""
    path = os.fspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"image not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXT:
        return _open_raw(path, fast)
    if ext in HEIF_EXT:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            pass
    try:
        with Image.open(path) as im:
            im.load()
            return _to_rgb(ImageOps.exif_transpose(im))
    except Exception as ex:
        why = "Pillow does not know this format" if isinstance(ex, UnidentifiedImageError) else f"Pillow cannot read it ({str(ex)[:100]})"
    with open(path, "rb") as f:
        tiff = f.read(2) in (b"II", b"MM")
    im = _raw_preview(path) if tiff else None                       # a RAW file with an extension not in RAW_EXT
    return im if im is not None else _ffmpeg_image(path, why)


# ---------------------------------------------------------------- the look
def look_values(look=None):
    """The recipe as a complete dict. look=None: LOOK with project.json "look" on top. A dict: LOOK with that
    dict on top (project.json is then ignored). Unknown keys are an error, values are limited to -100..100."""
    over = (vk.load().get("look") or {}) if look is None else look
    bad = sorted(set(over) - set(LOOK))
    if bad:
        raise ValueError(f"unknown look setting(s) {bad}; valid names: {sorted(LOOK)}")
    vals = dict(LOOK)
    vals.update(over)
    return {k: min(max(float(v), -100.0), 100.0) for k, v in vals.items()}


def _channel_gains(L):
    """(wb, ex): temp and tint as one multiplier per channel (neutral grey keeps its brightness), and the
    exposure multiplier (100 = +2 stops)."""
    t, m = L["temp"] / 100.0, L["tint"] / 100.0
    g = np.array([1 + 0.18 * t + 0.045 * m, 1 - 0.09 * m, 1 - 0.18 * t + 0.045 * m], np.float32)
    return g / float(g @ _LUMA), float(2.0 ** (L["exposure"] / 50.0 / 2.2))


def _box(a, r):
    """Mean over a (2r+1)^2 window, edges replicated. Summed-area table, so the cost does not grow with r."""
    k = 2 * r + 1
    c = np.cumsum(np.cumsum(np.pad(a.astype(np.float64), r, mode="edge"), 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return ((c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)).astype(np.float32)


def _base_coeffs(img, ex):
    """Guided-filter coefficients (a, b) of the luminance at low resolution: base = a * luminance + b.

    The base is the luminance with texture smoothed away but big edges kept. Shadows and highlights are
    decided on the base, so a lifted shadow keeps its local contrast (a plain curve turns it flat and grey)
    and no glow appears along a dark animal against a bright sky (a blurred mask would give that halo)."""
    w, h = img.size
    k = min(1.0, _LOW / max(w, h))
    lw, lh = max(2, round(w * k)), max(2, round(h * k))
    y = (np.asarray(img.resize((lw, lh), Image.BOX), np.float32) @ _LUMA) * (ex / 255.0)
    r = max(1, round(0.035 * max(lw, lh)))
    m = _box(y, r)
    v = np.maximum(_box(y * y, r) - m * m, 0.0)
    a = v / (v + _EPS)
    return _box(a, r), _box(m * (1.0 - a), r)


def apply(img, amount=1.0, look=None):
    """Return img with the look applied. amount blends from the original (0.0) to the full look (1.0).

    look=None uses LOOK plus the project.json overrides; a dict overrides LOOK directly (see look_values).
    Typical amounts: 1.0 for camera photos, 0.45 for phone photos (already processed by the phone), 0.15 for
    dusk and 0 for night shots, which the lifted shadows would turn grey."""
    L = look_values(look)
    amount = min(max(float(amount), 0.0), 1.0)
    img = img if img.mode == "RGB" else img.convert("RGB")
    if amount == 0.0 or not any(L.values()):
        return img.copy()
    src = np.asarray(img)
    h, w = src.shape[:2]
    wb, ex = _channel_gains(L)
    sh, hl, wh, dz, vib = (L[k] / 100.0 for k in ("shadows", "highlights", "whites", "dehaze", "vibrance"))
    a_lo, b_lo = _base_coeffs(img, ex)
    lh, lw = a_lo.shape
    a_im, b_im = Image.fromarray(a_lo), Image.fromarray(b_lo)
    out = np.empty_like(src)
    step = max(8, _STRIP // w)
    for y0 in range(0, h, step):
        y1 = min(h, y0 + step)
        box = (0, y0 * lh / h, lw, y1 * lh / h)                     # the kernel reads past the box, so strips join seamlessly
        a = np.asarray(a_im.resize((w, y1 - y0), Image.BICUBIC, box=box))
        b = np.asarray(b_im.resize((w, y1 - y0), Image.BICUBIC, box=box))
        orig = src[y0:y1].astype(np.float32) * (1 / 255.0)
        y = orig @ _LUMA
        # temp/tint fade out towards white: a blown sky stays white instead of turning pink (as it does on a RAW file)
        t = np.clip((y - 0.7) * (1 / 0.3), 0.0, 1.0)
        x = orig * (1.0 + (wb - 1.0) * (1.0 - t * t)[..., None])
        if ex != 1.0:
            x *= ex
            y *= ex
        base = np.clip(a * y + b, 0.0, 1.5)
        # shadows: a gain that is largest at black and fades out at 0.65. Black stays black, the curve stays monotonic.
        u = np.clip(1.0 - base * (1 / 0.65), 0.0, 1.0)
        u *= u
        g = 1.0 + _KS * sh * u if sh >= 0 else 1.0 / (1.0 - _KS * sh * u)
        # highlights: take a flat step off everything above ~0.8 so bright skies get tone back while white stays near white
        v = base * g
        t = np.clip((v - 0.4) * (1 / 0.6), 0.0, 1.0)
        g *= 1.0 + _KH * hl * t * t * (1.0 - 0.75 * t) / np.maximum(v, 0.4)
        if wh:                                                      # whites: stretch the very top (4th power keeps it out of the midtones)
            p = np.minimum(y * g, 1.0)
            p *= p
            g *= 1.0 + _KW * wh * p * p
        x *= g[..., None]
        if dz:                                                      # dehaze: move the black point, which also adds a little contrast
            bp = _KD * dz
            x -= bp
            x *= 1.0 / (1.0 - bp)
        hot = x > 0.92                                              # soft shoulder: values pushed past white roll off instead of clipping
        if hot.any():
            x[hot] = 0.92 + 0.08 * np.tanh((x[hot] - 0.92) * 12.5)
        np.clip(x, 0.0, 1.0, out=x)
        if vib or dz:
            mx, mn = x.max(axis=2), x.min(axis=2)
            sat = (mx - mn) / np.maximum(mx, 1e-3)
            # skin-ish hues (red > green > blue, 10-40 degrees) get only part of the boost so faces do not turn orange
            hue = (x[..., 1] - x[..., 2]) / np.maximum(x[..., 0] - x[..., 2], 1e-3)
            skin = np.clip(1.0 - np.abs(hue - 0.4) * (1 / 0.35), 0.0, 1.0) * (x[..., 0] >= x[..., 1])
            f = 1.0 + vib * (1.0 - sat) * (1.0 - 0.5 * skin) + 0.4 * dz
            y2 = (x @ _LUMA)[..., None]
            x = np.clip(y2 + (x - y2) * np.maximum(f, 0.0)[..., None], 0.0, 1.0)
        if amount < 1.0:
            x = orig + (x - orig) * amount
        out[y0:y1] = (x * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(out)


# ---------------------------------------------------------------- command line
def _when(path):
    """Trip-local capture time "YYYY-MM-DD HH:MM:SS", or "" when capture_time.py is absent or finds nothing."""
    try:
        import capture_time
    except ImportError:
        return ""
    try:
        r = capture_time.capture_local(path)
    except Exception:
        return ""
    r = r[0] if isinstance(r, (tuple, list)) else r
    return r.strftime("%Y-%m-%d %H:%M:%S") if hasattr(r, "strftime") else str(r or "")


def _update_csv(path, rows):
    """Insert or replace rows (keyed by id) in styled.csv, keeping everything else that is already there."""
    cols, old = list(CSV_COLS), {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8-sig") as f:
            rd = csv.DictReader(f)
            cols += [c for c in (rd.fieldnames or []) if c not in cols]
            for r in rd:
                if r.get("id"):
                    old[r["id"]] = r
    for r in rows:
        old[r["id"]] = dict(old.get(r["id"], {}), **r)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=cols, restval="", extrasaction="ignore")
        wr.writeheader()
        wr.writerows(old.values())
    os.replace(tmp, path)


def style_one(src, dst, long_edge, amount=1.0):
    """open -> shrink so the long edge is long_edge (never enlarge) -> look -> JPEG quality 95 at dst."""
    img = open_image(src)
    k = long_edge / max(img.size)
    if k < 1.0:                                                     # shrink first: the look then runs on far fewer pixels
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
    img = apply(img, amount)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    img.save(tmp, "JPEG", quality=95, subsampling=0, optimize=True)  # temp name first: a killed run leaves no half file
    os.replace(tmp, dst)
    return dst


def main():
    import argparse
    cfg = vk.load()
    ap = argparse.ArgumentParser(description="Render photos in the project's look.", usage="style.py [--project P] <outdir> <long_edge_px> @list.txt [--amount 1.0] [--force]")
    ap.add_argument("outdir")
    ap.add_argument("long_edge", type=int)
    ap.add_argument("items", nargs="+", help="@list.txt with '<source path>::<id>' lines, or such items directly")
    ap.add_argument("--amount", type=float, default=1.0)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    try:
        if a.long_edge < 16:
            raise ValueError(f"long_edge_px must be a pixel size such as 3840, got {a.long_edge}")
        outdir = in_project(a.outdir)
        look_values()                                               # a typo in project.json "look" stops the run here, not per photo
        todo = []
        for it in a.items:
            todo += read_list(it) if it.startswith("@") or "::" not in it else [tuple(s.strip().strip('"') for s in it.rsplit("::", 1))]
        bad = [p for p, i in todo if not i]
        if bad or not todo:
            raise ValueError(f"every line must be '<source path>::<id>'; no id for: {bad[:3]}" if bad else "the list is empty")
    except (ValueError, OSError) as ex:
        sys.exit(f"style: ERROR {ex}")
    rows, done, skipped, failed = [], 0, 0, 0
    for src, pid in todo:
        src = os.path.abspath(src)
        name = re.sub(r'[\\/:*?"<>|\s]+', "_", pid) + "_" + os.path.splitext(os.path.basename(src))[0] + ".jpg"
        dst = os.path.join(outdir, name)
        try:
            if os.path.normcase(dst) == os.path.normcase(src):
                raise ValueError("output would overwrite the source")
            if os.path.exists(dst) and not a.force:
                if not os.path.isfile(src):
                    raise FileNotFoundError(f"image not found: {src}")
                skipped += 1
            else:
                style_one(src, dst, a.long_edge, a.amount)
                done += 1
            rows.append({"id": pid, "src": src, "out": dst, "when": _when(src)})
            print(name, flush=True)
        except Exception as ex:
            failed += 1
            print(f"style: ERROR {pid}: {ex}", file=sys.stderr, flush=True)
    csv_path = os.path.join(cfg["work"], "styled.csv")
    if rows:
        os.makedirs(cfg["work"], exist_ok=True)
        _update_csv(csv_path, rows)
    print(f"style: styled={done} skipped={skipped} failed={failed} csv={csv_path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
