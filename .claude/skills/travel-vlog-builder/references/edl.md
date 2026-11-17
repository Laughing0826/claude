# The edit list (`edl_<version>.py`)

The edit list is the whole video written down: one line per shot, in screen order. `build_edl.py` runs it and writes
`edit_list_<version>.json`, which every later step reads. Change the video by changing this file.

Contents: [Shape of the file](#shape-of-the-file) · [Shot kinds](#shot-kinds) · [Options](#options) ·
[Captions](#captions) · [Special shots](#special-shots) · [What build_edl.py checks](#what-build_edlpy-checks) ·
[Patterns that work](#patterns-that-work)

## Shape of the file

Plain Python, no imports. `day(n, date)` opens a chapter; the shot lines follow.

```python
day(0, None)                                   # not date-checked: intro montage, end card
R("rewind", 15.4, clips=[...])                 # intro
P("P335", 7.0, "in", tr="Brightness Flash", title=(...), mg="vehicle")

day(1, "2026-02-16")                           # everything below was filmed on 16 Feb (trip-local date)
V("V12", 1, 3.6, tr="Push", card=("DAY 1 · 16 FEB · RIETVLEI — DULLSTROOM", "第一天 · 里特夫萊 — 杜爾斯特魯姆"),
  sub=("Straight from the airport to Rietvlei Nature Reserve.", "一下機就直奔里特夫萊自然保護區。", 1))
S("C0003", 1, 3.4, sp=("Common Ostrich", "鴕鳥"), badge="ostrich")
A("D1-08", 2.4, "left", tr="Cross Dissolve")
```

- `ref` is an id from `catalog.csv`. `i` is the in-point in seconds from the start of the source clip. `d` is the
  time on screen in seconds. Timeline frames are `round(d * fps)`.
- Day numbers may be fractions for travel days before Day 1 (`day(0.5, "2026-02-15")`).
- Text pairs are always `(English, second language)`. Use `""` for the second language to leave it out.
  If `project.json` has `"lang2": ""` the whole video is English-only.

## Shot kinds

| Call | Source | What happens to it |
|---|---|---|
| `S(ref, i, d)` | main-camera clip | used **straight from the source file** in Resolve, graded there with the project LUT. Best quality; needs a landscape clip whose frame rate is a whole multiple of the timeline's (50 fps in 25). |
| `SV(ref, i, d)` | main-camera clip | **pre-rendered** with the LUT baked in. Use for portrait clips and odd frame rates (`build_edl.py` tells you). |
| `V(ref, i, d)` | phone video | pre-rendered to the timeline frame rate; portrait clips keep their full height over a blurred copy of themselves; sound levelled. |
| `D(ref, i, d)` | main-camera clip | documentary cut, pre-rendered: `speed`, `z`, `c` (see [Special shots](#special-shots)). |
| `A(ref, d=2.3, mv="in")` | main-camera photo, already styled | pre-rendered with a slow move. No extra look applied. |
| `P(ref, d=2.3, mv="in")` | phone photo | same, plus a light version of the photo look: `dark=0` normal (default), `dark=1` dusk or indoor (lighter touch), `dark=2` night or sunset (left as shot). |
| `M(d)` | the route map image | pre-rendered zooming in; pair with `mg="route"`. |
| `C(ref, photos, title, note, cap, d=5.6, bg=1)` | 2–4 photos | scrapbook slide. `ref` is just a name for the slide. |
| `R(ref, d, clips=[...])` | several clips | VHS rewind intro. `ref` is just a name. |

`mv` (photo move): `"in"` slow zoom in (default), `"out"` zoom out, `"left"` / `"right"` drift, `"pano"` pan across
a wide panorama (give it 4 s or more). Alternate moves between neighbouring photos so they do not all breathe the
same way.

## Options

Add as keyword arguments to any shot unless noted.

| Option | Meaning | Notes |
|---|---|---|
| `tr="Cross Dissolve"` | transition **into** this shot | none = hard cut. Names must be Resolve's: Cross Dissolve, Additive Dissolve, Dip To Color Dissolve, Push, Barn Door, Clock Wipe, Edge Wipe, Split, Star, Heart, Brightness Flash, Zoom In, Slide Left, Slide Up, Slide Down, Glitch, Film Strip, Spin, Camera Shake, Foreground Wipe. Not on shots under 1.2 s. Ignored on the first shot. |
| `mute=True` | silence the clip's own sound | montage shots, wind or engine noise, clips under music only |
| `sub=(en, l2, span)` | a caption that starts with this shot and stays for `span` shots | see [Captions](#captions) |
| `subs=[(t0, t1, en, l2), ...]` | captions timed in seconds within this shot | for speech |
| `card=(en, l2)` | chapter card, top left | English must look like `"DAY 1 · 16 FEB · PLACE — PLACE"`: the part before the first ` · ` is drawn large ("Day" + number), the rest small |
| `loc=(en, l2)` | location tag, top right | short: a place name in capitals |
| `sp=(en, l2)` | name label, lower left | species or thing shown. Only when sure. |
| `lower=(NAME, scientific, l2)` | documentary name title, lower left | on the first shot of a `doc` group |
| `title=(main, l2, small, top, tagline)` | opening or closing title | `main` in capitals; `small` is the spaced small-caps line; `top` a short script line above; `tagline` a script line below. The 3-item form `(main, l2, small)` also works. Give the shot 5–7 s. |
| `stk="text"` | yellow pop-up sticker | a short exclamation or joke, may mix both languages. No emoji (they are removed). |
| `badge="sprite"` | illustrated "Spotted! #n" badge | sprite name from `Graphics\mg\cut\`. Numbered in order of first appearance; use once per animal, at its first good sighting. |
| `mg="vehicle"` | the vehicle sprite drives across the bottom | with the opening title |
| `mg="flight"` | flight-path panel with a plane | stays up for `mg_span` shots (default 3); needs `"flight"` in `project.json` |
| `mg="route"` | animated route on the map | only on `M()`; needs `"route"` in `project.json` |
| `mg="parade"` | all sprites hop along the bottom | with the closing title |
| `doc="name"` | groups consecutive shots into one documentary sequence | cinema bars cover the whole group |

Where things sit, so they do not collide: card top-left, location tag top-right, name label and documentary title
lower-left, badge right-middle, captions bottom-centre, sticker upper-right (it moves left when a location tag is
present, and lower when a card is present). Avoid a card and a location tag and a sticker all on one short shot.

## Captions

Captions are drawn as styled graphics (second language on top, English below) and also written to `.srt` files.

- `sub=(en, l2, span)`: narration. It appears 5 frames into this shot and leaves 4 frames before the end of the
  last shot it spans. `span` counts shots including this one. Size the span so the caption is up at least 2.5 s and
  about 1 s per 3 words of English.
- `subs=[(0.2, 3.3, en, l2), ...]`: speech, timed against the clip. Get the words by transcribing the clip (Resolve's
  transcription, or listen-free methods available to you); auto-transcription is often wrong for Cantonese and for
  mixed languages, so always list these lines under "please check" with their timecodes.
- Two captions never overlap: an earlier one is cut short 2 frames before the next begins.
- Keep each line to one line on screen: English up to about 70 characters, Chinese up to about 30. Longer lines are
  shrunk to fit, which looks weak; split the sentence across two shots instead ("…" at the join reads well).
- Voice: first person, present tense, warm and brief; say what the picture does not ("Dullstroom, 2,000 m up —
  dinner by the fire."). The second language is a natural rendering, not word-for-word.
- Facts in captions (distances, heights, animal behaviour) must come from the itinerary or be common knowledge you
  are sure of; list any you inferred under "please check".

## Special shots

### Documentary sequence: `D()` with `doc=`

For a subject with enough good footage (a clip of 8 s or more, or two or three clips of the same animal). Three
shots work well: a wide establishing shot at normal speed, a slow-motion close-up, a third angle or behaviour.

```python
D("C0016", 4, 5.0, speed=1, z=(1.0, 1.06), doc="giraffe", tr="Dip To Color Dissolve", badge="giraffe",
  lower=("GIRAFFE", "Giraffa camelopardalis", "長頸鹿"),
  sub=("On the road from Orpen, two giraffes browse the treetops.", "從奧本門進來的路上，兩隻長頸鹿在樹梢覓食。", 1))
D("C0016", 22, 4.4, speed=0.5, z=(1.42, 1.5), c=(0.5, 0.4), doc="giraffe", tr="Cross Dissolve",
  sub=("A tongue almost half a metre long strips leaves from between the thorns.", "近半米長的舌頭，從尖刺之間捲走嫩葉。", 1))
D("C0017", 2, 4.0, speed=0.5, z=(1.12, 1.2), doc="giraffe", tr="Cross Dissolve")
A("D4-18", 2.3, "out", tr="Dip To Color Dissolve")      # the shot after the sequence dips out of it
```

- `speed=0.5` is slow motion and needs a source filmed at twice the timeline rate or more (50 fps for 25). At
  `speed=0.5` the shot uses `d * 0.5` seconds of source. On a normal-rate source use `speed=1`.
- `z=(start, end)` zoom: `(1.0, 1.06)` is a slow push-in on the full frame; `(1.3, 1.5)` is a close-up crop that
  keeps creeping in. Stay at or under 1.5 on 4K sources, 1.25 on HD sources.
- `c=(x, y)` is where the zoom is centred, as fractions of the frame (0.5, 0.5 = centre). Find it by looking at the
  clip sheet: put the animal's eye or the action there.
- Enter with `Dip To Color Dissolve`, cut inside with `Cross Dissolve`, and give the next ordinary shot a
  `Dip To Color Dissolve`. Captions here are narration in a nature-film voice: what the animal is doing and one
  true fact. Put `lower=` and usually `badge=` on the first shot only.
- A still photo of the same subject may sit inside the group (`A(..., doc="giraffe")`).

### Scrapbook slide: `C()`

```python
C("slide_d1", ["D1-24", "D1-39", "D1-41"], ("Rietvlei birds", "里特夫萊的鳥"), ("16 FEB", "Day 1"),
  ("Korhaan, thick-knee and barbet — all before lunch.", "北黑鴇、斑石鴴、黑領擬啄木鳥——午餐前全部到齊。"), bg=1, tr="Push")
```

Photos: 2, 3 or 4 catalog ids; the first is the large one. `title` is the paper label, `note` the yellow sticky
note (two short lines: date, day), `cap` the caption strip. `bg` chooses `Graphics\mg\scrap_bg<bg>.png`; alternate
1 and 2. Use `d=5.6` (6.0 for four photos). One slide per day or per theme gathers good photos that did not earn
their own shot; a final slide of people closes the film. Do not also add `sub=` to a slide (it has its own caption).

### Rewind intro: `R()`

```python
R("rewind", 15.4, clips=[("V106", 8, "24 FEB 2026", "DAY 9"), ("C0044", 2, "22 FEB 2026", "DAY 7"), ...,
                         ("V1", 2, "15 FEB 2026", "HONG KONG")])
```

Each clip is `(id, in-point, date text, label text)`. Order them from the **end of the trip back to the start**;
the last one must be the clip the story opens with, because the tape then "plays" from it. Use **video clips only**
(the user asked for this), one or two per day, the most striking moments. Length: about 0.9 s per clip plus 1 s.
Each clip needs about 2.4 s of source after its in-point. Follow with the title shot (`tr="Brightness Flash"`), then
the same first clip again as an ordinary shot so the story starts.

## What `build_edl.py` checks

- **ERROR** (must fix): unknown id, missing file, in-point plus length beyond the clip, `S()` on a portrait clip
  or a frame rate that is not a multiple of the timeline's, malformed options, a graphic whose `project.json`
  section is missing.
- **WARN** (decide): unknown transition name, transition on a very short shot, a plain shot over 6 s, slow motion
  on a normal-rate source, badge sprite not cut yet, a documentary group without a name title.
- **DATE!**: the shot was filmed on a different date from its chapter. Move it to the right chapter.
- **ORDER(-N min)**: filmed more than 20 minutes earlier than the shot before it. Usually move it; sometimes
  intended (a chapter that opens with its best later moment). Explain every one you keep.
- **NOTIME**: no capture time known; you cannot vouch for where it sits. Say so in the report.

It also prints the totals to compare with your targets: number of shots, length, average shot length, counts by
kind, counts by transition (`cut` = hard cuts), captions, cards, labels, stickers, badges.

## Patterns that work

- **Chapter opening:** a scene-setting clip or photo with `card=`, a transition in (`Dip To Color Dissolve` or
  `Push`), and a `sub=` saying where we are. **Chapter ending:** a sunset or night photo (`dark=2`).
- **Arrival at a place:** photo or clip with `loc=` and `tr="Barn Door"` or `"Push"`.
- **Rhythm:** clip, photo, photo, clip. Two or three photos in a row, then movement. Photos 2.2–2.8 s, clips 2.8–4.6 s,
  speech as long as the sentence.
- **A joke lands on a cut:** set-up caption ends with "…", the punch-line shot has `tr="Slide Up"` and a sticker.
- **People are part of the story:** every chapter needs at least one shot of the travellers, the vehicle, a meal or
  the room among the scenery.
