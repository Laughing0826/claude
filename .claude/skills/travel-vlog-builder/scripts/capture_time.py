"""capture_time - the TRUE capture time of a photo or video, in the trip's local time zone.

Why this exists: folder names and file modification times lie (copies, cloud sync, re-exports), and a camera
clock is often still on the HOME time zone. Shots placed by those end up on the wrong day. The time embedded in
the file, converted with the offset stored next to it, is the only reliable source.

Usage (import from another script in this folder):
    import capture_time as ct
    when, src = ct.capture_local(path)                 # ("2026-02-16 09:41:05", "exif"), trip-local
    dt, off   = ct.exif_datetime(path)                 # ("2026:02:16 15:41:05", "+08:00") raw EXIF, ("", "") if none
    aware, src = ct.video_datetime(path, sidecar_root) # (timezone-aware datetime or None, "xml" | "qt-local" | "qt-utc" | "none")
    w, h      = ct.photo_size(path)                    # displayed size, (0, 0) if unknown
    tz        = ct.parse_offset("+08:00")              # datetime.timezone

Usage (self-check, writes nothing):
    python -I -X utf8 capture_time.py --selftest                                   # parser check, no project needed
    python -I -X utf8 capture_time.py --project <folder> [--sidecars <folder>] <file> [<file> ...]

Inputs:  media files (read only). project.json keys: "utc_offset" (the trip's zone, e.g. "+02:00") and the
         optional "camera_utc_offset" (zone the camera clock was set to, used only when a photo stores no offset).
Outputs: none. The time source returned with every time says how far it can be trusted:
    exif          photo: EXIF time + EXIF offset, converted to the trip zone               (reliable)
    exif-assumed  photo: EXIF time without an offset; camera_utc_offset was ASSUMED        (check one by eye)
    xml           clip:  Sony sidecar <clip>M01.XML, CreationDate with offset              (reliable)
    qt-local      video: QuickTime com.apple.quicktime.creationdate with offset (phones)   (reliable)
    qt-utc        video: container creation_time, UTC. Some action cams and drones store local time there (check)
    mtime         file modification time - only when allow_mtime=True was asked for        (unreliable)
    none          nothing embedded; the time is ""
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

import datetime
import json
import re
import struct
import threading

PHOTO_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".arw", ".dng", ".nef", ".cr2", ".cr3", ".raf"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mts", ".avi"}
RAW_EXT = {".arw", ".dng", ".nef", ".cr2", ".cr3", ".raf"}
HEIF_EXT = {".heic", ".heif"}

# sidecar remarks that deserve a human look: path -> text. inventory.py prints them.
notes = {}

_TIFF_MAGIC = (b"II*\x00", b"MM\x00*")
_DATE_TAGS = (0x9003, 0x9004, 0x0132)       # DateTimeOriginal, DateTimeDigitized, IFD0 DateTime (last resort)
_OFFSET_TAGS = (0x9011, 0x9012, 0x9010)     # OffsetTimeOriginal, OffsetTimeDigitized, OffsetTime
_SCAN_FIRST, _SCAN_MAX, _SCAN_TAIL = 256 << 10, 8 << 20, 1 << 20


# ---------------------------------------------------------------- time-zone and text helpers
def parse_offset(text):
    """"+08:00", "-0330", "+2", "Z" -> datetime.timezone. Raises ValueError for anything else."""
    s = str(text).strip().replace("\u2212", "-")        # typographic minus sign
    if s.upper() in ("Z", "UTC", "GMT"):
        return datetime.timezone.utc
    m = re.match(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", s, re.I)
    if not m or int(m.group(2)) > 14 or int(m.group(3) or 0) > 59:
        raise ValueError(f"not a UTC offset: {text!r} (expected something like \"+02:00\")")
    minutes = int(m.group(2)) * 60 + int(m.group(3) or 0)
    return datetime.timezone(datetime.timedelta(minutes=-minutes if m.group(1) == "-" else minutes))


def offset_text(tz):
    """datetime.timezone -> "+08:00"."""
    minutes = int(tz.utcoffset(None).total_seconds() // 60)
    return "%s%02d:%02d" % ("-" if minutes < 0 else "+", abs(minutes) // 60, abs(minutes) % 60)


_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:[.,]\d+)?\s*(Z|[+-]\d{2}:?\d{2}|[+-]\d{2})?")


def parse_iso(text):
    """ISO time stamp -> datetime, timezone-aware when the text carries an offset or Z; None if unparsable.
    (datetime.fromisoformat of Python 3.9 rejects "Z" and "+0200", both of which ffprobe prints.)"""
    m = _ISO.search(str(text))
    if not m:
        return None
    try:
        dt = datetime.datetime(*[int(g) for g in m.groups()[:6]])
        return dt.replace(tzinfo=parse_offset(m.group(7))) if m.group(7) else dt
    except ValueError:
        return None


def _clean_exif_time(text):
    """EXIF date text -> "YYYY:MM:DD HH:MM:SS", or "" for blanks and impossible dates such as 0000:00:00."""
    m = re.match(r"\s*(\d{4})[:\-/.](\d{2})[:\-/.](\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?", text or "")
    if not m:
        return ""
    try:
        return datetime.datetime(*[int(g or 0) for g in m.groups()]).strftime("%Y:%m:%d %H:%M:%S")
    except ValueError:
        return ""


def _clean_offset(text):
    """EXIF offset text -> "+08:00", or "" for blanks ("   :  ") and anything unparsable."""
    try:
        return offset_text(parse_offset((text or "").strip("\x00 \t\r\n")))
    except ValueError:
        return ""


# ---------------------------------------------------------------- minimal TIFF / EXIF reader (no PIL needed)
def _open_tiff(f, base):
    """TIFF header at file position `base` -> (read(offset, n), byte order, offset of IFD0), or None."""
    def rd(off, n):
        f.seek(base + off)
        return f.read(n)
    h = rd(0, 8)
    if len(h) < 8 or h[:4] not in _TIFF_MAGIC:
        return None
    e = "<" if h[:2] == b"II" else ">"
    return rd, e, struct.unpack(e + "I", h[4:8])[0]


def _ifd(rd, e, off):
    """One image file directory as {tag: (type, count, 4 raw value bytes)}; {} if the offset is nonsense."""
    raw = rd(off, 2)
    if len(raw) < 2:
        return {}
    n = struct.unpack(e + "H", raw)[0]
    if n > 1024:                                # a real IFD has tens of entries; this is random data
        return {}
    raw = rd(off + 2, 12 * n)
    out = {}
    for i in range(0, len(raw) - 11, 12):
        tag, typ, cnt = struct.unpack(e + "HHI", raw[i:i + 8])
        out.setdefault(tag, (typ, cnt, raw[i + 8:i + 12]))
    return out


def _text(rd, e, entry):
    typ, cnt, val = entry
    if typ not in (2, 7) or not cnt:            # ASCII, or UNDEFINED as some writers mislabel it
        return ""
    raw = val[:cnt] if cnt <= 4 else rd(struct.unpack(e + "I", val)[0], min(cnt, 64))
    return raw.split(b"\x00")[0].decode("latin-1").strip()


def _num(e, entry):
    if not entry:
        return 0
    typ, _, val = entry
    return struct.unpack(e + "H", val[:2])[0] if typ == 3 else struct.unpack(e + "I", val)[0] if typ in (4, 13) else 0


def _tiff_dates(f, base, tags):
    """Add the usable date/offset tags of the TIFF block at `base` (IFD0 and its Exif sub-IFD) to `tags`, cleaned.
    The first usable value of a tag wins; blanks such as "0000:00:00 00:00:00" are not usable."""
    t = _open_tiff(f, base)
    if not t:
        return
    rd, e, off = t
    ifd0 = _ifd(rd, e, off)
    for d in (ifd0, _ifd(rd, e, _num(e, ifd0[0x8769])) if 0x8769 in ifd0 else {}):
        for tag in _DATE_TAGS + _OFFSET_TAGS:
            if tag in d and tag not in tags:
                value = (_clean_exif_time if tag in _DATE_TAGS else _clean_offset)(_text(rd, e, d[tag]))
                if value:
                    tags[tag] = value


def _jpeg_exif_bases(f):
    """File positions of the TIFF headers inside the APP1 "Exif" segments of a JPEG."""
    bases, pos = [], 2
    while len(bases) < 4:
        f.seek(pos)
        h = f.read(10)
        if len(h) < 4 or h[0] != 0xFF or h[1] in (0xDA, 0xD9):     # start of image data: no more headers
            break
        if h[1] == 0xE1 and h[4:10] == b"Exif\x00\x00":
            bases.append(pos + 10)
        pos += 2 + struct.unpack(">H", h[2:4])[0]
    return bases


def _scan_bases(buf, start):
    """File positions of TIFF headers found in a chunk: those announced by "Exif\\0\\0" first, then bare ones
    (HEIC items without the prefix, PNG eXIf chunks, the CMT boxes of Canon CR3)."""
    out = []
    for prefix in (b"Exif\x00\x00", b""):
        for magic in _TIFF_MAGIC:
            i = buf.find(prefix + magic)
            while i >= 0 and len(out) < 64:
                if start + i + len(prefix) not in out:
                    out.append(start + i + len(prefix))
                i = buf.find(prefix + magic, i + 1)
    return out


def _pick(tags, wanted):
    """Value of the first wanted tag that was found; "" if none was."""
    return next((tags[t] for t in wanted if t in tags), "")


def _exif_from(f, size):
    """(dt, offset) from an open binary file of `size` bytes."""
    tags = {}
    f.seek(0)
    head = f.read(4)
    if head in _TIFF_MAGIC:                     # TIFF and TIFF-based RAW: ARW, DNG, NEF, CR2
        _tiff_dates(f, 0, tags)
    elif head[:2] == b"\xff\xd8":               # JPEG
        for base in _jpeg_exif_bases(f):
            _tiff_dates(f, base, tags)
    if not _pick(tags, _DATE_TAGS):
        # HEIC/HEIF, RAF, CR3, PNG, odd JPEGs: look for a TIFF header. Phones put it in the first few KB, so
        # read a small chunk first and only go on to 8 MB (and the tail of bigger files) when nothing turned up.
        spans = [(0, min(size, _SCAN_FIRST))]
        if size > _SCAN_FIRST:
            spans.append((_SCAN_FIRST - 16, min(size, _SCAN_MAX)))
        if size > _SCAN_MAX:
            spans.append((max(_SCAN_MAX - 16, size - _SCAN_TAIL), size))
        for a, b in spans:
            f.seek(a)
            for base in _scan_bases(f.read(b - a), a):
                _tiff_dates(f, base, tags)
            if _pick(tags, _DATE_TAGS):
                break
    dt = _pick(tags, _DATE_TAGS)
    return (dt, _pick(tags, _OFFSET_TAGS)) if dt else ("", "")


def exif_datetime(path):
    """(dt, offset) of a photo: dt "YYYY:MM:DD HH:MM:SS" from DateTimeOriginal (then DateTimeDigitized, then
    IFD0 DateTime), offset such as "+08:00" from OffsetTimeOriginal (then OffsetTimeDigitized, OffsetTime) or "".
    Works on RAW, JPEG, HEIC without decoding the image. Returns ("", "") when nothing is found; never raises."""
    try:
        with open(path, "rb") as f:
            return _exif_from(f, os.fstat(f.fileno()).st_size)
    except Exception:
        return "", ""


# ---------------------------------------------------------------- photo size
def _tiff_size(f):
    """Largest image described by IFD0 and its SubIFDs (in RAW files IFD0 is only the preview), rotation applied."""
    t = _open_tiff(f, 0)
    if not t:
        return 0, 0
    rd, e, off = t
    ifd0 = _ifd(rd, e, off)
    ifds = [ifd0]
    if 0x014A in ifd0:                          # SubIFDs: one offset inline, several behind a pointer
        _, cnt, val = ifd0[0x014A]
        raw = val if cnt == 1 else rd(struct.unpack(e + "I", val)[0], 4 * min(cnt, 8))
        ifds += [_ifd(rd, e, struct.unpack(e + "I", raw[i:i + 4])[0]) for i in range(0, len(raw) - 3, 4)]
    w, h = max(((_num(e, d.get(0x0100)), _num(e, d.get(0x0101))) for d in ifds), key=lambda s: s[0] * s[1])
    return (h, w) if _num(e, ifd0.get(0x0112)) in (5, 6, 7, 8) else (w, h)


def _heif_size(f):
    """Largest 'ispe' box (image extents) of a HEIC/HEIF file, swapped when its 'irot' box turns it by 90 degrees."""
    f.seek(0)
    buf = f.read(512 << 10)
    best, i = (0, 0), buf.find(b"ispe")
    while i >= 0:
        if len(buf) >= i + 16:
            w, h = struct.unpack(">II", buf[i + 8:i + 16])
            if 0 < w <= 65535 and 0 < h <= 65535 and w * h > best[0] * best[1]:
                best = (w, h)
        i = buf.find(b"ispe", i + 4)
    i = buf.find(b"\x00\x00\x00\x09irot")            # one payload byte: quarter turns, odd = sideways
    return best[::-1] if 0 <= i < len(buf) - 8 and buf[i + 8] & 1 else best


def photo_size(path):
    """(w, h) of a photo as displayed (rotation applied). (0, 0) when it cannot be read - e.g. CR3 and RAF,
    or a broken file. RAW sizes are the sensor area and can be a few pixels larger than the developed image."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in RAW_EXT or ext in HEIF_EXT:
            with open(path, "rb") as f:
                size = _tiff_size(f) if f.read(4) in _TIFF_MAGIC else _heif_size(f)
            if size[0] and size[1]:
                return size
        if ext not in RAW_EXT:                  # PIL would report a RAW file's small preview, not the image
            from PIL import Image
            if ext in HEIF_EXT:
                try:
                    import pillow_heif          # optional; without it HEIC sizes come from the box scan above
                    pillow_heif.register_heif_opener()
                except ImportError:
                    return 0, 0
            with Image.open(path) as im:
                w, h = im.size
                # pillow_heif already applies the rotation; for everything else honour EXIF Orientation
                turned = ext not in HEIF_EXT and im.getexif().get(0x0112, 1) in (5, 6, 7, 8)
            return (h, w) if turned else (w, h)
    except Exception:
        pass
    return 0, 0


