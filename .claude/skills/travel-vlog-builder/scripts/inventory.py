"""inventory - build or update <project>/catalog.csv, the single list of usable media.

The edit list refers to media by the ids in this catalog, so ids are STABLE: a file that is already listed keeps
its id on every later run, a moved or renamed file is recognised and keeps it, and an id is never handed to a
different file. Every "when" is the capture time embedded in the file, converted to the trip's time zone
(see capture_time.py) - never a folder name or a file modification time.

Usage:
    python -I -X utf8 inventory.py --project <folder>              first build, or add new media (ids are kept)
    python -I -X utf8 inventory.py --project <folder> --dry-run    report only, write nothing
    python -I -X utf8 inventory.py --project <folder> --force      rebuild from scratch - ids MAY CHANGE

Inputs:
  project.json
    "utc_offset": "+02:00"           the trip's time zone
    "camera_utc_offset": "+08:00"    optional: zone the camera clock was set to; used for photos that store no offset
    "sources": [
        {"path": "iCloud Photos", "photos": "P", "videos": "V"},
        {"path": "Clips", "videos": "S", "ids": "suffix", "sidecars": "E:/Camera/Trip"},
        {"path": "Photos", "photos": "A", "ids": "prefix"}
    ]
      path      folder, relative to the project or absolute; scanned recursively
      photos    kind letter for the photos found there (leave out to ignore photos)
      videos    kind letter for the videos found there (leave out to ignore videos)
                kinds: P phone photo, V phone video, S main-camera clip, A main-camera photo already styled
      ids       "seq" (default)  <kind><number> in order of capture time: P1, P2, V1 ...
                "suffix"         the part of the file name after the last "_":   Day1_C0028.MP4 -> C0028
                "prefix"         the part before the first "_":                  D1-08_AFR02432.jpg -> D1-08
                "stem"           the whole file name without its extension
      sidecars  folder with the Sony <clip>M01.XML files (searched recursively) when they are not next to the clips
      camera_utc_offset   optional, overrides the project value for this source
      allow_mtime         optional, true: fall back to the file modification time (unreliable; shown as src "mtime")
      shift_hours         optional number added to every capture time of this source (a clock that was simply wrong)
  <work>/styled.csv   optional, columns id,src,out,when: capture times of kind A photos, matched by id (or by "out")
  Photos: jpg jpeg png heic heif tif tiff arw dng nef cr2 cr3 raf.  Videos: mp4 mov m4v mts avi.

Outputs:
  <project>/catalog.csv          id,kind,path,when,dur,w,h,fps,src   sorted by capture time
        path  relative to the project when inside it, else absolute; always forward slashes
        when  "YYYY-MM-DD HH:MM:SS" trip-local, "" if the file has no embedded time
        dur   seconds (videos)      w,h  displayed size, 0 if unknown      fps  videos
        src   where "when" came from: exif | exif-assumed | xml | qt-local | qt-utc | styled | mtime | none
  <work>/catalog_prev.csv        the catalog as it was before this run
  <work>/catalog_removed.csv     rows of files that disappeared; their ids stay reserved and return with the file
  <work>/inventory_report.txt    the full report (the screen shows long lists cut short)
  Last line on screen:  INVENTORY ok total=.. new=.. kept=.. moved=.. restored=.. removed=.. no_time=.. assumed=..
                        collisions=.. unreadable=.. written=yes|no catalog=<path>     (INVENTORY FAILED: ... and exit 1)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

import csv
import datetime
import io
import re
import shutil
from concurrent.futures import ThreadPoolExecutor

import capture_time as ct

COLUMNS = ["id", "kind", "path", "when", "dur", "w", "h", "fps", "src"]
ID_MODES = ("seq", "suffix", "prefix", "stem")
SOURCE_KEYS = ("path", "photos", "videos", "ids", "sidecars", "camera_utc_offset", "allow_mtime", "shift_hours", "note")
SKIP_DIRS = {"$recycle.bin", "system volume information", "__macosx", "@eadir"}
MUST_OPEN = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}     # Pillow reads these; if it cannot, the file is broken


class Fail(Exception):
    """A problem the user has to fix; nothing is written."""


# ---------------------------------------------------------------- paths
def _key(path):
    """Comparison key of a path: absolute, normalised, lower-cased where the file system ignores case."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _shown(path, base):
    """Path as written to the catalog: relative to the project when inside it, with forward slashes."""
    path = os.path.abspath(path)
    try:
        inside = os.path.commonpath([_key(path), _key(base)]) == _key(base)
    except ValueError:                          # another drive
        inside = False
    out = os.path.relpath(path, base) if inside else path
    return out.replace("\\", "/") if os.sep == "\\" else out


