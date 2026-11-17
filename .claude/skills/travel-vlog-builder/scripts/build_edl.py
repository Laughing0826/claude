"""build_edl - turn the project's shot list into edit_list_<version>.json and check it.

usage:  python -I -X utf8 build_edl.py [--project <folder>] [<edl file>]
        default edl file: <base>/edl_<version>.py

The EDL file is plain Python that calls the vocabulary below, top to bottom, in screen order. It needs no imports
(this script runs it with the vocabulary already defined). One line = one shot:

  day(n, "YYYY-MM-DD")            every following shot belongs to trip day n, filmed on that local date.
                                  day(0, None) = not date-checked (intro montage, end card).
  S(ref, i, d, **o)               main-camera clip used straight from the source file (graded by LUT in Resolve)
  SV(ref, i, d, **o)              main-camera clip pre-rendered (portrait clips, odd frame rates); LUT baked in
  V(ref, i, d, **o)               phone video, pre-rendered (portrait gets blurred sides, sound normalised)
  D(ref, i, d, **o)               documentary cut of a main-camera clip: speed=1|0.5, z=(z0, z1), c=(cx, cy), doc="group"
  A(ref, d=2.3, mv="in", **o)     main-camera photo (already styled), slow zoom/pan
  P(ref, d=2.3, mv="in", **o)     phone photo; dark=0 normal look, 1 dusk/indoor (light look), 2 night/sunset (untouched)
  M(d, **o)                       the route map still (project.json route.map), zooming in
  C(ref, photos, title, note, cap, d=5.6, bg=1, **o)   scrapbook slide of 2-4 photos (catalog ids)
  R(ref, d, clips=[(id, i, date, day), ...])           VHS rewind intro; clips in REVERSE story order

  ref = id in catalog.csv, i = in-point in seconds, d = duration on screen in seconds, mv = in|out|left|right|pano.

Options (**o), all optional:
  tr="Cross Dissolve"              transition INTO this shot (none = hard cut); names in TRANSITIONS below
  mute=True                        drop the clip's sound (montage shots, wind noise)
  sub=(en, lang2, span)            caption starting on this shot and staying up for `span` shots
  subs=[(t0, t1, en, lang2), ...]  captions timed in seconds within this shot (transcribed speech)
  card=(en, lang2)                 chapter card, en like "DAY 1 · 16 FEB · PLACE — PLACE"
  loc=(en, lang2)                  location tag, top right
  sp=(en, lang2)                   species / name label, lower left
  lower=(NAME, scientific, lang2)  documentary name title (first shot of a doc group)
  title=(main, lang2, small, script_top, tagline)   opening or closing title
  stk="text"                       pop-up sticker
  badge="sprite"                   "Spotted!" badge with an illustration from Graphics/mg/cut/<sprite>.png
  mg="vehicle"|"parade"|"route"|"flight"            motion graphic over this shot

Output: <base>/edit_list_<version>.json, <base>/<version>/date_check_<version>.txt and a printed report.
Exit code 1 if any shot cannot be resolved (missing media, in-point beyond the clip, unknown id).
"""
import csv
import datetime
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vk

# transition names exactly as DaVinci Resolve knows them; FUSION ones need category "fusion" when added by script
FUSION_TRANSITIONS = {"Brightness Flash", "Zoom In", "Slide Left", "Slide Up", "Slide Down", "Glitch", "Film Strip", "Spin",
                      "Camera Shake", "Foreground Wipe"}
TRANSITIONS = FUSION_TRANSITIONS | {"Cross Dissolve", "Additive Dissolve", "Dip To Color Dissolve", "Push", "Barn Door", "Clock Wipe",
                                    "Edge Wipe", "Split", "Star", "Heart"}
MOVES = {"in", "out", "left", "right", "pano"}
MG = {"vehicle", "parade", "route", "flight"}

shots = []
_DAY = [None]


def _add(kind, ref, d, i=None, **k):
    s = dict(kind=kind, ref=ref, d=d, i=i, day=_DAY[0])
    s.update(k)
    shots.append(s)
    return s


