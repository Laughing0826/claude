---
name: travel-vlog-builder
description: Build or revise a long-form travel vlog (trip recap, safari or holiday film, photo-and-clip slideshow) from the user's own photos and video clips, delivered as an editable DaVinci Resolve timeline. Covers checking real capture dates against the itinerary, choosing photos and clips, an edit list with template-style pacing, a VHS rewind intro, day cards, location tags, name labels, stickers, bilingual captions, documentary-style sequences, scrapbook slides, illustrated motion graphics, a music bed that dips under speech, transitions and stabilisation (tested scripts for each step). Use this skill whenever the user wants a video made or changed from their footage, or mentions a vlog, DaVinci Resolve, a timeline, subtitles or captions for a video, music for a video, motion graphics, "make it like these videos", more animals or photos in the video, fixing the order or dates, a new cut (v2, v3...) or continuing an earlier video project - even when the request is only one part of this ("add music to the vlog").
---

# Travel vlog builder

This skill records how a strong first result was produced, so the same quality can be reached again by following it.
The method is **edit by data, verify by looking**:

1. Everything the video contains is written down in one edit list (a small Python file, one line per shot).
2. Scripts turn that list into finished shot files and transparent graphics, with numbers that can be checked.
3. DaVinci Resolve is driven by script to assemble those files into an ordinary, editable timeline.
4. You cannot watch video or hear audio. So after every stage you **look at still frames** and **check counts and
   durations**, and you tell the user plainly what was never seen or heard.

Folders: `<K>` is this skill's `scripts` folder. `<P>` is the project folder (holds `project.json`). Run every script as

```
python -I -X utf8 "<K>\<script>.py" --project "<P>" <arguments>
```

`-I` (isolated) and `-X utf8` matter on Windows: they keep stray files from being imported and keep Chinese text intact.
The scripts need only Python 3.9+, Pillow, numpy and ffmpeg/ffprobe on PATH. Do not install anything (Python packages,
downloaders, converters) without telling the user what and why and getting a yes; this user checks installs for safety.

## What good looks like

These are the habits that made the original result good. Each one exists because skipping it caused, or would have
caused, a visible mistake.

- **Measure instead of guessing.** Reference videos are measured (cut rhythm, structure). Dates come from the
  capture time inside each file, converted to the trip's time zone, never from folder names or file dates. In the
  original, folders named by day held clips from other days, and five scenes had been placed on the wrong day.
- **One source of truth.** Change the edit list and re-render; do not patch the timeline by hand for anything the
  edit list can express. Then every later version can be rebuilt and every number in your report is real.
- **Test one of each, look, then render all.** A full render takes minutes; a test of one shot per new element takes
  seconds. Looking at the test frames caught an unreadable slide title and a counter covering the map's labels.
- **Check every step with numbers.** After each Resolve step compare what came back with what you expected (items
  appended, start frame and length of every shot, last subtitle end). A wrong subtitle offset was caught this way.
- **Keep the user's work safe.** Never modify, move or delete originals. Never overwrite an earlier cut: each round
  is a new version (`v2`, `v3`) with its own folder and its own timeline; earlier timelines stay in the project.
- **Fold new requests in; drop none.** Users add wishes while you work. Add each to the request list in
  `PROGRESS.md`, acknowledge it in one line, fit it into the current plan, and account for every one in the final
  report.
- **A missing label is better than a wrong one.** If you are not sure of a species, place, date or spoken word,
  leave the label off or mark it, and list it under "please check". Never present a guess as fact.
- **Say what you could not verify.** Sound is never heard. Stabilisation is never watched. Auto-transcribed speech
  may be wrong. State these every time; do not write "done" where you mean "built but unheard".
- **Use waiting time.** Start slow jobs in the background (image generation, the full render, music fitting) and do
  the next independent thing meanwhile.

## Before you start

1. **Read what exists.** If `<P>\PROGRESS.md`, earlier `edl_v*.py` files or memory notes about this video exist, read
   them first and continue from there. Ask Resolve what is open (`r00_check`, below).