def _abs(shown, base):
    return os.path.normpath(shown if os.path.isabs(shown) else os.path.join(base, shown))


def read_rows(csv_path, base):
    """Rows of a catalog-shaped CSV as dicts, each with "_key" (comparison key of its path). [] if absent."""
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        lacking = [c for c in COLUMNS if c not in (rd.fieldnames or [])]
        if lacking:
            raise Fail(f"{csv_path} lacks the column(s) {', '.join(lacking)}. Restore it from _work/catalog_prev.csv, "
                       f"or rebuild with --force (ids may change).")
        rows = [dict((c, (r.get(c) or "").strip()) for c in COLUMNS) for r in rd]
    rows = [r for r in rows if r["id"] and r["path"]]
    for r in rows:
        r["_key"] = _key(_abs(r["path"], base))
    return rows


def load_catalog(cfg=None):
    """catalog.csv for other scripts: list of row dicts, each with an extra "abs" (absolute path of the file)."""
    cfg = cfg or vk.load()
    rows = read_rows(cfg["catalog"], cfg["base"])
    for r in rows:
        r["abs"] = _abs(r["path"], cfg["base"])
        del r["_key"]
    return rows


# ---------------------------------------------------------------- configuration
def read_sources(cfg):
    """Checked copy of project.json "sources". Raises Fail naming every problem at once."""
    problems = []
    for name in ("utc_offset", "camera_utc_offset"):
        if cfg.get(name):
            try:
                ct.parse_offset(cfg[name])
            except ValueError as e:
                problems.append(f'"{name}": {e}')
    raw = cfg.get("sources")
    if not isinstance(raw, list) or not raw:
        raise Fail('project.json has no "sources" list. Example: '
                   '"sources": [{"path": "iCloud Photos", "photos": "P", "videos": "V"}]')
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict) or not isinstance(s.get("path"), str) or not s["path"].strip():
            problems.append(f'sources[{i}]: must be an object with a "path"')
            continue
        tag = f'sources[{i}] "{s["path"]}"'
        odd = [k for k in s if k not in SOURCE_KEYS and not k.startswith("_")]
        if odd:
            problems.append(f"{tag}: unknown key(s) {', '.join(odd)}; allowed: {', '.join(SOURCE_KEYS)}")
        kinds = {}
        for media in ("photos", "videos"):
            k = s.get(media) or ""
            if k and not (isinstance(k, str) and re.match(r"^[A-Za-z]{1,4}$", k)):
                problems.append(f'{tag}: "{media}" must be a kind letter such as "P", not {k!r}')
            kinds[media] = k if isinstance(k, str) else ""
        if not kinds["photos"] and not kinds["videos"]:
            problems.append(f'{tag}: give "photos" and/or "videos" a kind letter, otherwise nothing is collected')
        ids = s.get("ids") or "seq"
        if ids not in ID_MODES:
            problems.append(f'{tag}: "ids" must be one of {", ".join(ID_MODES)}, not {ids!r}')
        root = _abs(s["path"].strip(), cfg["base"])
        if not os.path.isdir(root):
            problems.append(f"{tag}: folder not found: {root}. Connect the drive or correct the path "
                            f"(running without it would drop its files from the catalog).")
        sidecars = _abs(str(s["sidecars"]), cfg["base"]) if s.get("sidecars") else None
        if sidecars and not os.path.isdir(sidecars):
            problems.append(f'{tag}: sidecar folder not found: {sidecars}. Connect the drive, or remove "sidecars" '
                            f"to use the time stored inside the clips.")
        scfg = vk.Cfg(cfg)                       # capture_local reads the camera zone from the cfg it is given
        if s.get("camera_utc_offset"):
            try:
                ct.parse_offset(s["camera_utc_offset"])
                scfg["camera_utc_offset"] = s["camera_utc_offset"]
            except ValueError as e:
                problems.append(f'{tag}: "camera_utc_offset": {e}')
        shift = s.get("shift_hours") or 0
        if isinstance(shift, bool) or not isinstance(shift, (int, float)):
            problems.append(f'{tag}: "shift_hours" must be a number, not {shift!r}')
            shift = 0
        out.append(dict(n=i, label=s["path"].strip(), root=root, photos=kinds["photos"], videos=kinds["videos"],
                        ids=ids, sidecars=sidecars, cfg=scfg, allow_mtime=bool(s.get("allow_mtime")), shift=shift, count=0))
    if problems:
        raise Fail("project.json needs fixing:\n  - " + "\n  - ".join(problems))
    return out