def S(ref, i, d, **k): return _add("S", ref, d, i, **k)
def SV(ref, i, d, **k): return _add("SV", ref, d, i, **k)
def V(ref, i, d, **k): return _add("V", ref, d, i, **k)
def D(ref, i, d, **k): return _add("D", ref, d, i, **k)
def A(ref, d=2.3, mv="in", **k): return _add("A", ref, d, mv=mv, **k)
def P(ref, d=2.3, mv="in", **k): return _add("P", ref, d, mv=mv, **k)
def M(d, **k): return _add("M", k.pop("ref", "route-map"), d, mv=k.pop("mv", "in"), **k)
def C(ref, photos, title, note, cap, d=5.6, bg=1, **k): return _add("C", ref, d, photos=photos, title=title, note=note, cap=cap, bg=bg, **k)
def R(ref, d, clips, **k): return _add("R", ref, d, clips=clips, **k)
def day(n, date): _DAY[0] = (n, date)


VOCAB = dict(S=S, SV=SV, V=V, D=D, A=A, P=P, M=M, C=C, R=R, day=day)


def _load_catalog(cfg):
    if not os.path.exists(cfg["catalog"]):
        sys.exit(f"{cfg['catalog']} not found. Run inventory.py first.")
    cat = {}
    with open(cfg["catalog"], encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["path"] = r["path"] if os.path.isabs(r["path"]) else cfg.p(r["path"])
            cat[r["id"]] = r
    return cat


def _plus(when, secs):
    if not when:
        return ""
    return (datetime.datetime.strptime(when, "%Y-%m-%d %H:%M:%S") + datetime.timedelta(seconds=secs or 0)).strftime("%Y-%m-%d %H:%M:%S")


def finish(cfg):
    FPS = cfg["FPS"]
    cat = _load_catalog(cfg)
    errors, warns = [], []

    def item(ref, n):
        ref = ref.split(":", 1)[1] if len(ref) > 2 and ref[1] == ":" else ref     # accepts "A:D1-24" as well as "D1-24"
        if ref not in cat:
            errors.append(f"shot {n}: id '{ref}' is not in catalog.csv")
            return None
        if not os.path.exists(cat[ref]["path"]):
            errors.append(f"shot {n}: file missing for '{ref}': {cat[ref]['path']}")
            return None
        return cat[ref]

    t = 0
    for n, s in enumerate(shots):
        k, r = s["kind"], s["ref"]
        s["n"] = n
        s["frames"] = round(s["d"] * FPS)
        s["start"] = t
        t += s["frames"]
        s["when"] = ""
        if k in ("S", "SV", "V", "D"):
            it = item(r, n)
            if not it:
                continue
            s["file"] = it["path"]
            s["srcdur"] = float(it.get("dur") or 0)
            s["srcfps"] = float(it.get("fps") or 0)
            need = s["i"] + s["d"] * float(s.get("speed", 1))
            if s["srcdur"] and need > s["srcdur"] + 0.01:
                errors.append(f"shot {n} {r}: needs source up to {need:.2f}s but the clip is {s['srcdur']:.2f}s long")
            if k == "S":
                ratio = s["srcfps"] / FPS if s["srcfps"] else 1
                if abs(ratio - round(ratio)) > 0.01 or round(ratio) < 1:
                    errors.append(f"shot {n} {r}: {s['srcfps']:.2f} fps is not a multiple of the {FPS} fps timeline; use SV() so it is pre-rendered")
                if it.get("w") and it.get("h") and int(it["w"]) < int(it["h"]):
                    errors.append(f"shot {n} {r}: portrait clip; use SV() so it gets blurred sides")
            if k == "D" and float(s.get("speed", 1)) < 1 and s["srcfps"] and s["srcfps"] < 2 * FPS * 0.99:
                warns.append(f"shot {n} {r}: slow motion on a {s['srcfps']:.0f} fps source will stutter; use speed=1")
            s["when"] = _plus(it.get("when", ""), s["i"])
        elif k in ("A", "P"):
            it = item(r, n)
            if not it:
                continue
            s["file"] = it["path"]
            s["when"] = it.get("when", "")
        elif k == "M":
            mp = (cfg.get("route") or {}).get("map") or os.path.join("Graphics", r + ".png")
            s["file"] = mp if os.path.isabs(mp) else cfg.p(mp)
            if not os.path.exists(s["file"]):
                errors.append(f"shot {n}: map image missing: {s['file']}")
        elif k == "C":
            its = [item(x, n) for x in s["photos"]]
            if not all(its):
                continue
            if len(its) not in (2, 3, 4):
                errors.append(f"shot {n} {r}: a collage takes 2, 3 or 4 photos, got {len(its)}")
            s["files"] = [x["path"] for x in its]
            s["file"] = s["files"][0]
            s["when"] = max(x.get("when", "") for x in its)
        elif k == "R":
            cl = []
            for c in s["clips"]:
                c = c[1:] if len(c) == 5 else c                       # legacy (kind, id, i, date, day)
                it = item(c[0], n)
                if it:
                    cl.append(dict(ref=c[0], i=c[1], date=c[2], day=c[3], file=it["path"], lut=(it["kind"] == "S")))
            if len(cl) != len(s["clips"]):
                continue
            per = (s["frames"] - 22) // max(len(cl), 1)
            if per < 12:
                warns.append(f"shot {n} rewind: only {per} frames per clip; lengthen it or use fewer clips (about 0.9 s each reads well)")
            s["clips"] = cl
            s["file"] = cl[0]["file"]
        # option checks
        if s.get("tr") and s["tr"] not in TRANSITIONS:
            warns.append(f"shot {n} {r}: transition '{s['tr']}' is not in the known-good list; check the exact name in Resolve")
        if s.get("tr") and s["frames"] < 30:
            warns.append(f"shot {n} {r}: {s['frames']} frames is short for a transition; use a hard cut")
        if s.get("mv") and s["mv"] not in MOVES:
            errors.append(f"shot {n} {r}: mv '{s['mv']}' must be one of {sorted(MOVES)}")
        if s.get("mg") and s["mg"] not in MG:
            errors.append(f"shot {n} {r}: mg '{s['mg']}' must be one of {sorted(MG)}")
        if s.get("mg") in ("route", "flight") and not cfg.get(s["mg"]):
            errors.append(f"shot {n} {r}: mg='{s['mg']}' needs a \"{s['mg']}\" section in project.json")
        if s.get("stk") and s.get("mg") == "flight":
            warns.append(f"shot {n} {r}: a sticker on the shot that opens the flight panel can overlap it; put the sticker on the shot before")
        if s.get("stk") and len(s["stk"]) > 34:
            warns.append(f"shot {n} {r}: sticker text is long ({len(s['stk'])} characters); stickers read best under about 25")
        if k == "C" and (s.get("sub") or s.get("subs")):
            warns.append(f"shot {n} {r}: a slide has its own caption strip; a sub= on it would sit on top of that")
        if s.get("badge") and not os.path.exists(os.path.join(cfg["cut"], s["badge"] + ".png")):
            warns.append(f"shot {n} {r}: badge sprite '{s['badge']}' not in {cfg['cut']} yet")
        if k == "C":
            for key in ("title", "note", "cap"):
                if len(s.get(key) or ()) != 2:
                    errors.append(f"shot {n} {r}: collage {key} takes two strings (title=(en, lang2), note=(line1, line2), cap=(en, lang2))")
        elif s.get("title") and len(s["title"]) not in (3, 5):
            errors.append(f"shot {n} {r}: title takes (main, lang2, small) or (main, lang2, small, script_top, tagline)")
        if s.get("lower") and len(s["lower"]) != 3:
            errors.append(f"shot {n} {r}: lower takes (NAME, scientific name, lang2)")
        if s.get("card") and " · " not in s["card"][0]:
            errors.append(f"shot {n} {r}: card text must look like 'DAY 1 · 16 FEB · PLACE — PLACE'")
        if s.get("sub"):
            if len(s["sub"]) != 3:
                errors.append(f"shot {n} {r}: sub takes (en, lang2, span)")
            elif n + s["sub"][2] > len(shots):
                warns.append(f"shot {n} {r}: caption span runs past the last shot")
        for x in s.get("subs", []):
            if len(x) != 4 or not (0 <= x[0] < x[1] <= s["d"] + 0.01):
                errors.append(f"shot {n} {r}: subs entries are (t0, t1, en, lang2) with 0 <= t0 < t1 <= shot length")
        if k in ("S", "V", "SV", "A", "P") and s["d"] > 6 and not s.get("subs") and not s.get("title"):
            warns.append(f"shot {n} {r}: {s['d']}s is long for a single shot without speech; consider splitting or a D() sequence")
    # documentary groups must be contiguous and start with a name title
    seen = set()
    for a, b in zip([None] + shots, shots):
        g = b.get("doc")
        if g and (a is None or a.get("doc") != g):
            if g in seen:
                warns.append(f"shot {b['n']}: documentary group '{g}' appears twice; cinema bars are drawn once per contiguous run")
            seen.add(g)
            if not b.get("lower"):
                warns.append(f"shot {b['n']}: documentary group '{g}' starts without a lower=(NAME, scientific, lang2) title")
    os.makedirs(cfg["out"], exist_ok=True)
    with open(cfg["edit_list"], "w", encoding="utf-8") as f:
        json.dump(shots, f, ensure_ascii=False, indent=1)
    # ---- date / order check: every dated shot must be filmed on its chapter's date, and in time order ----
    prev, flags = None, []
    chk = os.path.join(cfg["out"], f"date_check_{cfg['version']}.txt")
    with open(chk, "w", encoding="utf-8") as o:
        for s in shots:
            d = s["day"]
            flag = ""
            if d and d[1] and s["when"]:
                if s["when"][:10] != d[1]:
                    flag += " DATE!"
                if prev and prev["day"] == d and prev["when"] and s["when"] < prev["when"]:
                    gap = (datetime.datetime.fromisoformat(prev["when"]) - datetime.datetime.fromisoformat(s["when"])).total_seconds() / 60
                    if gap > 20:
                        flag += f" ORDER(-{gap:.0f}min)"
            elif d and d[1] and s["kind"] in "SVDAP" and not s["when"]:
                flag += " NOTIME"
            line = f"{s['n']:3d} {s['kind']:2s} {s['ref']:12s} day={d[0] if d else ''} when={s['when']}{flag}"
            o.write(line + "\n")
            if flag:
                flags.append(line)
            if d and d[1] and s["when"]:
                prev = s
    secs = t / FPS
    real = [s for s in shots if s["kind"] not in ("R", "C", "M")]
    print(f"{len(shots)} shots  {secs:.1f}s = {int(secs // 60)}:{secs % 60:04.1f}  avg {secs / max(len(shots), 1):.2f}s  "
          f"(plain shots avg {sum(s['d'] for s in real) / max(len(real), 1):.2f}s)")
    print("kinds      ", dict(Counter(s["kind"] for s in shots)))
    print("transitions", dict(Counter(s.get("tr", "cut") for s in shots)))
    print(f"captions    {sum(1 for s in shots if s.get('sub')) + sum(len(s.get('subs', [])) for s in shots)}  "
          f"cards {sum(1 for s in shots if s.get('card'))}  labels {sum(1 for s in shots if s.get('sp') or s.get('lower'))}  "
          f"stickers {sum(1 for s in shots if s.get('stk'))}  badges {sum(1 for s in shots if s.get('badge'))}")
    print(f"date check  {len(flags)} flagged  -> {chk}")
    for l in flags:
        print("  " + l)
    for w in warns:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    print(f"edit list   {cfg['edit_list']}   errors {len(errors)}  warnings {len(warns)}")
    return 1 if errors else 0


if __name__ == "__main__":
    cfg = vk.load()
    path = sys.argv[1] if len(sys.argv) > 1 else cfg.p(f"edl_{cfg['version']}.py")
    if not os.path.exists(path):
        sys.exit(f"EDL file not found: {path}")
    with open(path, encoding="utf-8") as f:
        code = compile(f.read(), path, "exec")
    exec(code, dict(VOCAB))
    if not shots:
        sys.exit("the EDL file defined no shots")
    sys.exit(finish(cfg))
