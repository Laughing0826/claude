# Design guide: graphics, lettering and illustrations

All graphics are drawn by the scripts for a **1920 × 1080** frame as transparent ProRes 4444 clips and laid on
tracks above the footage. This file says what each one looks like, where its code is, and how to make the
illustrations they use. Read it before changing a graphic or adding one.

Contents: [Design language](#design-language) · [Fonts](#fonts) · [Each graphic](#each-graphic) ·
[Illustrations](#illustrations) · [Scrapbook backgrounds](#scrapbook-backgrounds) · [Route map](#route-map) ·
[Flight panel](#flight-panel) · [Adding or changing a graphic](#adding-or-changing-a-graphic) · [Checks](#checks-on-every-test-frame)

## Design language

One consistent set, used everywhere:

- **Gold lettering** for anything titular: a vertical gradient from pale gold (255, 240, 186) to deep gold
  (216, 160, 72) with a thin dark outline and a soft drop shadow. Flat gold (236, 196, 120) for rules and accents.
- **Three voices of type:** bold serif capitals with wide letter-spacing (titles, names), a script face (accents:
  "Day", taglines, "Spotted!"), a calligraphy-style face for the second language. Cream (255, 236, 196) for
  secondary lines, white for body.
- **Soft dark scrims** behind lettering (blurred, about half opacity) instead of boxes, so text reads on bright
  footage without looking pasted on.
- **Paper things** (location tag, sticker, slide label, sticky note, polaroids) are opaque, slightly rotated, with
  soft shadows.
- **Motion:** elements slide or rise 26–60 px into place over 8–14 frames with an ease-out, staggered a few frames
  apart; everything fades out over the last 8 frames. Stickers and badges pop (overshoot to 115 %, settle).
- **Vintage, hand-made warmth:** watercolour-and-ink illustrations, kraft paper, tape. No neon, no glossy 3D.

## Fonts

`gfx.py` asks for fonts by role; `vk.py` finds the file. Intended (Windows) faces, with the fallbacks used elsewhere:

| Role | Intended | Used for |
|---|---|---|
| `SERIF_B`, `SERIF`, `SERIF_I`, `SERIF_BI` | Georgia bold / regular / italic / bold italic | titles, names, English captions (italic), species labels (bold italic) |
| `SCRIPT`, `SCRIPT_B` | Segoe Script regular / bold | "Day", taglines, badge text, slide titles |
| `HAND` | Ink Free | sticky notes |
| `ZH` | Microsoft JhengHei Bold | second-language captions, stickers, tags |
| `ZH_K` | DFKai-SB (kaiu.ttf) | second-language titles and names (calligraphy feel) |
| `SANS_B` | Segoe UI Bold | location tag |
| `MONO` | Consolas Bold | VHS on-screen display |

Run `vk.py` once per project and read the font list. If a role fell back to another face (on macOS or Linux, or if
a font is missing), say so and set `"fonts": {"ROLE": "file.ttf"}` in `project.json`. For a second language other
than Chinese, point `ZH` and `ZH_K` at fonts that cover it. Missing glyphs show as empty boxes in test frames.

## Each graphic

Positions are x, y in frame pixels. Track = the Resolve video track it lands on.

| Graphic | Option | Look and position | Timing | Code |
|---|---|---|---|---|
| Opening / closing title | `title=` | centred stack over a horizontal scrim: script line (70 px, y 262); main title in gold serif capitals, letter-spaced, up to 108 px (y 372); gold rule with a diamond (y 512); second language in gold calligraphy 70 px (y 532); script tagline 40 px (y 636); small spaced line 28 px cream (y 722) | starts 8 frames in; layers arrive at frames 4, 12, 22, 26, 40, 52; up to 6.6 s | `prep.text_overlay` |
| Day card | `card=` | top left over a soft oval scrim: gold script "Day" 84 px with a 150 px gold serif number; gold rule; route line in spaced capitals 34 px; second language 50 px cream | slides in from the left over 10 frames, staggered; up to 4.6 s | `prep.text_overlay` |
| Location tag | `loc=` | white rounded tag, top right (right edge x 1846, y 64): red pin dot, bold name 32 px, second language 28 px grey | slides in from the right | `prep.text_overlay` |
| Name label | `sp=` | lower left (x 84–108, y 768): thin gold bar, gold bold-italic name 48 px, second language 44 px white | slides in from the left | `prep.text_overlay` |
| Documentary title | `lower=` | lower left over a scrim: gold hairline (y 742), NAME in spaced serif capitals 56 px, scientific name in gold italic 34 px, second language 42 px cream | rule at frame 14, name at 18, second line at 26 | `prep.text_overlay` |
| Cinema bars | `doc=` | black bars 138 px top and bottom (about 2.39:1) | ease in and out over 12 frames; span the whole sequence | `prep.letterbox_overlay` |
| Sticker | `stk=` | yellow (255, 214, 10) rounded label, dark outline, bold 50 px text, tilted 4°; upper right (1470, 235); moves to (460, 240) with a location tag, (1480, 380) with a day card | pops in at frame 10; about 2.5 s | `prep.sticker_overlay` |
| Badge | `badge=` | die-cut illustration 230 px high with a white outline, gold script "Spotted!  #n" under it; right side (1650, 610) | pops in at frame 14 with a slight wobble; about 2.6 s | `prep.badge_overlay` |
| Caption | `sub=`, `subs=` | bottom centre: second language 50 px white bold (y 952), English 36 px cream italic (y 1012), dark outlines and soft shadow; each shrinks to fit 1700 px | rises 14 px over 6 frames; fades over 5 | `prep.caption_overlay` |
| Vehicle | `mg="vehicle"` | the vehicle sprite, 120 px high, drives left to right along y 905 | from frame 30 to the end of the shot | `prep.vehicle_overlay` |
| Parade | `mg="parade"` | all sprites hop up along the bottom edge, one every 4 frames | from frame 30 | `prep.parade_overlay` |
| Flight panel | `mg="flight"` | dark translucent panel top left with a dotted arc, city names, distance label, plane sprite flying the arc | spans `mg_span` shots | `prep.flight_overlay` |
| Route | `mg="route"` | gold line growing along the roads, pulsing rings on reached pins, vehicle sprite driving, km and day counter panel | spans the map shot | `prep.route_overlay` |
| VHS intro | `R()` | REW ◀◀ / PLAY ▶ top left, counter top right, date and day bottom left, "SP  VHS" bottom right, monospace white with shadow; colour fringing, scanlines, tracking bands, a noise bar near the bottom | see `references/edl.md` | `special.rewind` |
| Scrapbook slide | `C()` | see below | 5.6 s | `special.collage` |

Scrapbook slide layout: illustrated paper background; polaroids (cream border 20 px, a kraft card peeking out
behind, a strip of tape on top, soft shadow) at fixed places for 2, 3 or 4 photos (`special.LAYOUT`), each resting
at a slight angle; a rotated paper label with the title (script + calligraphy); a yellow sticky note with date and
day in a handwriting face; a torn cream strip across the bottom with the caption (second language 44 px ink,
English 33 px italic brown). The first photo is in place from the first frame; the others drop in 9 frames apart;
label and note fade in last.

## Illustrations

Badges, the vehicle, the plane and the parade use hand-painted style illustrations. Generate them as **sticker
sheets** (one image holding many drawings, so they share one style), then cut the sheet into sprites.

1. **Generate** with the available image tool, in the background (it takes minutes). On this user's PC:
   `& "$env:USERPROFILE\.claude\skills\chatgpt-image\gen-image.ps1" -Prompt $p -Out "<P>\Graphics\mg\animals_sheet.png"`.
   Prompts that worked (replace the subjects with this trip's):

   > A sticker sheet of 12 hand-painted watercolor illustrations of African safari animals, all in one consistent
   > warm, soft watercolor-and-ink style like a vintage illustrated travel map. Arrange them in a neat grid of 4
   > columns and 3 rows on a pure flat white (#FFFFFF) background. Each animal is a complete full-body side view,
   > similar size, clearly separated from its neighbours by wide empty white margins, nothing overlapping or
   > touching. No text, no labels, no numbers, no borders, no frames, no ground shadows, no background wash. Row 1:
   > white rhinoceros, African elephant, giraffe, plains zebra. Row 2: Cape buffalo, hippopotamus, spotted hyena,
   > ostrich. Row 3: impala ram, chacma baboon sitting, lilac-breasted roller bird perched on a small twig, southern
   > yellow-billed hornbill perched on a small twig. Landscape 3:2 image.

   > A sticker sheet of 8 hand-painted watercolor illustrations in one consistent warm, soft watercolor-and-ink
   > style like a vintage illustrated travel map. Arrange them in a neat grid of 4 columns and 2 rows on a pure flat
   > white (#FFFFFF) background. Each object is complete, similar size, clearly separated from its neighbours by
   > wide empty white margins, nothing overlapping or touching. No text, no labels, no numbers, no borders, no
   > frames, no ground shadows, no background wash. Row 1: a dark-green open safari game-viewing truck with a canvas
   > roof and three rows of seats, exact side view facing right; a white passenger jet airliner flying, exact side
   > view facing right; a camera with a long camouflage telephoto lens; a pair of binoculars. Row 2: a flat-topped
   > acacia tree; a round thatched rondavel hut; a red map location pin; a golden setting sun with a few small
   > orange clouds. Landscape 3:2 image.

   What matters in the prompt: one consistent style, a strict grid with wide white margins, pure white background,
   "no text / no shadows / no background wash", each subject named per row, side views facing right for anything
   that will move (the route flips the vehicle when it drives left).
2. **Look at the sheet** (Read the image): right number of drawings, none touching, none cut off.
3. **Cut** it: `cut_sheet.py "<sheet>" <rows> <cols> name1,name2,...` in reading order. Sprites go to
   `<P>\Graphics\mg\cut\<name>.png`.
4. **Look at the contact sheet** (`<P>\_work\cut_sheet.jpg`, on green so white fringes show): every sprite whole,
   no fragments of neighbours, no holes in white areas. If two drawings were merged or a part was dropped, re-run
   with a different `--white` threshold or regenerate the sheet with wider margins.
5. Optional recolouring of one sprite (the plane's tail was turned from red to the airline's green) with
   `cut_sheet.recolor_hue`.

Use only animals and objects that actually appear in the video. Name sprites in lower case; the edit list refers to
them (`badge="giraffe"`), `project.json` lists the parade and the vehicle.

## Scrapbook backgrounds

Two backgrounds alternate (`bg=1`, `bg=2`): `Graphics\mg\scrap_bg1.png`, `scrap_bg2.png`, 16:9. Without them a plain
paper background is drawn, which is acceptable but plainer. Prompts that worked (change the plants and scenery to
the destination):

> A 16:9 landscape scrapbook page background, flat-lay view. Layered kraft-brown and cream torn paper with soft
> deckled edges, a few strips of beige washi tape, a vintage postage stamp and a faded round postmark in one corner.
> Around the edges and corners: hand-painted watercolor botanical illustrations of African savanna plants (thorny
> acacia branches with small leaves, golden savanna grasses, a protea flower, an aloe). In the lower-left and right
> margins, faint loose watercolor-and-ink sketches of flat-topped acacia trees, distant hills and a dirt safari
> track. The large middle area is mostly empty plain cream paper, left clear for placing photographs later. No
> photographs, no people, no animals, no text, no letters, no numbers. Warm beige, cream, olive green and ochre
> palette, soft even lighting.

> A 16:9 landscape scrapbook page background, flat-lay view. Cream watercolor paper with torn kraft-brown paper
> pieces in the corners, small strips of beige washi tape, a vintage postage stamp top-right, faint wavy postmark
> lines. Around the edges: hand-painted watercolor illustrations of African bushveld leaves and seed pods, golden
> grasses and reeds, and at the bottom-right a faint loose watercolor-and-ink sketch of a river with reeds and
> rocks; at the left a faint sketch of an acacia tree at sunset. The large middle area is mostly empty plain cream
> paper, left clear for placing photographs later. No photographs, no people, no animals, no text, no letters, no
> numbers. Warm cream, sand, sage green and soft orange palette, soft even lighting.

When the user shows example slides, describe what you see in them (frames, tape, paper, caption strip, plants) and
match that; the slide design here was copied from such an example.

## Route map

1. The map image: an illustrated 16:9 map with numbered stops (generate it in the same watercolour style, or use one
   the user has). Save as `Graphics\route-map.png`.
2. `map_grid.py "<P>\Graphics\route-map.png"` draws a labelled grid on a copy. Open it and **read off** the pixel
   position of each stop and of two to five points along each road between stops. (Automatic pin detection was
   tried and found one pin of seven; reading the grid is the reliable way.)
3. Put them in `project.json`:
   ```json
   "route": {"map": "Graphics/route-map.png",
             "pins": [[207, 902], [568, 660], ...],                       one per stop, in travel order
             "legs": [[[207, 902], [330, 780], [430, 710], [568, 660]], ...],   one list of points per leg, pin to pin
             "km":   [241.6, 109.2, ...],                                  distance of each leg, from the itinerary
             "labels": ["Day 1", "Day 2", ...],                           optional, shown while driving each leg
             "end_label": "Day 8",                                         optional
             "panel": [50, 560]}                                           top-left of the km counter
   ```
   A final leg back to the start may end near, not on, the first pin.
4. Test-render the map shot and look: the line must follow the map's own roads, and the counter panel must not
   cover the map's lettering (move `panel` if it does; in the original it had to move off the bottom-left labels).
   The map shot zooms from 100 % to 109 %; the overlay follows the same zoom automatically.

## Flight panel

`project.json`: `"flight": {"from": ["HONG KONG", "香港"], "to": ["JOHANNESBURG", "約翰尼斯堡"],
"label": "10,700 km  ·  13 h", "sprite": "plane"}`. Put `mg="flight"` on the first in-flight shot; it stays up for
`mg_span` shots (default 3). Distance and time are facts: take them from the booking or mark them as assumed.

## Adding or changing a graphic

1. Find the nearest existing one in the table above and copy its function.
2. Draw full-frame RGBA images with `gfx.new()`, `gfx.text(...)` (shadow, outline, `grad=gfx.GOLD_GRAD`),
   `gfx.spaced(...)`, `gfx.fit(role, size, text, max_width)`; turn each into a layer with
   `gfx.crop_layer(img, t0, "up"|"left"|"right"|"fade", ln, dist)` and render with `gfx.render_layers(layers, dur, dst)`.
   For frame-by-frame animation write a generator of RGBA frames and pass it to `gfx.enc_alpha`.
3. Register it in `prep.do_overlays` with a start offset, a length and a track, and add its option to `build_edl.py`
   if it needs a new keyword.
4. Test-render one shot with it and look at the composited frame before using it everywhere.

Keep to the design language above so new elements belong to the same family. When the user asks for "fancier" or
shows a reference they dislike (plain white subtitle text), move towards this family, show a test frame, and ask
only if the direction is truly ambiguous.

## Checks on every test frame

- Text readable against its background at a glance; add or strengthen a scrim rather than a box.
- Nothing covers a face, the animal's head, or another graphic. Two graphics never share a corner.
- No clipped text at the frame edge; no empty boxes where characters should be.
- Illustration sprites have clean edges, no white halo against dark footage.
- Map graphics sit on the roads; the counter and labels do not hide map text.
- Slide: photos inside the frame, title label and note not covering a subject, caption on the strip.