# ---------------------------------------------------------------- videos
_lock = threading.Lock()
_dir_cache = {}       # folder -> {UPPER-CASE sidecar name: real name}
_root_cache = {}      # sidecar root -> {UPPER-CASE clip name: [sidecar paths]}
_NTSC = {"23.98": 24000 / 1001.0, "29.97": 30000 / 1001.0, "59.94": 60000 / 1001.0, "119.88": 120000 / 1001.0}
_DAY = datetime.timedelta(hours=24)


def _clip_names(path):
    """Names a clip may have had on the camera card: the whole stem, then its parts from the right
    (Day1_C0028.MP4 was recorded as C0028.MP4, so its sidecar is C0028M01.XML)."""
    stem = os.path.splitext(os.path.basename(path))[0]
    parts = [p for p in re.split(r"[_\-\s]+", stem) if p]
    return [s.upper() for s in dict.fromkeys([stem] + parts[::-1])]


def _read_sidecar(xml_path):
    """(CreationDate as aware datetime or None, clip length in seconds or None) of a Sony NonRealTimeMeta XML."""
    with open(xml_path, "rb") as f:
        text = f.read(256 << 10).decode("utf-8", "replace")
    m = re.search(r'<CreationDate\s+value="([^"]+)"', text)
    dt = parse_iso(m.group(1)) if m else None
    frames = re.search(r'<Duration\s+value="(\d+)"', text)
    fps = re.search(r'formatFps="([\d.]+)(i?)', text)
    secs = None
    if frames and fps and float(fps.group(1)) > 0:              # Duration counts frames; "50i" is 25 frames a second
        secs = int(frames.group(1)) / (_NTSC.get(fps.group(1), float(fps.group(1))) / (2 if fps.group(2) else 1))
    return (dt if dt and dt.tzinfo else None), secs


