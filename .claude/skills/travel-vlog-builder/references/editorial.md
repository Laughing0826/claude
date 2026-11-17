# Editorial guide: what goes in the video and why

These are the rules the original edit followed. Numbers are from a 25 fps, 8-minute, nine-day safari vlog built to
match five popular travel vlogs; adapt the content, keep the proportions unless the user's references say otherwise.

Contents: [Structure](#structure) · [Pacing](#pacing) · [Choosing shots](#choosing-shots) · [Order and dates](#order-and-dates) ·
[The intro](#the-intro) · [Documentary sequences](#documentary-sequences) · [Scrapbook slides](#scrapbook-slides) ·
[Transitions](#transitions) · [Treatment of photos and clips](#treatment-of-photos-and-clips) · [Words on screen](#words-on-screen) ·
[When you are not sure](#when-you-are-not-sure) · [Typical requests](#typical-requests)

## Structure

1. **Blocks, in this order:** hook intro → title → getting there → route map → day chapters → route map recap →
   going home → slide of the travellers → end card.
2. **Title** after the hook, over the trip's signature landscape, 7 s. **First voice heard is the traveller's own**
   (a selfie clip right after the title, if one exists).
3. **Route map before Day 1** and again as a recap near the end (5.5–6.5 s each).
4. **Each day opens with a day card** on that morning's first shot: `DAY n · DD MMM · FROM — TO`, places taken from
   the itinerary's overnight table. A day with only two or three shots (the flight home) gets a small location tag
   instead of a card.
5. **Each day ends on evening material** (sunset, dinner, night sky) with a soft transition, so the next card reads
   as a night passing.
6. **Chapter length follows how much happened:** 40–70 s for a full day, 20 s or less for a travel day. Let
   scenery days be scenery; not every day needs a slide or a documentary sequence.
7. **The last word goes to people and thanks:** a slide of the travellers, then a thank-you card on a sunset with
   the trip's numbers ("Nine days · 1,202 km · countless memories").

What the five reference vlogs had in common, measured: a cold open of 20–40 s with a cut every 1–2 s; then shots of
2.5–4 s; the presenter talking to camera; small centred captions; pop-up keyword stickers; name labels; location
tags in a corner; a route or flight graphic early; food, room and vehicle shots between the sights; sunsets closing
chapters; music throughout. If the user gives other references, measure them (`analyze_template.py`) and follow
those instead.

## Pacing

| Element | Length |
|---|---|
| still photo | 2.3 s default; 2.6–2.8 s when a caption or label must be read; 3.0–3.4 s for a hero image; 4 s for a panorama pan |
| clip | 3.0–3.6 s typical; 4.2–4.6 s for the best behaviour; a talking clip runs as long as the sentences |
| documentary cut | 4–5 s each; a sequence is three or four cuts, 13–16 s |
| scrapbook slide | 5.6 s (6 s for four photos) |
| route map | 5.5–6.5 s; title 7 s; end card 5 s |
| rewind intro | about 0.9 s per clip, then about 1 s of PLAY |
| **average over the film** | **3.0–3.4 s per shot** |

- About half the shots start a caption; let the other half breathe.
- No captions over the intro, the title, the travellers' slide or the end card.
- Slow passages are earned and bounded: at most two documentary sequences in a day.
- If the opening is a montage instead of a rewind: alternate clip (1.4–1.6 s) and still (1.2 s), muted, hard cuts,
  a flash on about every third cut, one sentence split across three captions.

## Choosing shots

- **Look before choosing.** Open the candidate sheets and clip sheets. Never choose from a file name or a score alone.
- **Camera for animals and landscapes, phone for people, places, travel and food.** Put a human-scale shot (the
  group, the vehicle, a meal, the room, a sign) between runs of wildlife. A film of only animals is a slideshow.
- **Keep one subject together:** the clip and the still of the same animal sit next to each other.
- **Alternate kinds** (clip, photo, photo, clip). A run of four or five stills is fine only as a themed
  mini-sequence (birds of one morning, one sunset).
- **Mark each arrival** at an overnight stop with one photo and a location tag, where it happened in the day. Tag
  each place once.
- **Do not reuse a shot.** The same clip may appear at different in-points inside one documentary sequence, in the
  intro, and in the final slide; otherwise once.
- **Skip** clips that are very short, shaky beyond rescue, or duplicates of a better neighbour.
- **Camera photos:** from thousands of frames, score sharpness and exposure, keep the best frame of each burst,
  review the top 48 per day on sheets, and pick by eye (in the original 52 from 30,528, later 12 more). Favour
  mammals, behaviour, eye contact, close-ups, and frames that match a clip you are using.
- **"More animals"** is answered four ways at once: more stills, more clips, slides that hold three stills each,
  and longer documentary sequences for the best clips. Render any newly chosen photo in the same look as the others
  before using it.

## Order and dates

- **Do not trust folder names or file dates.** Read the capture time stored in each file with its UTC offset and
  convert to the destination's local time (`inventory.py` does this). Check the camera clock before trusting it:
  count files per offset and per date and see that the dates match the itinerary.
- **Inside a day, follow true capture time.** Reordering by up to 20 minutes to keep a subject together is fine;
  `build_edl.py` flags anything beyond that (`ORDER`) and anything filmed on another date (`DATE!`).
- **Resolve a real flag by moving the shot**, and keep `date_check_<version>.txt` for the user. A slide is dated by
  its latest photo.
- **Tell the user exactly what moved and why** ("the buffalo river crossing is 21 Feb, not 20 Feb").
- **Captions agree with the clock:** write "6 a.m.", "at dusk", "before breakfast" from the timestamps.
- **Place names, distances, nights and routes come from the user's itinerary.** Where the itinerary's notes and its
  booking table disagree, use the booking and mention it.
- **Re-examine earlier guesses when better evidence arrives** (a caption written from memory of v1 may be wrong).

## The intro

Default hook: the **VHS rewind**. The trip runs backwards, last day first, one or two clips per day, **video only**,
each stamped with its real date and day, and stops on the first shot of the story, which then plays. Then a flash
into the title. If a line from an earlier draft was good (a tagline, a statistic), keep it: taglines go under the
title, statistics on the end card. Alternative when the user prefers: the fast cold-open montage described under
Pacing.

## Documentary sequences

For "nature documentary style" and for any long, good clip of a large or charismatic animal.

- **Which clips:** long enough (8 s or more, or several clips of the same animal), steady, the animal large in
  frame. One sequence per species; at most two a day.
- **Three beats:** real-time wide with a slow push-in (zoom 1.0 → 1.06) → slow-motion close-up (zoom about 1.3–1.5,
  centred on the head or the action) → slow-motion medium (zoom about 1.1–1.3) or a still of the same animal.
- **Slow motion only from high-frame-rate footage** (50 fps at half speed on a 25 fps timeline).
- **One long clip can supply two or three cuts** at different in-points and zooms.
- **Fade through colour into and out of the sequence; dissolve inside it.** Cinema bars cover the whole sequence.
- **Title the animal once, on the wide shot:** NAME, scientific name in italics, second-language name. Only for
  identifications you are certain of.
- **Narration:** line 1 = place and time plus what is happening; line 2 = one true fact or behaviour; the third
  shot is silent. Third person, present tense, calm; no jokes, no exclamation marks, no stickers, no novelty wipes
  inside the sequence.

## Scrapbook slides

In the style of the user's own example slides: an illustrated paper background, two to four photos as taped
polaroids, a handwritten-style title label, a sticky note with the date, a torn-paper caption strip.

- One per day or theme, placed after the shots it relates to (often late in the day), entered with `Push` (or
  `Dip To Color Dissolve` straight after a documentary sequence).
- Three photos is the default; the first is the large one, so put the strongest there. Mix subjects (not three
  near-identical frames).
- Title: 2–4 words. Note: date and day. Caption: one warm sentence naming what is shown.
- The closing slide shows the travellers (four photos), with a `Heart` wipe.

## Transitions

| Use | Transition |
|---|---|
| into a moving wildlife clip, inside montages and action | hard cut |
| into a still photo | Cross Dissolve |
| new day, into and out of a documentary sequence, nightfall, end card | Dip To Color Dissolve |
| arriving at a camp or lodge | Barn Door |
| arriving at a sight; entering a slide | Push |
| travelling (road, plane) | Slide Left |
| a reaction or punch line | Slide Up |
| maps | Zoom In |
| after the intro into the title | Brightness Flash |
| soft evening joins | Additive Dissolve |
| novelty wipes, **once each**, only where the shape means something | Clock Wipe (a morning), Star (night sky), Heart (friends), Glitch (a shock sighting), Film Strip (dinner snapshots), Edge Wipe, Split, Spin |

In the original: 148 shots, 109 transitions of 15 kinds, 39 hard cuts. About a third of joins stay hard cuts.
Lengths are set in the Resolve step (12–20 frames); every prepared shot carries 12 spare frames per side for them.

## Treatment of photos and clips

- A still is never placed as a still: it becomes a moving shot. Default move is a slow push-in; alternate in and
  out on neighbours; drift sideways on wide subjects; pan only true panoramas and hold them longer.
- **One look for all camera material** (the user's own photo look, as styled JPEGs for photos and a LUT for clips).
  Phone photos get a weaker dose (`dark=0`), dusk and interiors less (`dark=1`), sunsets and night shots none
  (`dark=2`). Never grade twice: styled camera photos pass through untouched.
- If the user has edited photos of their own, derive the look from those (the original recipe was copied from the
  user's Lightroom settings: highlights down hard, shadows up, a little dehaze, vibrance and magenta tint) and
  show a before/after sheet before applying it to everything.
- Portrait clips and photos are shown whole over a blurred copy of themselves, never cropped to landscape.
- Mute clips whose sound adds nothing; keep animal and reaction sound.
- Stabilise only real video, and say that the result was not watched.

## Words on screen

- **Both languages on every caption, second language above English**, as designed graphics. Plain subtitle tracks
  are kept too but switched off, so nothing doubles.
- **Write the second language naturally for its audience** (Traditional Chinese for this user), not word for word.
- **Voice of ordinary captions:** first person, present tense, short, a little playful. Set-up and pay-off across
  two shots work well ("…to a fuel stop with rhinos outside the window!").
- **Species label** = English common name as the trip checklist writes it + second-language name. Label a species
  at its first good appearance, at most once more in a new place. **One illustrated badge per species**, numbered
  in order of first appearance. Check second-language species names against a reliable list when one is available;
  otherwise list them under "please check".
- **Stickers** are for people moments and surprise sightings: short, exclamatory, may mix languages, one or two a
  day.
- **A specific wording the user asks for** (an airline's anniversary livery, a person's name, a joke) goes in where
  it fits naturally, in both languages, and again at a second natural point if there is one (departure and arrival).
- Text shrinks to fit the frame, but a shrunken line looks weak: keep lines short.

## When you are not sure

- Species not certain → no label; use a general word in the caption ("an eagle") or no text. Never attach a
  scientific name to an uncertain identification.
- Place not certain → no tag, or the itinerary's wording, and list it.
- Speech you cannot hear → use the transcription tool's text, and list those captions with their timecodes.
- Facts in narration → only what you are sure of; list the ones the user should confirm.
- A design choice you asked about and got no answer to → take the option you recommended and say so.
- Everything unverified goes in the "Please check" list and into `PROGRESS.md`. What could not be checked at all
  (sound, stabiliser) goes in the first lines of the report, not at the bottom.

## Typical requests

| The user says | Do |
|---|---|
| "make it like these videos" | measure them; write down the pattern; build to it |
| "add music" / "more tracks" | `references/music.md`; one track per section, 4–6 for 8 minutes |
| "both languages" | bilingual captions on V6 + three subtitle tracks off |
| "it is shaky" | `r04_stabilize` on all real video; say it is unreviewed |
| "check the dates / follow the itinerary" | inventory with true times, day table, fix every flag, report what moved |
| "more animals / more photos" | more picks, more clips, slides, documentary sequences |
| "slides like this picture" | scrapbook slides; generate backgrounds in that style; show a test frame |
| "fancier text" | the gold serif + script + calligraphy lettering of this kit; show a test frame |
| "intro like a TV rewind" | `R()` with video only |
| "documentary style" | `D()` sequences as above |
| "mention X on the Y shot" | sticker and caption on that shot, both languages |
| "motion graphics / illustrations" | illustration sheets → badges, route map vehicle, flight path, parade |
