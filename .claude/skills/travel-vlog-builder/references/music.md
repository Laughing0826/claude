# Music and sound

You cannot hear. So the music is chosen by description, fitted by duration, mixed by arithmetic, and reported as
**unheard**. The method below produced a five-track bed for an 8-minute video in a few minutes.

Contents: [Plan the sections](#1-plan-the-sections) · [Find tracks](#2-find-tracks) · [Fit to length](#3-fit-each-track-to-its-section) ·
[Download and check](#4-download-and-check) · [Mix](#5-mix-the-bed) · [Clip sound and effects](#clip-sound-and-effects) ·
[Failures seen](#failures-seen) · [What to tell the user](#what-to-tell-the-user)

## 1. Plan the sections

Get the timings from the edit list (after `build_edl.py`): the start of every chapter card, the title, the intro,
the end, and every shot where someone speaks or reacts aloud.

```
python -I -X utf8 -c "import json; E=json.load(open(r'<P>\edit_list_<version>.json',encoding='utf-8')); [print(s['n'], s['ref'], round(s['start']/25,2), round((s['start']+s['frames'])/25,2), (s.get('card') or s.get('title') or [''])[0][:16]) for s in E if s.get('card') or s.get('title') or s.get('subs') or s['kind']=='R']; print('end', (E[-1]['start']+E[-1]['frames'])/25)"
```

Divide the video into sections that each get one track. A new track about every 1½–2½ minutes keeps a long video
fresh; the user asked for **more than three** tracks. The original 8:22 video used five:

| Section | Mood searched | Why |
|---|---|---|
| title and journey out (after the intro) | energetic, upbeat | momentum |
| first days (first wildlife) | African adventure, marimba, percussion | sense of place |
| the scenic day (canyon) | cinematic, peaceful, wonder | landscape |
| the big wildlife days | dreamy, hopeful, steady | carries documentary sequences |
| last day and journey home | warm acoustic, hopeful | ending |

A rewind intro carries its own tape sound; start the first track when the title appears. Change tracks **at a
chapter card**, never in the middle of a scene.

## 2. Find tracks

Epidemic Sound tools (load them with a tool search if needed). Ask the user before using their account the first
time ("Add music from your Epidemic Sound account?"). Search each mood, several at once:

```
SearchRecordings  query: {"term": "upbeat adventure travel vlog safari"}
                  filter: {"duration": {"min": 140000, "max": 260000}, "vocals": false}     (milliseconds)
                  first: 6
```

Optional filter: `"bpm": {"min": 115, "max": 140}`. Each result gives id, title, bpm, length and tags (mood,
genre, "no vocals"). Choose **instrumental** tracks ("no vocals"; avoid "vocal presence") whose tags fit and whose
natural length is at or above the section length. Avoid children's music and comedy tags unless that is the
intended tone. Prefer different artists and tempos for neighbouring sections.

## 3. Fit each track to its section

Epidemic can re-cut a track to an exact length with a proper ending:

```
EditRecording  id: <recording id>
               input: {"targetDurationMs": 96000, "forceDuration": true, "maxResults": 1,
                       "skipStems": true, "downloadAudioFormat": "WAV"}
-> {"recordingEdit": {"id": <job id>, "status": "PENDING"}}

PollEditRecordingJob  id: <job id>
-> status COMPLETED with edit {"id": <edit id>, "durationMs": ...}      (a few seconds; poll again if PENDING)

DownloadRecordingEdit  input: {"editId": <edit id>, "jobId": <job id>}
-> {"assetUrl": "<signed URL, expires>"}
```

Target lengths: section length **plus the overlap** with the next track (2–3 s), and for the last track the length
you want it to run before the end (it will be aligned to end with the video). Start all edits together, then poll.

If a job completes with `"edit": null`, that track could not be cut that way: retry with only
`{"targetDurationMs": ..., "maxResults": 2, "downloadAudioFormat": "WAV"}`, or pick another track.

## 4. Download and check

Download each `assetUrl` straight away (the links expire) into `<P>\Music\<version>\`, with numbered names:

```powershell
$ProgressPreference = 'SilentlyContinue'
Invoke-WebRequest $url -OutFile "<P>\Music\v3\2_Out on a Safari - Artist.wav" -UseBasicParsing
Get-ChildItem "<P>\Music\v3" | ForEach-Object { "{0}  {1:N1} MB  {2}s" -f $_.Name, ($_.Length/1MB), (ffprobe -v error -show_entries format=duration -of csv=p=0 $_.FullName) }
```

**Compare every duration with what you asked for.** In the original one file arrived as 47 s instead of 122 s; an
earlier full-length edit of the same track was used instead. Keep unused downloads in `Music\unused\`.

## 5. Mix the bed

Write `<P>\music_plan.json`, then run `mix.py`. Example (the original mix):

```json
{"out": "Music/South_Africa_v3_music_bed.wav", "lufs": -19, "master": 0.8, "tail_fade": 2.0, "ramp": 0.45,
 "tracks": [
   {"file": "Music/v3/1_Chasing the Top.wav", "start": 15.25, "fade_in": 0.25, "fade_out": 2.5, "stop": {"card": "DAY 1", "offset": 1.6}},
   {"file": "Music/v3/2_Out on a Safari.wav", "start": {"card": "DAY 1", "offset": -0.4}, "fade_in": 1.0, "fade_out": 2.5},
   {"file": "Music/3_Somewhere (116s).wav",   "start": {"card": "DAY 3", "offset": -0.4}, "fade_in": 1.0, "fade_out": 3.0, "expect": 116},
   {"file": "Music/v3/4_A Step Ahead.wav",    "start": {"after_prev": -2.6}, "fade_in": 2.5, "fade_out": 2.0},
   {"file": "Music/v3/5_Rose In The Garden.wav", "start": "end", "fade_in": 1.0, "fade_out": 0.3}],
 "duck": [{"ref": "V1", "db": -12}, {"ref": "V2", "db": -12}, {"ref": "V8", "db": -5}, {"ref": "V64", "db": -6}, {"ref": "V101", "db": -6}]}
```

How to set it:

- **Starts.** First track: the second the title appears (here 15.25, just before the 15.4 s title so it lands on
  the flash). Later tracks: `{"card": "DAY 3", "offset": -0.4}` = 0.4 s before that chapter card, or
  `{"after_prev": -2.6}` = 2.6 s before the previous track ends. Last track: `"end"`, so its own ending lands on the
  last frame.
- **Fades.** In 1.0 s (0.25 s for the opener, 2.5 s when entering under a still-playing track); out 2–3 s where the
  next track overlaps. `"stop"` cuts a track early (the opener stops 1.6 s after Day 1 begins).
- **Ducking** (the music dips while someone speaks): `-12` dB under speech to camera for the whole shot; `-5` to
  `-6` dB under shots with spoken reactions or important ambient sound. Ramps of 0.45 s on both sides.
- **Levels.** Every track is normalised to -19 LUFS, the sum is multiplied by 0.8, and the last 2 s fade out.
  Clip sound is normalised to -20 LUFS when shots are rendered, so speech sits above the dipped music.
- `"expect"` (seconds) makes `mix.py` warn when a file's real length differs.

Read the output: the placement table (each track's start and end), the ducked spans, and the warnings (a gap
without music, a file shorter than expected, a track starting after the end, clipping). Fix the plan until the
only gaps are intended (the intro). Then the bed goes on A2 in step `r05_overlays_music`.

If the video's length changes afterwards, re-fit the affected tracks (step 3) and mix again; anchors given as
cards move by themselves.

## Clip sound and effects

- Phone and camera clips keep their sound unless the shot has `mute=True`. Mute montage shots, wind, engine noise
  and any clip whose sound adds nothing; keep voices, animal calls, water, laughter.
- Photos, maps and slides are silent.
- The rewind intro synthesises its own tape whirr and a click at PLAY (`special._tape_audio`), because the
  library's "VHS tape rewind" effect could not be downloaded on the user's plan. It is synthetic and unheard.

## Failures seen

| What happened | What to do |
|---|---|
| `DownloadRecording` (the original, uncut track) → "You don't have permission to download this asset" | The plan allows fitted edits, not originals. Use `EditRecording` + `DownloadRecordingEdit`. |
| `DownloadSoundEffect` → same permission error | Sound effects are not available on this plan. Synthesise simple effects or do without, and say so. |
| `PollEditRecordingJob` → COMPLETED but `"edit": null` | Retry without `forceDuration`/`skipStems` and with `maxResults: 2`, or choose another track. |
| `DownloadRecordingEdit` → "Edit not found" | The edit id and job id do not belong together, or the edit expired. Use the ids from the same poll result; if it persists, make the edit again or fall back to an earlier good download. |
| A downloaded file is much shorter than requested | Do not use it. Re-download once; otherwise use another edit of that track. |

## What to tell the user

Always, in the report: the track names in order; that music was chosen by tags and **nothing was listened to**, so
levels and the dips under speech are untested; that any synthesised sound is synthetic; and that the music is one
file on A2, so changing a single track means re-mixing (offer to).