def _sidecars(path, sidecar_root):
    """[(capture time, clip length or None)] of the Sony sidecars whose NAME matches this clip, distinct times only."""
    folder = os.path.dirname(os.path.abspath(path))
    with _lock:
        if folder not in _dir_cache:
            _dir_cache[folder] = {n.upper(): n for n in os.listdir(folder) if n.upper().endswith("M01.XML")}
        here = _dir_cache[folder]
        index = {}
        if sidecar_root:
            root = os.path.abspath(sidecar_root)
            if root not in _root_cache:         # one walk per run, however many clips ask
                idx = {}
                for d, _, names in os.walk(root):
                    for n in names:
                        if n.upper().endswith("M01.XML") and not n.startswith("."):
                            idx.setdefault(n.upper()[:-7], []).append(os.path.join(d, n))
                _root_cache[root] = idx
            index = _root_cache[root]
    names = _clip_names(path)
    found = [os.path.join(folder, here[n + "M01.XML"]) for n in names if n + "M01.XML" in here][:1]
    if not found:                               # a sidecar next to the clip beats the camera-card copy
        found = next((index[n] for n in names if n in index), [])
    out = []
    for x in sorted(found):
        dt, secs = _read_sidecar(x)
        if dt and dt not in [o[0] for o in out]:
            out.append((dt, secs))
    return out


