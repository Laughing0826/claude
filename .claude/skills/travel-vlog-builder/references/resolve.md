# Building the timeline in DaVinci Resolve

Everything here was done, and seen to work, on DaVinci Resolve Studio 21 on Windows through its MCP script tools.
The timeline that results is an ordinary Resolve timeline the user can keep editing by hand.

Contents: [The tools](#the-tools) · [Before the first step](#before-the-first-step) · [The steps](#the-steps) ·
[Track layout](#track-layout) · [Rules for any Resolve script](#rules-for-any-resolve-script) ·
[API used and verified](#api-used-and-verified) · [Problems seen and their fixes](#problems-seen-and-their-fixes) ·
[Rebuilding and recovering](#rebuilding-and-recovering)

## The tools

| Tool | Use it for |
|---|---|
| `run_script` | scripts that only call the Resolve API: no `import`, no files. `r00_check`, `r08_summary`. |
| `run_script_unsafe` | scripts that import `json`, `os`, `time`, read the build file or write files. Every build step. |
| `search_scripting_api` | look up a method before using it for the first time, e.g. `api: DaVinciResolveScript.pyi`, `pattern: stabiliz\|SetTrackEnable`. `get_scripting_api` returns a full type declaration. |

Arguments: `script` (Python source) and `timeout` in seconds (use 60; 30 is enough for the two read-only steps).
Inside a script `resolve` and `project` (the current project) already exist. The tool returns whatever the script
assigned to the global variable `result`, as JSON (tuples become lists, integer keys become strings). Nothing
carries over between calls. If the tools are not in your tool list, search for them ("resolve run_script").

## Before the first step

- Resolve is running with the right project open. If Resolve shows an "update available" prompt, close it without
  updating; do not update the user's software.
- The project's frame rate and size equal `project.json` (`r00_check` shows them). The frame rate cannot be changed
  once the project has a timeline. For a brand-new project set it first with
  `project.SetSetting("timelineFrameRate", "25")` and the two `timelineResolution...` settings (look these up with
  `search_scripting_api`; they were not needed in the original session, so verify the result with `r00_check`).
- If `project.json` has a LUT: the `.cube` file must sit inside Resolve's own LUT folder (for example
  `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\LUT\<subfolder>\`), and `"resolve_lut"` must be that
  path. `"lut"` is the copy the render scripts use. Both must be the same look.
- `prep.py all` and `validate.py` have finished with `bad 0`, and the music bed exists if there is music.

## The steps

Print each script with `python -I -X utf8 "<K>\resolve_script.py" --project "<P>" <step>` and send the **entire
printed text** as `script`. Do not retype or shorten it. Read `result` and compare with the "expect" column before
the next step.

| Step | What it does | Expect in `result` | Repeat? |
|---|---|---|---|
| `r00_check` | project name, frame rate, size, timelines, bins | right project; fps and size match; `target_exists` false on a first build | any time |
| `r01_import` | bins `<version>/Shots`, `/Overlays`, `/Music`, plus `Clips`, `Subtitles`; imports in batches of 40 | every group `remaining: 0`, `missing_files: []` | yes, until all `remaining` are 0 |
| `r02_timeline` | new timeline `<name> <version>`; every shot on V1 at its exact frame; LUT on `S` clips; track name | `appended == expected`, `nbad == 0`, `end_s == expected_end_s`, `luts == expected_luts` | only with `--replace` |
| `r03_transitions` | adds each shot's `tr` at its start | `total == expected`, `fail == []` | **no** |
| `r04_stabilize` | Resolve stabiliser on real video (kinds S, V, SV, D) | `fail == []`; if `pending` is not empty run again with `--only <those numbers>` | yes, until `pending == []` |
| `r05_overlays_music` | tracks V2–V6 with all overlays; music bed on A2; track names | `overlays_added == expected`, `tracks == expected_tracks` (V1 = shot count), `music.dur_s` = video length | **no** |
| `r06_subtitles` | `.srt` files as subtitle tracks (Bilingual, English, second language), moved to the right time, switched off | each `t<k>` shows `expected_items` items, first start = `first`, last end = `expect_last_end_s` | **no** |
| `r07_stills` | exports about 18 representative frames to `<P>\_work\stills_<version>\` | `exported == of`; run again with `--want` for any `pending` | yes |
| `r08_summary` | counts of everything, list of timelines, saves | shots, transitions, per-track counts equal to the edit list; earlier timelines still listed | any time |

Options: `--replace` (r02: delete and rebuild this version's timeline only), `--only 12,15` (r04), `--enable-subs`
(r06: leave text subtitles on, for a version without styled captions), `--want 0:200,1:110` (r07: shot:frame-offset
pairs), `--test` (use the test build file).

After `r07_stills` make the sheet and look at it:

```
Get-ChildItem "<P>\_work\stills_<version>\*.jpg" | ForEach-Object { "$($_.FullName)::$($_.BaseName)" } | Set-Content "<P>\_work\stills_list.txt" -Encoding utf8
python -I -X utf8 "<K>\sheet.py" "<P>\_work\stills_<version>_sheet.jpg" 3 690 "@<P>\_work\stills_list.txt"
```

## Track layout

| Track | Name | Contents |
|---|---|---|
| V1 | Main | every shot, with transitions |
| V2 | Cinema bars | bars over documentary sequences |
| V3 | Titles & labels | titles, day cards, location tags, name labels, documentary titles |
| V4 | Stickers | pop-up stickers |
| V5 | Motion graphics | badges, flight path, route, vehicle, parade |
| V6 | Captions | styled captions, baked as graphics |
| A1 | Clip sound | sound of clips (photos and slides are silent) |
| A2 | Music | one mixed music bed |
| Subtitle 1–3 | Bilingual, English, second language | editable text, **switched off** because V6 shows the same words. To export or restyle text subtitles the user turns one on and V6 off. |

Tell the user: with five overlay tracks a slower PC may stutter until Playback → Render Cache → Smart is on.

## Rules for any Resolve script

- **Stay under 60 seconds.** Give every loop a time budget (`if time.time() - t0 > 40: break`), return what is
  left, and continue in the next call. Import files in batches. Try a slow call on three items and time it before
  running it on all (stabilising took 0.4–0.7 s per clip).
- **Frames are absolute.** `st = tl.GetStartFrame()` (90000 for a 25 fps timeline starting at 01:00:00:00). Write
  `st + frame`; read `value - st`.
- **Source in/out are in source frames.** A 50 fps clip in a 25 fps timeline: `startFrame = round(seconds * 50)`
  made even, `endFrame = startFrame + 2 * timeline_frames`. Pre-rendered shots: `startFrame = head`,
  `endFrame = head + frames`.
- **ASCII only in script text.** Non-ASCII characters typed in a script can fail. Build such strings with `chr()`
  (`chr(0x4e2d) + chr(0x6587)`) or read them from a UTF-8 file. `resolve_script.py` already escapes paths and names.
- **Verify after every change**: count what came back, compare each item's start and length with the plan, count
  items per track. Save with `resolve.GetProjectManager().SaveProject()` at the end of each changing script.
- **Sort and filter V1 items.** After transitions exist, `GetItemListInTrack("video", 1)` also returns items whose
  `GetType()` is `"transition"`. Keep only `"video"`, sort by `GetStart()`, then index by shot number.
- **Set the bin first.** `mp.SetCurrentFolder(bin)` before `ImportMedia` and before `CreateEmptyTimeline`.
- **Names in the media pool** are file names with extension, except `.srt` files, which appear without it.
- **Tracks must exist** before clips are appended to them (`tl.AddTrack("video")`, `tl.AddTrack("audio", "stereo")`,
  `tl.AddTrack("subtitle")`).
- **`mediaType`** in `AppendToTimeline`: 1 = video only (photos, slides, muted clips, all overlays), 2 = audio only
  (music), omitted = picture and sound.
- **No still images on the timeline.** Resolve ignores short still durations and stills have no spare frames for
  transitions; that is why photos, maps and slides are pre-rendered as video. (An earlier attempt also found that
  this Resolve would not import JPG stills.)

## API used and verified

`resolve.GetProjectManager()` · ProjectManager `GetCurrentProject()`, `SaveProject()` · Project `GetName()`,
`GetMediaPool()`, `GetCurrentTimeline()`, `SetCurrentTimeline(tl)`, `GetTimelineCount()`, `GetTimelineByIndex(i)`
(from 1), `ExportCurrentFrameAsStill(path)` · MediaPool `GetRootFolder()`, `AddSubFolder(parent, name)`,
`SetCurrentFolder(folder)`, `ImportMedia([paths])`, `CreateEmptyTimeline(name)`, `AppendToTimeline([info, ...])`,
`DeleteTimelines([tl])` · Folder `GetSubFolderList()`, `GetName()`, `GetClipList()` · Timeline `GetName()`,
`GetStartFrame()`, `GetEndFrame()`, `SetCurrentTimecode("HH:MM:SS:FF")`, `GetItemListInTrack(type, index)`,
`GetTrackCount(type)`, `AddTrack(type[, "stereo"])`, `SetTrackName(type, index, name)`,
`SetTrackEnable(type, index, bool)`, `MoveItems(items, {"trackIndex": k, "startFrame": f})` · TimelineItem
`GetType()`, `GetStart()`, `GetEnd()`, `GetDuration()`, `Stabilize()`, `AddTransition({...})`, `GetNodeGraph()` ·
Graph `SetLUT(1, path)`.

`AppendToTimeline` info keys: `mediaPoolItem`, `startFrame`, `endFrame`, `trackIndex`, `recordFrame`, `mediaType`.

`AddTransition` argument: `{"type": name, "category": "fusion" or "simple", "position": "start", "alignment":
"center" | "right" | "left", "duration": frames}`. Category `"fusion"` for Brightness Flash, Zoom In, Slide Left,
Slide Up, Slide Down, Glitch, Film Strip, Spin, Camera Shake, Foreground Wipe; `"simple"` for the others. Lengths
used: Cross Dissolve 12, Additive Dissolve 16, Dip To Color Dissolve 20, Brightness Flash 8, Glitch 10, others 14.

Used by the step scripts but **not** exercised in the original session (they are standard API; if one fails, look
it up and adjust): `resolve.GetVersionString()`, `project.GetSetting(name)`, `project.RefreshLUTList()`,
`tl.GetStartTimecode()`. `AddTransition`, `Stabilize` and `MoveItems` exist in Resolve 21; on an older Resolve
check with `search_scripting_api`, and if transitions cannot be scripted tell the user to select V1 and press
Ctrl+T for cross dissolves.

## Problems seen and their fixes

| Problem | Fix |
|---|---|
| A transition is refused | The clip lacks spare frames on that side. The step already retries: centred at full length, centred 10, right-aligned 10, left-aligned 10. Remaining failures are listed in `fail`: lengthen the handle (move the in-point later than 0.5 s, or end earlier) or make it a hard cut. |
| Subtitles land at the wrong time | Resolve places an appended `.srt` with its first line at the record frame. The step moves the items so the first line starts at the first caption's own frame, then compares the last line's end with the expected value. If they differ, move again with `MoveItems(items, {"startFrame": st + first})`. |
| Captions appear twice | Text subtitle tracks and styled captions are both on. Keep the subtitle tracks switched off. |
| A step ran out of time | Expected. Run the same step again (r01) or with `--only` (r04) / `--want` (r07). |
| `lost` or `missing_files` in a result | Files were not imported or not rendered. Run `validate.py`, then `r01_import` again. |
| `nbad` is not 0 after r02 | A shot's start or length differs from the plan, usually an `S` clip whose frame rate or in-point was wrong. Fix the edit list (or use `SV`), re-render, rebuild with `--replace`. |
| LUT count is low | The LUT path is not inside Resolve's LUT folder, or `resolve_lut` is wrong. Fix and apply again to `S` clips only. |
| Resolve looks frozen during import or stabilise | It is working; wait for the call to return, then continue with what is `pending`. |
| Exported check frame shows the previous frame | The viewer had not redrawn; the step waits 0.35 s per frame. Increase the pause if it happens. |

## Rebuilding and recovering

- A changed edit list means: `build_edl.py`, `prep.py all`, `validate.py`, re-mix music if the length changed,
  then `r01_import`, `r02_timeline --replace`, `r03` … `r08`. Transitions, stabilisation, overlays and subtitles
  belong to the timeline, so they are all redone on the new one.
- `--replace` deletes only the timeline with this version's name. Never delete or rename another timeline.
- Stabilisation uses Resolve's default settings and was never watched. Tell the user that if a shot warps they can
  switch it off for that clip in the Inspector.
- The final export is left to the user (Deliver page; "Export Subtitle → Burn into video" is only needed if they
  switch the text subtitles on instead of V6) unless they ask you to render.