def read_styled(cfg):
    """<work>/styled.csv -> ({id: when}, {path key of the styled file: when}); both empty when there is none.
    Rows whose "when" is not a date and time are skipped, so the photo falls back to its own EXIF."""
    by_id, by_out = {}, {}
    path = os.path.join(cfg["work"], "styled.csv")
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                m = re.match(r"(\d{4})[:\-/](\d{2})[:\-/](\d{2})[ T](\d{2}:\d{2}:\d{2})", (r.get("when") or "").strip())
                when = "%s-%s-%s %s" % m.groups() if m else ""
                if when and (r.get("id") or "").strip():
                    by_id[r["id"].strip()] = when
                if when and (r.get("out") or "").strip():
                    by_out[_key(_abs(r["out"].strip(), cfg["base"]))] = when
    return by_id, by_out


# ---------------------------------------------------------------- scanning and probing
def scan(cfg, sources):
    """All media files under the sources -> (items, listed_twice). A file reachable through two sources belongs
    to the first. The project's own output folders, hidden files and "._" resource forks are skipped."""
    own = set(_key(cfg[n]) for n in ("out", "work", "graphics", "music", "subs"))
    seen, items, twice = set(), [], []
    for s in sources:
        for root, dirs, names in os.walk(s["root"]):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() not in SKIP_DIRS
                             and _key(os.path.join(root, d)) not in own)
            for n in sorted(names):
                ext = os.path.splitext(n)[1].lower()
                media = "photo" if ext in ct.PHOTO_EXT else "video" if ext in ct.VIDEO_EXT else None
                if n.startswith(".") or not media or not s[media + "s"]:
                    continue
                path = os.path.join(root, n)
                if _key(path) in seen:
                    twice.append(_shown(path, cfg["base"]))
                    continue
                seen.add(_key(path))
                s["count"] += 1
                items.append(dict(abs=path, media=media, kind=s[media + "s"], source=s))
    return items, twice


def probe(item, cfg):
    """(row, None) for a usable file - the row has no id yet - or (None, reason) for one that is not."""
    s, path = item["source"], item["abs"]
    row = dict(id="", kind=item["kind"], path=_shown(path, cfg["base"]), when="", dur="", w="0", h="0", fps="", src="none",
               _key=_key(path), _media=item["media"], _ids=s["ids"], _source=s["n"])
    try:
        if os.path.getsize(path) == 0:
            return None, "empty file"
        if item["media"] == "video":
            info = vk.probe(path)
            if not info["w"] or info["dur"] <= 0:
                return None, "ffprobe finds no playable video in it"
            row.update(dur="%.3f" % info["dur"], w=str(info["w"]), h=str(info["h"]),
                       fps=("%.3f" % info["fps"]).rstrip("0").rstrip("."))
        else:
            w, h = ct.photo_size(path)
            if not w and os.path.splitext(path)[1].lower() in MUST_OPEN:
                return None, "the image cannot be opened"
            row.update(w=str(w), h=str(h))
        when, src = ct.capture_local(path, s["cfg"], s["sidecars"], s["allow_mtime"])
        if when and s["shift"]:
            t = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M:%S") + datetime.timedelta(hours=s["shift"])
            when = t.strftime("%Y-%m-%d %H:%M:%S")
        row.update(when=when, src=src)
    except Exception as e:                      # one odd file must not stop thousands
        return None, f"{type(e).__name__}: {e}"
    return row, None


def probe_all(items, cfg):
    results = []
    with ThreadPoolExecutor(max_workers=max(1, int(cfg.get("workers") or 4))) as pool:
        for i, res in enumerate(pool.map(lambda it: probe(it, cfg), items), 1):
            results.append(res)
            if len(items) >= 400 and i % 200 == 0:
                print(f"  ... {i}/{len(items)} files read", file=sys.stderr)
    return results


# ---------------------------------------------------------------- ids
def _wanted(row):
    """The id a file asks for under the suffix / prefix / stem rules."""
    stem = os.path.splitext(os.path.basename(row["path"]))[0]
    if row["_ids"] == "suffix":
        stem = stem.rsplit("_", 1)[-1]
    elif row["_ids"] == "prefix":
        stem = stem.split("_", 1)[0]
    return stem.strip()


