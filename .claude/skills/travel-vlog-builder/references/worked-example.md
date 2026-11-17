# Worked example: the 8-minute safari vlog

The project this skill was distilled from: a nine-day trip (flight out, eight days on the road through highlands,
a canyon and a national park, flight home), filmed on a mirrorless camera (50 fps clips, about 30,000 RAW frames)
and a phone (about 1,150 photos, 150 videos). Captions in Traditional Chinese and English. Three cuts were made.

## The three versions

| Version | What it was | Length | Why the next one was needed |
|---|---|---|---|
| v1 | camera clips and 52 chosen camera photos; day cards; two subtitle tracks; no transitions, no music | 8:01 | the user wanted it to look like five template vlogs and to use the phone footage |
| v2 | template-style: fast cold open, selfie pieces, day chapters, location tags, name labels, stickers, 150 shots averaging 3.0 s, 102 transitions of 17 kinds | 7:33 | music, then a stream of new wishes |
| v3 | everything below | 8:22 | — |

## Requests that arrived during v3, and where each landed

| Request (user's words, shortened) | Answer in v3 |
|---|---|
| "Yes, add music" / "more than 3 audio tracks" | five fitted tracks mixed into one bed on A2, dips under speech |
| "motion graphics using illustrations" | two generated sticker sheets → 11 "Spotted!" badges, flight path with plane, route map with a driving truck and km counter, title truck, end-card parade |
| "both languages as the subtitle" | 76 styled captions, Chinese above English, on V6; three text subtitle tracks kept but off |
| "some videos seem very shaky" | Resolve stabiliser on all 68 video clips (reported as not reviewed) |
| "wording that it is the airline's 80th-anniversary design" | sticker and caption on the departure plane, a second caption on arrival |
| "double check the dates, arrange according to the itinerary" | capture times read from camera sidecars and photo metadata; every shot placed by real time; five scenes moved to their true day; `date_check_v3.txt` kept |
| "more pictures and videos of the animals" | 12 more camera photos in the user's look, 10 earlier picks brought back, more clips, 8 animal slides |
| "slides like these" (example images) | nine scrapbook slides: polaroids, tape, paper background, caption strip |
| "fancier words; intro like a TV rewind; intro footage all videos" | gold serif + script + calligraphy lettering; VHS rewind of 16 video clips, then PLAY and the title |
| "cut long footage in nature-documentary style" | five sequences (giraffe, impala, buffalo, elephant, hippo): slow motion, close-ups, cinema bars, name + scientific name |

## Numbers of the final cut

- 1920 × 1080, 25 fps, 502.48 s, 148 shots (average 3.4 s): 1 rewind intro, 15 documentary cuts, 9 slides, 17 other
  camera clips, 33 camera photos, 36 phone videos, 35 phone photos, 2 route maps.
- 109 transitions: Cross Dissolve 53, Dip To Color Dissolve 19, Push 12, Slide Up 5, Slide Left 4, Barn Door 4,
  Additive Dissolve 3, Zoom In 2, and one each of Brightness Flash, Film Strip, Clock Wipe, Star, Edge Wipe, Glitch,
  Heart. 39 hard cuts.
- 166 overlays: cinema bars 5 (V2), titles and labels 53 (V3), stickers 16 (V4), motion graphics 16 (V5),
  captions 76 (V6). Three subtitle tracks of 76 lines each.
- Render: 131 prepared shots and 166 overlays, about 3.4 GB, about 6 minutes on 6 workers. Timeline build: 8 script
  calls in about 2½ minutes.
- Music: opener from 0:15 (after the rewind) → Day 1 → Day 3 → mid Day 5 → last track ending on the final frame;
  -12 dB under the two airport selfie clips, -5/-6 dB under three reaction clips.

## Timeline of the v3 round (40 minutes)

1. Plan written; chapter and speech timings listed; three music searches sent together; edits ordered.
2. New requests arrive → plan rewritten each time; illustration sheets ordered in the background; stabiliser tried
   on 3 clips, then run on the rest in two timed calls.
3. Itinerary read; capture times extracted for all clips and RAW frames; clock checked (offsets counted); candidate
   sheets looked at; 12 more photos chosen and rendered.
4. Edit list rewritten in itinerary order; date check run (2 flags → 1 fixed, 1 explained); intro replaced by the
   rewind; documentary sequences patched in; totals re-read after each change (154 → 142 → 148 shots).
5. Graphics code written; sheets cut (first attempt merged neighbours → smaller join distance); map coordinates read
   from a grid after automatic pin detection failed.
6. Test render of 15 representative shots → two errors fixed → composite frames looked at → slide title made
   legible, map counter moved off the map's labels → stale test files deleted → full render in the background.
7. Meanwhile: music re-fitted to the new lengths, one truncated download replaced by an earlier edit, bed mixed.
8. Every file validated; timeline built step by step with read-backs; subtitle offset caught and corrected;
   18 frames exported from the timeline, looked at, and sent.
9. Notes and memory updated; scripts saved with the project; report with a six-item "please check" list.

## What was said to be unverified

Sound (nothing listened to; rewind sound synthetic); airport captions from auto-transcription; an assumed
fuel-stop name, flight distance and two narration facts; uncertain species left unlabelled; stabiliser not reviewed
clip by clip; playback may need render cache.

## Weak spots of that run, worth doing better

- The final frame sheet showed a sticker crowding the flight panel and a long caption over a map label; neither was
  fixed or mentioned. Check for overlaps on the final sheet and act on them.
- An earlier-version memory note was renamed in content but not in file name; keep note names in step with versions.
- The design question about the end card was settled without telling the user; say which option you took.