2. **Check the tools** and tell the user in one line each if something is missing:
   - `python -I -X utf8 "<K>\vk.py" --project "<P>"` prints the configuration, the fonts that will be used and
     whether ffmpeg is found. A fallback font changes the look; on Windows the intended fonts are present.
   - DaVinci Resolve Studio running with the project open, and its MCP tools: `run_script`, `run_script_unsafe`,
     `search_scripting_api` (find them with a tool search for "resolve script"). Without Resolve you can still do
     everything up to the rendered shots; say so.
   - Optional: Epidemic Sound tools for music (`SearchRecordings`, `EditRecording`, ...); an image-generation tool
     for illustrations (on this user's PC: `%USERPROFILE%\.claude\skills\chatgpt-image\gen-image.ps1`).
3. **Create the project** if new: a working folder outside the originals, `project.json` copied from
   `assets/project.example.json` and edited (see `references/setup.md`). Ask only for what you cannot find out:
   where the footage is, the itinerary or dates, the languages for captions, any reference videos, and a disk budget.
4. **Start `PROGRESS.md`** in `<P>` with: the request list (numbered, each with a status), decisions, open questions.
   Keep it current; it is how the work survives a new session.

## The workflow

Work through the phases in order. Each ends with a gate: do not go on until it holds. In a revision round, start at
the earliest phase the new requests touch. Details for each phase are in the reference files named in brackets.

### 1. Inventory and true dates  [`references/setup.md`]

```
inventory.py                       -> <P>\catalog.csv  (id, kind, path, when, dur, w, h, fps, src)
```

Every usable file gets a stable id (`P12` phone photo, `V7` phone video, `C0016` camera clip, `D4-18` chosen camera
photo). `when` is the capture time in the trip's time zone. Read the warnings: files with no embedded time, and
times that had to assume the camera's time zone. Read the itinerary (convert a PDF to text first) and write a day
table into `PROGRESS.md`: day number, date, places, distances. Note anything in the itinerary that contradicts the
bookings and use the booked fact.

Gate: every file you intend to use has a trustworthy `when`, and you have the day table.

### 2. Study the references  [`references/editorial.md`]

If the user named template videos or sent example images, measure and look before designing:

```
analyze_template.py <video> ...    -> cut rhythm, cold-open length, frame sheets in <P>\_work\templates
```

Open the frame sheets and the user's images. Write down, concretely, what to copy: opening style, shot length,
caption position and size, labels, stickers, maps, music use. If nothing was provided, use the defaults in
`references/editorial.md` (they come from five popular travel vlogs).

Gate: a short "what the references look like" list is in `PROGRESS.md`.

### 3. Choose the media  [`references/editorial.md`]

```
score_photos.py scan <folder> ...  -> sharpness and exposure for every photo
score_photos.py pick               -> best frame of each burst, top 48 per day, sheets cand_D<n>.jpg
clip_sheet.py videos               -> one frame sheet per clip (to see content and choose in-points)
clip_sheet.py photos               -> day-by-day thumbnail sheets of phone photos
style.py <outdir> 3840 @list.txt   -> chosen camera photos rendered in the user's photo look
```

Look at the sheets. Pick by eye for story as well as sharpness: animals and landscapes, but also people, food,
rooms, vehicles, signs, arrivals and sunsets, because those make it a trip and not a slideshow. For each clip you
plan to use, note what it shows and the good seconds. Re-run `inventory.py` after rendering styled photos.

Gate: you have looked at every clip and photo you will use; nothing is chosen from its file name alone.

### 4. Write the edit list  [`references/edl.md`, `references/editorial.md`]

Write `<P>\edl_<version>.py` (start from `assets/edl.example.py`), then:

```
build_edl.py                       -> <P>\edit_list_<version>.json, <version>\date_check_<version>.txt, a report
```

Fix every `ERROR`. Go through every `DATE!`, `ORDER` and `NOTIME` flag and every `WARN`: either fix it or write
down why it is intended (for example a flight photo placed after the landing on purpose). Compare the printed
totals with the targets from phase 2 (length, average shot, share of hard cuts).

Gate: zero errors; every flag fixed or explained in `PROGRESS.md`.

### 5. Graphics assets  [`references/design.md`]

Only what the edit list uses: illustration sheets for badges, vehicle, plane and parade (generate, then
`cut_sheet.py`, then look at the contact sheet); scrapbook backgrounds `Graphics\mg\scrap_bg1.png`, `scrap_bg2.png`;
the route map and its pin and road coordinates (`map_grid.py`, read the numbers off the grid, put them in
`project.json`). Start image generation in the background early; it is slow.

Gate: every sprite named in the edit list exists and looks whole on the contact sheet.

### 6. Test render and look

```
prep.py test n1,n2,...             one shot of EACH kind and each graphic type used (title, card, tag, label,
                                   sticker, badge, route, flight, parade, collage sizes, documentary cut, caption)
preview_frames.py auto --test      -> <P>\_work\preview_sheet.jpg  (shot + overlays composited as the viewer sees them)
```

Open the sheet. Check, element by element: readable on its background, nothing covering a face or the subject or
another graphic, text not clipped, second language rendered (no empty boxes), colours and position consistent,
map graphics sitting on the map's roads. Fix the code or the edit list and repeat until right.

Gate: you have seen every element type correct in a composited frame.

### 7. Full render and validation

```
prep.py all                        run in the background; about 1 minute per minute of video on a fast PC
validate.py                        every shot and overlay exists, has the right number of frames, has alpha
```

While it runs, do phase 8. Afterwards read the tail of the render output for `SHOT ERR`, `OVERLAY ERR`,
`CAPTION ERR`, then run `validate.py`. Re-run `prep.py all` after any fix (only changed items render).

Gate: `validate.py` prints `bad 0`.

### 8. Music  [`references/music.md`]

List chapter starts and speech shots from the edit list. Choose one track per section (opening, each group of
days, the ending), instrumental, fitted to the section length. Download, **check every file's duration**, write
`<P>\music_plan.json`, then:

```
mix.py                             -> one music bed WAV: crossfades, dips under speech, ends with the video
```

Read its warnings (gaps, truncated files, clipping). Ask before using the user's music account the first time.
If the edit list changes length later, re-fit and re-mix.

Gate: the bed is as long as the video, with no warning left unexplained.

### 9. Build the timeline in Resolve  [`references/resolve.md`]

For each step, print the script and send the whole text to the Resolve tool named in its first line:

```
resolve_script.py r00_check            read-only: project, frame rate, timelines
resolve_script.py r01_import           repeat until every "remaining" is 0
resolve_script.py r02_timeline         expect appended == expected, nbad == 0, end_s == expected_end_s
resolve_script.py r03_transitions      expect total == expected, fail == []
resolve_script.py r04_stabilize        repeat with --only <pending numbers> until pending == []
resolve_script.py r05_overlays_music   expect tracks == expected_tracks, music dur_s == video length
resolve_script.py r06_subtitles        expect last end == expect_last_end_s; tracks left switched off
```

Tool calls end after 60 seconds, so the scripts stop early and report what is left; run them again as told. If a
result has `error`, read it and fix the cause; do not continue past it. The project frame rate must already
match `project.json` (it cannot be changed once a timeline exists). Never run a "once" step twice.

Gate: every step returned the expected numbers.

### 10. Look at the finished timeline

```
resolve_script.py r07_stills           exports about 18 frames from the real timeline
sheet.py "<P>\_work\stills_<version>_sheet.jpg" 3 690 @list.txt
resolve_script.py r08_summary          final counts, saves the project
```

Open the sheet. This is the only view of the true result: transitions, grade, overlays and captions together.
Fix anything wrong (edit list -> render -> rebuild with `r02_timeline --replace` and the following steps).
Send the sheet to the user with the report.

Gate: you have looked at frames from the timeline itself, and `r08_summary` matches the edit list.

### 11. Notes and report

Update `PROGRESS.md` (state, track layout, what changed, not verified, files, tools installed), save a short memory
note pointing at it, and keep `project.json`, `edl_<version>.py` and `music_plan.json` in `<P>` as the record.
Then report in this shape, in plain words, without overclaiming:

```
<One or two sentences: what now exists, where (project and timeline name), its length, and the most important
 thing that is untested. Say that earlier versions are untouched.>

## What's in <version>
- **<Request or feature>:** what was done, in viewer terms.   (one bullet per request in the request list)

## Please check
1. **Sound.** Never listened to: music was chosen by tags; levels and dips are untested.
2. **<Auto-transcribed captions, with times>.**
3. **Things I assumed:** <each fact you could not confirm>.
4. **Names I was not sure of** are shown without a label.
5. **Stabiliser.** Not reviewed clip by clip; how to switch it off for one clip.
6. <Anything else the user must do or decide: subtitle style, final export.>

<Where the date check and notes are. Disk used.>
```

Leave the final export (Deliver page) to the user unless they ask for it.

## Revision rounds

A request to change an existing video is a new version, not a patch:

1. Add the requests to `PROGRESS.md`. Set `"version"` in `project.json` to the next number.
2. Copy `edl_v<old>.py` to `edl_v<new>.py` and edit the copy. The old file stays as the record of the old cut.
3. Rebuild from the earliest affected phase. `prep.py all` renders into the new version's own folder, and the new
   timeline gets the new name; the old folder and the old timelines stay as they are.
4. In the report, list what changed since the previous version and why (for example every clip that moved day).

Typical requests and where they land: "more animals" -> phases 3-4 (more picks, slides, badges); "check the dates"
-> phases 1 and 4; "add music" -> phase 8 then steps r01 and r05; "both languages" -> captions in the edit list;
"it is shaky" -> r04; "documentary style" -> `D()` sequences; "fancier text / intro" -> phase 5-6 design work.

## When something is not covered

The scripts are meant to be edited. To add a new graphic or shot type, read `references/design.md`, write it next to
the similar existing one in `prep.py` or `special.py`, test-render it, and look at it before using it widely. For
any Resolve call not in `references/resolve.md`, look it up with `search_scripting_api` first, try it on one item,
check the result, then apply it to all.

## Reference files

| File | Read it when |
|---|---|
| `references/setup.md` | starting a project: prerequisites, `project.json` fields, folder layout, inventory and time zones |
| `references/editorial.md` | planning and writing the edit: structure, pacing numbers, choosing shots, transitions, captions, documentary sequences, slides |
| `references/edl.md` | writing `edl_<version>.py`: every shot kind and option, with examples and limits |
| `references/design.md` | making or changing graphics: each overlay's look and timing, illustration prompts, sprite cutting, map coordinates |
| `references/music.md` | music: searching, fitting, downloading, `music_plan.json`, ducking levels, failures seen |
| `references/resolve.md` | building in Resolve: the tools, each step's expected result, API notes, known pitfalls, recovery |
| `references/quality.md` | before reporting: full checklists per phase and the list of mistakes this method prevents |
| `references/worked-example.md` | wanting a concrete model: the numbers and decisions of the original 8-minute safari vlog |