def _print_of(row, with_name):
    """Fingerprint that survives moving (and, without the name, renaming) a file."""
    name = os.path.basename(row["path"]).lower() if with_name else ""
    if not with_name and not row["when"]:
        return None                             # size alone is not an identity
    return (row["kind"], name, row["when"], row["dur"], row["w"], row["h"])


def assign_ids(rows, old, retired):
    """Fill row["id"] for every row and return what happened. Order of preference:
    1. same path as before (in the catalog, or in the removed list: the file came back) -> same id
    2. same fingerprint as a row whose file is gone -> the file was moved or renamed -> same id
    3. a fresh id that no file has ever had: the wanted name, or <kind><next number>."""
    known = {}
    for r in old + retired:
        known.setdefault(r["_key"], r)
    used = set(r["id"] for r in old + retired)
    old_keys = set(r["_key"] for r in old)
    st = dict(kept=0, restored=[], moved=[], new=[], collisions=[], removed=[])

    todo = []
    for r in rows:
        k = known.get(r["_key"])
        if not k:
            todo.append(r)
            continue
        r["id"] = k["id"]
        if r["_key"] in old_keys:
            st["kept"] += 1
        else:
            st["restored"].append(r)

    present = set(r["_key"] for r in rows)
    orphans = [k for k in known.values() if k["_key"] not in present]
    for with_name in (True, False):             # moved files first, then files that were also renamed
        gone, came = {}, {}
        for r in orphans:
            gone.setdefault(_print_of(r, with_name), []).append(r)
        for r in todo:
            came.setdefault(_print_of(r, with_name), []).append(r)
        for fp, was in gone.items():
            if fp is not None and len(was) == 1 and len(came.get(fp, [])) == 1:     # unambiguous on both sides
                now = came[fp][0]
                now["id"] = was[0]["id"]
                st["moved"].append((was[0]["path"], now))
                orphans.remove(was[0])
                todo.remove(now)

    # wanted names: granted when free and asked for by one file only; otherwise a longer, unique name
    asks = {}
    for r in todo:
        if r["_ids"] != "seq":
            asks.setdefault(_wanted(r), []).append(r)
    clashing = []
    for want, group in sorted(asks.items()):
        if want and want not in used and len(group) == 1:
            group[0]["id"] = want
            used.add(want)
        else:
            clashing.append((want, group))
    for want, group in clashing:
        for r in sorted(group, key=lambda r: r["path"]):
            name = os.path.basename(r["path"])
            tries = [os.path.splitext(name)[0], name] + [f"{name}-{n}" for n in range(2, 1000)]
            r["id"] = next(t for t in tries if t and t not in used)
            used.add(r["id"])
            st["collisions"].append((want, r))

    # running numbers: new files in order of capture time, continuing after the highest number ever used
    nxt = {}
    for r in sorted((r for r in todo if r["_ids"] == "seq"), key=lambda r: (r["when"] or "9999", r["path"])):
        k = r["kind"]
        if k not in nxt:
            pat = re.compile(r"^%s(\d+)$" % re.escape(k))
            nxt[k] = 1 + max([int(m.group(1)) for m in map(pat.match, used) if m] or [0])
        while f"{k}{nxt[k]}" in used:
            nxt[k] += 1
        r["id"] = f"{k}{nxt[k]}"
        used.add(r["id"])

    st["new"] = todo
    st["removed"] = [k for k in orphans if k["_key"] in old_keys]
    st["retired"] = orphans                     # every row whose file is gone: newly removed + removed earlier
    return st


# ---------------------------------------------------------------- report and output
class Report:
    """Lines go to the screen and to <work>/inventory_report.txt; long lists are cut short on screen only."""

    def __init__(self):
        self.lines = []

    def say(self, text="", screen=True):
        self.lines.append(text)
        if screen:
            print(text)

    def block(self, title, items, limit=12, why=""):
        if not items:
            return
        self.say(f"  {title} ({len(items)})" + (f": {why}" if why else ""))
        for i, it in enumerate(items):
            self.say("      " + it, i < limit)
        if len(items) > limit:
            print(f"      ... and {len(items) - limit} more, see _work/inventory_report.txt")


