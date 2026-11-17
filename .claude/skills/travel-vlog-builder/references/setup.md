# Setup: tools, project folder, `project.json`, inventory

Contents: [Tools](#tools) · [Project folder](#project-folder) · [project.json](#projectjson) ·
[Inventory and time zones](#inventory-and-time-zones) · [Script list](#script-list)

## Tools

| Need | Check | If missing |
|---|---|---|
| Python 3.9+ with Pillow and numpy | `python -c "import PIL, numpy; print(PIL.__version__, numpy.__version__)"` | ask the user before installing; a virtual environment inside `<P>\_work\venv` keeps it contained |
| ffmpeg and ffprobe on PATH | `ffmpeg -version` | ask the user to install ffmpeg |
| DaVinci Resolve (Studio) open, with its MCP tools | tool search "resolve script"; then `r00_check` | everything up to rendered shots still works; say the timeline cannot be built |
| Epidemic Sound tools (optional) | tool search "epidemic" | ask the user for music files, or leave A2 empty and say so |
| Image generation (optional) | on this user's PC `%USERPROFILE%\.claude\skills\chatgpt-image\gen-image.ps1` | slides use a plain paper background; skip badges, vehicle, plane and parade, or ask for illustrations |
| PDF to text for itineraries (optional) | `markitdown file.pdf -o file.txt` | ask the user for a text copy |

Optional Python extras, used only if already installed: `rawpy` (full-quality RAW development; otherwise the
embedded preview is used), `pillow_heif` (HEIC photos; otherwise ffmpeg converts them). Reference videos from the
web need a downloader the user must approve; a few screenshots or a screen recording from the user also work.

Shell notes (Windows PowerShell): quote every path; run scripts as `python -I -X utf8 "<K>\script.py" --project "<P>" ...`;
long jobs go in the background; write text files as UTF-8 without BOM.

## Project folder

One folder per video project, **outside** the originals (the original used a cloud-synced folder with a 200 GB
budget; an 8-minute version takes 3–4 GB, the whole project about 22 GB).

```
<P>\
  project.json              configuration (below)
  catalog.csv               every usable file with id and true capture time     (inventory.py)
  PROGRESS.md               requests, state, decisions, unverified items
  edl_v1.py, edl_v2.py ...  the edit list of each version                       (you write these)
  edit_list_v1.json ...     built edit list                                     (build_edl.py)
  music_plan.json           music placement                                     (you write this)
  Clips\  Photos\           copies of camera clips; chosen camera photos in the photo look (style.py)
  <phone folder>\           phone photos and videos as exported (never modified)
  Graphics\route-map.png    Graphics\mg\*.png sheets and backgrounds   Graphics\mg\cut\*.png sprites
  Music\  Subtitles\
  v1\ v2\ ...               per version: shots\, overlays\, build_<v>.json, date_check_<v>.txt
  _work\                    scratch: sheets, thumbnails, previews, stills, reports
```

Camera cards and photo libraries stay where they are and are only read. Copy camera clips you will use into
`Clips\` (so Resolve does not depend on a removable drive); name copies `<anything>_<clip id>.MP4`.

## project.json

Copy `assets/project.example.json` and edit. All keys:

| Key | Meaning |
|---|---|
| `name` | video name; the Resolve timeline is "`<name> <version>`" |
| `version` | `"v1"`, `"v2"`...; change it to start a new cut |
| `fps`, `width`, `height` | timeline format; must equal the Resolve project's. Graphics are laid out for 1920 × 1080. Use 25 fps when the main camera films 50 fps (PAL), 30 for 60 fps footage. |
| `handles` | spare frames at each end of prepared shots (12) |
| `utc_offset` | the trip's time zone, e.g. `"+02:00"`; all capture times are converted to it |
| `camera_utc_offset` | the zone the camera clock was set to, used only for photos that store no offset |
| `day1` | date of Day 1 (`"YYYY-MM-DD"`), for candidate ids like `D4-18` |
| `lang2` | second caption language code (`"zh"`), `""` for English only |
| `lut` | `.cube` look for main-camera clips, used by the render scripts; `resolve_lut` = the same file's path inside Resolve's LUT folder. Leave both out if the clips need no grade. |
| `look` | overrides for the photo look sliders (see `style.py`), e.g. `{"shadows": 60}` |
| `sources` | where the media is (below) |
| `fonts`, `fonts_dir` | font overrides by role |
| `workers` | parallel render processes (6; fewer on a small machine) |
| `year` | not required; write full dates in the rewind clips instead |
| `route`, `flight`, `vehicle`, `parade`, `badge_label` | motion graphics, see `references/design.md` |

## Inventory and time zones

```json
"sources": [
  {"path": "iCloud Photos", "photos": "P", "videos": "V"},
  {"path": "Clips", "videos": "S", "ids": "suffix", "sidecars": "E:/Camera cards/Trip"},
  {"path": "Photos", "photos": "A", "ids": "prefix"}
]
```

- `path`: folder, relative to the project or absolute, scanned with subfolders. `photos` / `videos`: the kind
  letter for what is found there (leave one out to ignore that type). Kinds: `P` phone photo, `V` phone video,
  `S` main-camera clip, `A` main-camera photo already rendered in the photo look.
- `ids`: `"seq"` (default) numbers by capture time (`P1`, `V1`...); `"suffix"` takes the part after the last `_`
  (`Day1_C0028.MP4` → `C0028`); `"prefix"` the part before the first `_` (`D1-08_AFR02432.jpg` → `D1-08`); `"stem"`.
- `sidecars`: where the camera's `C0028M01.XML` files are, if not next to the clips (Sony stores the capture time there).
- Per source, optional: `camera_utc_offset`, `shift_hours` (a clock that was simply wrong), `allow_mtime` (last
  resort; marked unreliable).

Run `inventory.py` (add `--dry-run` to only report). **Ids are stable**: re-running after adding files keeps every
existing id, so edit lists stay valid. `--force` renumbers and should not be used once an edit list exists.

Read its report:

- the per-kind counts and the list by day: do the days match the itinerary?
- `src` column: `exif`, `xml`, `qt-local` are reliable; `exif-assumed` used `camera_utc_offset` (check one photo
  against something known); `qt-utc` is usually right for phones; `none` / `mtime` cannot be trusted for ordering.
- warnings: files without a time, id collisions, unreadable files.

Typical trap: the camera clock was left on home time. The offset stored in each photo makes the conversion
automatic; if no offset is stored, set `camera_utc_offset`. A photo "taken at 03:00" is the sign of a wrong offset.

For chosen camera photos, `style.py` writes `_work\styled.csv` with each id's capture time; run `inventory.py`
again afterwards so the `A` entries appear with their true times.

## Script list

| Script | Purpose |
|---|---|
| `vk.py` | print configuration, fonts in use, ffmpeg check |
| `inventory.py` | `catalog.csv` with ids and true capture times |
| `capture_time.py` | time reader used by the above; `--selftest`; or give it files to inspect |
| `analyze_template.py` | measure reference videos; frame sheets |
| `score_photos.py` | `scan` / `pick`: shortlist photos from thousands; candidate sheets |
| `clip_sheet.py` | `videos` / `photos`: sheets to see what each clip and photo shows |
| `style.py` | render chosen photos in the photo look |
| `sheet.py` | contact sheet from any list of images or video frames |
| `build_edl.py` | edit list → JSON, with date and sanity checks |
| `cut_sheet.py`, `map_grid.py` | illustration sheets → sprites; grid for reading map coordinates |
| `prep.py` | `test` / `all` / `prune`: render shots, overlays, captions, subtitles, build file |
| `preview_frames.py` | composited check frames on a sheet |
| `validate.py` | every rendered file present and correct |
| `mix.py` | music bed from `music_plan.json` |
| `resolve_script.py` | print each Resolve step (`resolve/r00` … `r08`) ready to send |
| `gfx.py`, `special.py`, `kb.py` | libraries: drawing, special shots, photo motion |

Each script's own header (first lines of the file) states its exact usage and output.