def _embedded(path):
    """(Apple creationdate with its local offset or None, container creation_time in UTC or None, length in
    seconds) of a video, from one ffprobe call."""
    r = vk.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:format_tags:stream_tags", "-of", "json", path],
               check=False)
    j = json.loads(r.stdout or "{}")
    tags = {}
    for holder in [j.get("format", {})] + j.get("streams", []):
        for k, v in holder.get("tags", {}).items():
            tags.setdefault(k.lower(), v)
    local = parse_iso(tags.get("com.apple.quicktime.creationdate", ""))
    utc = parse_iso(tags.get("creation_time", ""))
    if utc and utc.tzinfo is None:              # ffprobe always prints Z; be safe if a build does not
        utc = utc.replace(tzinfo=datetime.timezone.utc)
    ok = lambda d: d if d and d.tzinfo and d.year >= 1995 else None     # 1904/1970 mean "clock never set"
    try:
        length = float(j.get("format", {}).get("duration") or 0)
    except ValueError:
        length = 0.0
    return ok(local), ok(utc), length


def video_datetime(path, sidecar_root=None):
    """(timezone-aware datetime or None, source) of a video. Tried in order:
      "xml"       Sony sidecar <clip>M01.XML next to the file or anywhere under sidecar_root (CreationDate)
      "qt-local"  ffprobe tag com.apple.quicktime.creationdate (phones; carries the local offset)
      "qt-utc"    ffprobe tag creation_time (UTC)
    (None, "none") when the file carries nothing. Never raises.

    A sidecar is found by clip NAME only, and Sony restarts at C0001 on a freshly formatted card, so the name can
    match another day's clip. A sidecar is therefore used when its date is within 24 h of the time inside the
    file, or else when its clip length equals the file's (a re-export keeps the length but not the date), or
    when it is the only one and nothing contradicts it. Anything doubtful is explained in notes[path]."""
    try:
        cands = _sidecars(path, sidecar_root)
    except Exception:
        cands = []
    try:
        local, utc, length = _embedded(path)
    except Exception:
        local, utc, length = None, None, 0.0
    ref = local or utc
    said = lambda d: d.isoformat(sep=" ")
    near = [c for c in cands if ref and abs(c[0] - ref) <= _DAY]
    fits = [c for c in cands if c[1] is not None and length and abs(c[1] - length) <= max(0.5, 0.02 * length)]
    pick = None
    if near:
        pick = min(near, key=lambda c: abs(c[0] - ref))
    elif len(fits) == 1:
        pick = fits[0]
        if ref:
            notes[path] = ("sidecar (%s) matched by clip length; the time inside the file (%s) is far from it, as "
                           "after a re-export. Check the day." % (said(pick[0]), said(ref)))
    elif len(cands) == 1 and not (ref and cands[0][1] is not None and length):
        pick = cands[0]                         # the only candidate and at most one way to cross-check it
        if ref:
            notes[path] = ("sidecar says %s but the file itself says %s. Sidecar used; check that it belongs to "
                           "this clip." % (said(pick[0]), said(ref)))
        elif pick[1] is not None and length:
            notes[path] = ("sidecar used, but it describes a %.1f s clip and this file is %.1f s long. Check that "
                           "it belongs to this clip." % (pick[1], length))
    elif cands:
        notes[path] = ("%d sidecar(s) carry this clip's name (%s) but neither date nor clip length fits this file; "
                       "ignored, %s." % (len(cands), ", ".join(said(c[0]) for c in cands),
                                         "using the time inside the file" if ref else "and the file has no time of its own"))
    if pick:
        return pick[0], "xml"
    if local:
        return local, "qt-local"
    if utc:
        return utc, "qt-utc"
    return None, "none"


