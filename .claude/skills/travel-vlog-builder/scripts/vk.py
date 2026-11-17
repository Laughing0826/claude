"""vk - shared configuration and small helpers for the vlog kit.

Every script in this folder starts with `import vk; cfg = vk.load()`.
The project folder holds `project.json` (see assets/project.example.json). It is found, in order, from:
  1. `--project <folder or project.json>` on the command line (removed from sys.argv),
  2. the VLOG_PROJECT environment variable,
  3. the current working directory.

Only Pillow, numpy and the ffmpeg/ffprobe command-line tools are required.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "name": "Travel Vlog",
    "version": "v1",
    "fps": 25,
    "width": 1920,
    "height": 1080,
    "handles": 12,              # spare frames at each end of every prepared shot, so transitions have material
    "utc_offset": "+00:00",     # the trip's local time zone; capture times are converted to it
    "lang2": "zh",              # second caption language (shown ABOVE the English line); "" for English only
    "lut": None,                # optional .cube applied to main-camera clips (kinds S, SV, D)
    "fonts_dir": None,          # extra folder searched first for fonts
    "fonts": {},                # role -> file name, overriding the defaults in FONT_ROLES
    "workers": 6,
    "year": "",                 # appended to dates in the rewind intro, e.g. "2026"
    "route": None,              # route-map animation, see references/design-spec.md
    "flight": None,             # flight-path animation
    "vehicle": "truck",         # sprite (Graphics/mg/cut/<name>.png) that drives the route and the title
    "parade": None,             # list of [sprite, height_px] for the end-card parade
    "badge_label": "Spotted!",
    "look": {},                 # overrides for style.LOOK (the photo look recipe)
}

# role -> candidate file names, first existing wins (Windows names first, then macOS, then Linux)
FONT_ROLES = {
    "SERIF_B": ["georgiab.ttf", "Georgia Bold.ttf", "LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf"],
    "SERIF": ["georgia.ttf", "Georgia.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"],
    "SERIF_I": ["georgiai.ttf", "Georgia Italic.ttf", "LiberationSerif-Italic.ttf", "DejaVuSerif.ttf"],
    "SERIF_BI": ["georgiaz.ttf", "Georgia Bold Italic.ttf", "LiberationSerif-BoldItalic.ttf", "DejaVuSerif-Bold.ttf"],
    "SCRIPT": ["segoesc.ttf", "SnellRoundhand.ttc", "LiberationSerif-Italic.ttf", "DejaVuSerif.ttf"],
    "SCRIPT_B": ["segoescb.ttf", "SnellRoundhand.ttc", "LiberationSerif-BoldItalic.ttf", "DejaVuSerif-Bold.ttf"],
    "HAND": ["Inkfree.ttf", "Bradley Hand Bold.ttf", "LiberationSans-Italic.ttf", "DejaVuSans.ttf"],
    "ZH": ["msjhbd.ttc", "PingFang.ttc", "NotoSansCJK-Bold.ttc", "wqy-zenhei.ttc"],
    "ZH_K": ["kaiu.ttf", "Kaiti.ttc", "STKaiti.ttf", "NotoSerifCJK-Regular.ttc", "wqy-zenhei.ttc"],
    "SANS_B": ["segoeuib.ttf", "Arial Bold.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
    "MONO": ["consolab.ttf", "Menlo.ttc", "DejaVuSansMono-Bold.ttf", "LiberationMono-Bold.ttf"],
}

_cfg = None
_font_index = None


class Cfg(dict):
    """dict with attribute access plus derived paths."""
    __getattr__ = dict.get

    def p(self, *parts):
        return os.path.join(self["base"], *parts)


def _find_project(argv):
    path = None
    if "--project" in argv:
        i = argv.index("--project")
        path = argv[i + 1]
        del argv[i:i + 2]
    path = path or os.environ.get("VLOG_PROJECT") or os.getcwd()
    if os.path.isdir(path):
        path = os.path.join(path, "project.json")
    return os.path.abspath(path)


def load(argv=None):
    """Read project.json and return the configuration (cached)."""
    global _cfg
    if _cfg is not None:
        return _cfg
    pj = _find_project(sys.argv if argv is None else argv)
    if not os.path.exists(pj):
        sys.exit(f"project.json not found at {pj}. Pass --project <folder> or set VLOG_PROJECT. "
                 f"Copy assets/project.example.json to start one.")
    with open(pj, encoding="utf-8") as f:
        user = json.load(f)
    c = Cfg(DEFAULTS)
    c.update(user)
    c["project_json"] = pj
    c["base"] = os.path.abspath(user.get("base") or os.path.dirname(pj))
    v = c["version"]
    c["out"] = c.p(v)                          # everything rendered for this cut
    c["shots"] = c.p(v, "shots")
    c["overlays"] = c.p(v, "overlays")
    c["work"] = c.p("_work")                   # scratch: CSVs, contact sheets, test frames
    c["graphics"] = c.p("Graphics")
    c["mg"] = c.p("Graphics", "mg")            # generated illustrations and backgrounds
    c["cut"] = c.p("Graphics", "mg", "cut")    # transparent sprites cut from the sheets
    c["music"] = c.p("Music")
    c["subs"] = c.p("Subtitles")
    c["catalog"] = c.p("catalog.csv")
    c["edit_list"] = c.p(f"edit_list_{v}.json")
    c["build"] = c.p(v, f"build_{v}.json")
    c["W"], c["H"], c["FPS"], c["HD"] = int(c["width"]), int(c["height"]), int(c["fps"]), int(c["handles"])
    os.environ["VLOG_PROJECT"] = pj            # so worker processes resolve the same project
    _cfg = c
    return c


def ensure_dirs(*names):
    c = load()
    for n in names:
        os.makedirs(c[n], exist_ok=True)


# ---------------------------------------------------------------- fonts
def _index_fonts():
    global _font_index
    if _font_index is not None:
        return _font_index
    c = load()
    home = os.path.expanduser("~")
    dirs = [c.get("fonts_dir"), r"C:\Windows\Fonts", os.path.join(home, "AppData", "Local", "Microsoft", "Windows", "Fonts"),
            "/System/Library/Fonts", "/Library/Fonts", os.path.join(home, "Library", "Fonts"),
            "/usr/share/fonts", os.path.join(home, ".fonts")]
    idx = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".ttc", ".otf")):
                    idx.setdefault(f.lower(), os.path.join(root, f))
    _font_index = idx
    return idx


def font_path(role):
    """Path of the font file for a role such as 'SERIF_B' (see FONT_ROLES), honouring project.json overrides."""
    c = load()
    idx = _index_fonts()
    names = ([c["fonts"][role]] if role in c.get("fonts", {}) else []) + FONT_ROLES[role]
    for n in names:
        if os.path.isabs(n) and os.path.exists(n):
            return n
        if n.lower() in idx:
            return idx[n.lower()]
    sys.exit(f"No font found for role {role}; tried {names}. Set \"fonts\": {{\"{role}\": \"<file>\"}} in project.json.")


def font_report():
    """role -> file actually used. Print this once per project: a fallback font changes the look."""
    return {r: os.path.basename(font_path(r)) for r in FONT_ROLES}


# ---------------------------------------------------------------- ffmpeg helpers
def run(cmd, cwd=None, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if check and r.returncode:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-400:]}")
    return r


def probe(path):
    """dict(w, h, rot, fps, dur, audio) of a media file; w/h are the DISPLAYED size (rotation applied)."""
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height,r_frame_rate,avg_frame_rate:stream_side_data=rotation:stream_tags=rotate:format=duration",
             "-of", "json", path], check=False)
    try:
        j = json.loads(r.stdout or "{}")
    except ValueError:
        j = {}
    out = dict(w=0, h=0, rot=0, fps=0.0, dur=0.0, audio=False)
    for s in j.get("streams", []):
        if s.get("codec_type") == "audio":
            out["audio"] = True
        elif s.get("codec_type") == "video" and not out["w"]:
            w, h = int(s.get("width", 0)), int(s.get("height", 0))
            rot = 0
            for sd in s.get("side_data_list", []):
                if "rotation" in sd:
                    rot = abs(int(float(sd["rotation"])))
            if not rot and "rotate" in s.get("tags", {}):
                rot = abs(int(float(s["tags"]["rotate"])))
            if rot in (90, 270):
                w, h = h, w
            fr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            if fr in ("0/0", "0/1"):
                fr = s.get("r_frame_rate") or "0/1"
            a, b = (fr.split("/") + ["1"])[:2]
            out.update(w=w, h=h, rot=rot, fps=(float(a) / float(b)) if float(b) else 0.0)
    try:
        out["dur"] = float(j.get("format", {}).get("duration", 0) or 0)
    except ValueError:
        pass
    return out


def count_frames(path):
    r = run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
             "stream=nb_read_packets", "-of", "csv=p=0", path], check=False)
    try:
        return int(r.stdout.strip().split(",")[0])
    except ValueError:
        return 0


def lut_local():
    """Copy the project's LUT into the work folder as look.cube and return that folder.

    ffmpeg's lut3d filter cannot take a Windows path without painful escaping, so every ffmpeg call that
    uses the LUT runs with cwd=<work> and refers to it simply as 'look.cube'. Returns None if no LUT is set."""
    c = load()
    if not c.get("lut"):
        return None
    os.makedirs(c["work"], exist_ok=True)
    dst = os.path.join(c["work"], "look.cube")
    src = c["lut"] if os.path.isabs(c["lut"]) else c.p(c["lut"])
    if not os.path.exists(src):
        sys.exit(f"LUT not found: {src}")
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        shutil.copyfile(src, dst)
    return c["work"]


def tc(frames, fps=None):
    """Frame count -> SRT time stamp."""
    fps = fps or load()["FPS"]
    ms = round(frames * 1000 / fps)
    h, r = divmod(ms, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


if __name__ == "__main__":
    c = load()
    print(json.dumps({k: c[k] for k in ("name", "version", "base", "out", "fps", "width", "height", "handles", "utc_offset", "lang2", "lut")}, indent=1, ensure_ascii=False))
    print("fonts:", json.dumps(font_report(), indent=1))
    for tool in ("ffmpeg", "ffprobe"):
        print(tool, "->", shutil.which(tool) or "NOT FOUND")