def _csv_text(rows):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def _write(path, text):
    """Write through a temporary file so a crash never leaves half a catalog."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError as e:                        # on Windows: the csv is open in Excel
        if os.path.exists(tmp):
            os.remove(tmp)
        raise Fail(f"cannot write {path} ({e.strerror or e}). If it is open in another program (Excel?), close it and run again.")


def build(cfg, force=False, dry_run=False):
    """Scan, probe, assign ids, report and (unless dry_run) write. Returns the counts of the summary line."""
    if not shutil.which("ffprobe"):
        raise Fail("ffprobe was not found on PATH (it comes with ffmpeg); videos cannot be read without it.")
    try:
        import PIL  # noqa: F401 - only to fail early with a clear message
    except ImportError:
        raise Fail("Pillow is not installed for this Python (python -m pip install pillow); photos cannot be read without it.")
    sources = read_sources(cfg)
    base, work, catalog = cfg["base"], cfg["work"], cfg["catalog"]
    removed_csv = os.path.join(work, "catalog_removed.csv")
    before = read_rows(catalog, base)
    old, retired = ([], []) if force else (before, read_rows(removed_csv, base))
    styled_id, styled_out = read_styled(cfg)

    items, twice = scan(cfg, sources)
    if not items:
        raise Fail("no photos or videos found under: " + ", ".join(s["root"] for s in sources))
    rows, unreadable = [], []
    for item, (row, reason) in zip(items, probe_all(items, cfg)):
        if row:
            rows.append(row)
        else:
            unreadable.append(f"{_shown(item['abs'], base)}: {reason}")

    def use_styled(r, rid):                     # kind A: the styling step knows the RAW file's capture time
        when = styled_id.get(rid) or styled_out.get(r["_key"])
        if r["kind"] == "A" and when:
            r.update(when=when, src="styled")
    for r in rows:                              # before ids exist, so numbering and move detection see it
        use_styled(r, _wanted(r) if r["_ids"] != "seq" else "")
    st = assign_ids(rows, old, retired)
    for r in rows:
        use_styled(r, r["id"])
    rows.sort(key=lambda r: (r["when"] or "9999", r["kind"], r["path"]))
    holders = {}
    for r in rows:
        holders.setdefault(r["id"], []).append(r["path"])
    duplicates = [f"{i}: {', '.join(p)}" for i, p in sorted(holders.items()) if len(p) > 1]

    # ---- report
    rp = Report()
    cam = cfg.get("camera_utc_offset") or cfg["utc_offset"]
    zone = dict((s["n"], s["cfg"].get("camera_utc_offset") or cfg["utc_offset"]) for s in sources)
    rp.say(f"inventory of \"{cfg['name']}\"  trip zone {cfg['utc_offset']}  camera zone when a photo stores none {cam}")
    for s in sources:
        extra = [f"sidecars={s['sidecars']}" if s["sidecars"] else "", f"camera zone {zone[s['n']]}" if zone[s["n"]] != cam else "",
                 "allow_mtime" if s["allow_mtime"] else "", f"shift_hours={s['shift']:+g}" if s["shift"] else ""]
        rp.say("  ".join([f"  source {s['n']}: {s['label']}", f"photos={s['photos'] or '-'} videos={s['videos'] or '-'} ids={s['ids']}",
                          f"files={s['count']}"] + [x for x in extra if x]))
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    rp.say("kinds: " + "  ".join(f"{k}={n}" for k, n in sorted(kinds.items())) + f"  total={len(rows)}")
    srcs = {}
    for r in rows:
        srcs[r["src"]] = srcs.get(r["src"], 0) + 1
    rp.say("time sources: " + "  ".join(f"{k}={n}" for k, n in sorted(srcs.items())))
    rp.say("days (trip-local):")
    rp.say("  day          photos  videos  first     last")
    days = {}
    for r in rows:
        d = days.setdefault(r["when"][:10] or "(no time)", dict(photo=0, video=0, t=[]))
        d[r["_media"]] += 1
        d["t"].append(r["when"][11:])
    for day in sorted(days, key=lambda d: (d.startswith("("), d)):
        d = days[day]
        rp.say(f"  {day:<11}  {d['photo']:>6}  {d['video']:>6}  {min(d['t']):<8}  {max(d['t']):<8}")

    no_time = [r["path"] for r in rows if not r["when"]]
    assumed = [f"{r['path']}  -> {r['when']}  (camera clock taken as {zone[r['_source']]})"
               for r in rows if r["src"] == "exif-assumed"]
    mtimes = [f"{r['path']}  -> {r['when']}" for r in rows if r["src"] == "mtime"]
    doubts = [f"{_shown(p, base)}: {t}" for p, t in sorted(ct.notes.items())]
    line = lambda r: f"{r['id']:<10} {r['when'] or '(no time)':<19}  {r['path']}"
    if old or retired:
        rp.say("changes since the last run:" + ("" if st["new"] or st["moved"] or st["restored"] or st["removed"] else " none"))
    else:
        rp.say("first build" + (" (--force: every id was assigned anew):" if force else ":"))
    rp.block("NEW ids", [line(r) for r in sorted(st["new"], key=lambda r: (r["kind"], r["when"] or "9999", r["path"]))], 30)
    rp.block("MOVED OR RENAMED, id kept", [f"{r['id']:<10} {was}  ->  {r['path']}" for was, r in st["moved"]])
    rp.block("CAME BACK, old id restored", [line(r) for r in st["restored"]])
    rp.block("REMOVED", [line(r) for r in st["removed"]],
             why="no longer found under any source (deleted, renamed beyond recognition, or its source left "
                 "project.json), so the row left the catalog. Its id stays reserved and returns if the file does")
    if force and before:
        was = dict((r["_key"], r["id"]) for r in before)
        changed = [f"{was[r['_key']]} -> {r['id']}  {r['path']}" for r in rows if r["_key"] in was and was[r["_key"]] != r["id"]]
        rp.block("IDS CHANGED BY --force", changed, 30,
                 why="an edit list that uses the old ids now points to other media or to nothing - update it")
    warned = no_time or assumed or mtimes or doubts or st["collisions"] or duplicates or unreadable
    rp.say("warnings:" if warned else "warnings: none")
    rp.block("NO EMBEDDED TIME", no_time,
             why="\"when\" is empty, so these cannot be placed on a day. Do not guess from the folder name: "
                 "ask for the real time or leave them out")
    rp.block("ASSUMED CAMERA ZONE", assumed,
             why="the photo stores no UTC offset, so the zone of its camera clock was taken from \"camera_utc_offset\". "
                 "Check one against a photo whose real time is known")
    rp.block("FILE MODIFICATION TIME USED", mtimes, why="allow_mtime is on for this source; these times are unreliable")
    rp.block("SIDECAR DOUBT", doubts)
    rp.block("ID COLLISION", [f"{want or '(empty)'}: {r['path']} -> {r['id']}" for want, r in st["collisions"]],
             why="the wanted id is taken or wanted by several files; each got a longer, unique id instead")
    rp.block("DUPLICATE ID IN THE CATALOG", duplicates, why="fix by hand or rebuild with --force")
    rp.block("UNREADABLE", unreadable, why="left out of the catalog")
    if twice:                                   # normal when one source is a sub-folder of another: say it once
        rp.say(f"note: {len(twice)} file(s) lie under two sources; each belongs to the first source that lists it")
        for t in twice:
            rp.say("      " + t, screen=False)

    # ---- write
    text = _csv_text(rows)
    current = None
    if os.path.exists(catalog):
        with open(catalog, encoding="utf-8", newline="") as f:
            current = f.read()
    written = "no"
    if dry_run:
        rp.say("dry run: nothing written")
    else:
        os.makedirs(work, exist_ok=True)
        if text != current:
            if current is not None:
                shutil.copyfile(catalog, os.path.join(work, "catalog_prev.csv"))
            _write(catalog, text)
            written = "yes"
        else:
            rp.say("catalog.csv is already up to date")
        if st["retired"]:
            _write(removed_csv, _csv_text(st["retired"]))
        elif os.path.exists(removed_csv):
            os.remove(removed_csv)
    counts = dict(total=len(rows), new=len(st["new"]), kept=st["kept"], moved=len(st["moved"]), restored=len(st["restored"]),
                  removed=len(st["removed"]), no_time=len(no_time), assumed=len(assumed),
                  collisions=len(st["collisions"]) + len(duplicates), unreadable=len(unreadable))
    summary = "INVENTORY ok " + " ".join(f"{k}={v}" for k, v in counts.items()) + f" written={written} catalog={catalog}"
    rp.lines.append(summary)
    if not dry_run:
        with open(os.path.join(work, "inventory_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(rp.lines) + "\n")
    print(summary)
    return counts


def main():
    cfg = vk.load()                             # also removes --project <folder> from sys.argv
    args = sys.argv[1:]
    odd = [a for a in args if a not in ("--force", "--dry-run")]
    if odd:
        print(f"INVENTORY FAILED: unknown argument(s) {' '.join(odd)}. "
              "Usage: inventory.py --project <folder> [--dry-run] [--force]")
        return 1
    try:
        build(cfg, force="--force" in args, dry_run="--dry-run" in args)
    except Fail as e:
        print(f"INVENTORY FAILED: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