# ---------------------------------------------------------------- the one call most scripts need
def capture_local(path, cfg=None, sidecar_root=None, allow_mtime=False):
    """(when, source): when is "YYYY-MM-DD HH:MM:SS" in the TRIP zone cfg["utc_offset"], source as listed in the
    module docstring. ("", "none") when the file has no embedded time: the modification time is used only with
    allow_mtime=True (source "mtime"), because it is wrong for anything that was copied, synced or exported."""
    cfg = cfg or vk.load()
    trip = parse_offset(cfg["utc_offset"])
    ext = os.path.splitext(path)[1].lower()
    aware, src = None, "none"
    if ext not in VIDEO_EXT:
        dt, off = exif_datetime(path)
        if dt:
            naive = datetime.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
            if off:
                aware, src = naive.replace(tzinfo=parse_offset(off)), "exif"
            else:                               # no offset stored: the camera clock zone has to be assumed
                zone = cfg.get("camera_utc_offset") or cfg["utc_offset"]
                aware, src = naive.replace(tzinfo=parse_offset(zone)), "exif-assumed"
    if aware is None and ext not in PHOTO_EXT:
        aware, src = video_datetime(path, sidecar_root)
    if aware is None and allow_mtime:
        try:
            aware, src = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc), "mtime"
        except OSError:
            pass
    if aware is None:
        return "", "none"
    return aware.astimezone(trip).strftime("%Y-%m-%d %H:%M:%S"), src


# ---------------------------------------------------------------- self-check
def _demo_tiff(e, ifd0, exif=None):
    """Smallest TIFF carrying the given {tag: text} in IFD0 and in an Exif sub-IFD (for --selftest)."""
    def block(tags, at, pointer=None):
        n = len(tags) + (pointer is not None)
        data_at, entries, data = at + 2 + 12 * n + 4, b"", b""
        for tag in sorted(tags):
            raw = tags[tag].encode("ascii") + b"\x00"
            entries += struct.pack(e + "HHI", tag, 2, len(raw))
            entries += raw.ljust(4, b"\x00") if len(raw) <= 4 else struct.pack(e + "I", data_at + len(data))
            data += raw if len(raw) > 4 else b""
        if pointer is not None:
            entries += struct.pack(e + "HHII", 0x8769, 4, 1, pointer)
        return struct.pack(e + "H", n) + entries + b"\x00" * 4 + data
    head = (b"II*\x00" if e == "<" else b"MM\x00*") + struct.pack(e + "I", 8)
    if exif is None:
        return head + block(ifd0, 8)
    return head + block(ifd0, 8, 8 + len(block(ifd0, 8, 0))) + block(exif, 8 + len(block(ifd0, 8, 0)))


def _selftest():
    import io
    read = lambda b: _exif_from(io.BytesIO(b), len(b))
    le = _demo_tiff("<", {0x0132: "2026:03:01 10:00:00"}, {0x9003: "2026:02:16 15:41:05", 0x9011: "+08:00"})
    be = _demo_tiff(">", {0x0132: "2026:03:01 10:00:00"}, {0x9004: "2026:02:16 15:41:06", 0x9010: "+02:00"})
    app1 = b"Exif\x00\x00" + le
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 9 + b"\xff\xe1" + struct.pack(">H", len(app1) + 2) + app1 + b"\xff\xd9"
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 300 + b"\x00\x00\x00\x06Exif\x00\x00" + be
    aware = datetime.datetime(2026, 2, 16, 15, 41, 5, tzinfo=parse_offset("+08:00"))
    checks = [
        ("RAW/TIFF little-endian", read(le), ("2026:02:16 15:41:05", "+08:00")),
        ("TIFF big-endian, digitized fallback", read(be), ("2026:02:16 15:41:06", "+02:00")),
        ("IFD0 DateTime only", read(_demo_tiff("<", {0x0132: "2026:03:01 10:00:00"})), ("2026:03:01 10:00:00", "")),
        ("JPEG APP1", read(jpeg), ("2026:02:16 15:41:05", "+08:00")),
        ("HEIC scan", read(heic), ("2026:02:16 15:41:06", "+02:00")),
        ("bare TIFF inside other data", read(b"\x89PNG" + b"\x07" * 50 + le), ("2026:02:16 15:41:05", "+08:00")),
        ("blank date ignored", read(_demo_tiff("<", {0x0132: "0000:00:00 00:00:00"})), ("", "")),
        ("garbage", read(b"MM\x00*" + b"\xff" * 40), ("", "")),
        ("empty file", read(b""), ("", "")),
        ("parse_offset", [offset_text(parse_offset(s)) for s in ("+08:00", "-0330", "+2", "Z")],
         ["+08:00", "-03:30", "+02:00", "+00:00"]),
        ("parse_iso offset", parse_iso("2026-02-16T15:41:05+08:00"), aware),
        ("parse_iso compact offset", parse_iso("2026-02-16T09:41:05+0200"), aware),
        ("parse_iso Z", parse_iso("2026-02-16T07:41:05.000000Z"), aware),
        ("home zone to trip zone", aware.astimezone(parse_offset("+02:00")).strftime("%Y-%m-%d %H:%M:%S"), "2026-02-16 09:41:05"),
    ]
    bad = [(name, got, want) for name, got, want in checks if got != want]
    for name, got, want in bad:
        print(f"FAIL {name}: got {got!r}, expected {want!r}")
    print(f"CAPTURE_TIME selftest: {len(checks) - len(bad)}/{len(checks)} passed")
    return 1 if bad else 0


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        return _selftest()
    cfg = vk.load()                             # also removes --project <folder> from sys.argv
    args = sys.argv[1:]
    sidecars = None
    if "--sidecars" in args:
        i = args.index("--sidecars")
        sidecars = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 1
    missing = lost = 0
    print("trip zone %s, camera zone assumed for photos without offset %s"
          % (cfg["utc_offset"], cfg.get("camera_utc_offset") or cfg["utc_offset"]))
    for path in args:
        if not os.path.isfile(path):
            print(f"{path}\n  NOT FOUND")
            lost += 1
            continue
        when, src = capture_local(path, cfg, sidecars)
        print(f"{path}\n  trip-local: {when or '(no embedded time)'}   source: {src}")
        if os.path.splitext(path)[1].lower() in VIDEO_EXT:
            aware, vsrc = video_datetime(path, sidecars)
            print(f"  as stored:  {aware.isoformat() if aware else '-'} ({vsrc})")
        else:
            dt, off = exif_datetime(path)
            print(f"  as stored:  EXIF {dt or '-'} offset {off or '(none stored)'}   size %dx%d" % photo_size(path))
        if path in notes:
            print(f"  note:       {notes[path]}")
        missing += not when
    print(f"CAPTURE_TIME files={len(args)} without_time={missing} not_found={lost}")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
