# Quality: checks, habits and the mistakes this method prevents

Use this as the checklist before saying anything is finished. The items come from watching what a strong run did
and from the places where a weaker run would slip.

Contents: [Understanding the request](#understanding-the-request) · [Facts before design](#facts-before-design) ·
[Building](#building) · [Testing and looking](#testing-and-looking) · [Verifying](#verifying) · [Safety](#safety) ·
[Progress notes](#progress-notes) · [Reporting](#reporting) · [Final checklist](#final-checklist)

## Understanding the request

1. Keep **one running list of every request** in `PROGRESS.md`, in the user's own words, each with a status. New
   messages that arrive while you work are added to it and acknowledged in one line ("Noted your three additions;
   folding them in now: …"). Re-read the list before the final message; each request gets its own bullet.
2. **Every attachment is part of the request.** Open each image; pull frames from each video. Describe what you see
   before designing anything "like this".
3. When a request can be read two ways, state your reading in one sentence and proceed; list it under "please check".
   Stop to ask only when the readings need different source material or the action is risky (an account, an install).
4. An absolute rule from the user ("all the footage in the intro should be videos") is a constraint to check, not a
   preference: confirm it holds in the edit list before rendering.
5. Decide **new version or not** as soon as a request changes order, length or structure. If so, create the next
   version and leave the old timeline alone from then on.

## Facts before design

6. Capture time comes from inside the file; convert with the stored offset; never folder names or file dates.
7. Try one clip and one photo first and compare with something you know (the itinerary's date), then run the batch.
   Read the per-day table the inventory prints.
8. Read lengths, timings and counts from the data files each time. Do not carry numbers over from an earlier version.
9. Check that fonts, the LUT and the input files exist before relying on them (`vk.py`).

## Building

10. The edit list is the only source of truth. A new idea becomes an option or a shot kind there, not a one-off
    placed by hand in the editor.
11. After every `build_edl.py` run read the totals (shots, length, average, kinds, transitions, flags) and explain to
    yourself any change from the previous run.
12. When the length changes, redo what depends on time: music fits and mix, then the whole timeline.
13. Start slow jobs first and in the background (image generation, music fitting, the full render), then do the next
    independent piece. Send independent tool calls together.
14. In Resolve, time one to three items before looping over all; give loops a time budget; finish the `pending`
    list in the next call.

## Testing and looking

15. Before the full render, test **one of each** kind and graphic type. Find them by reading the edit list (the
    numbers of the first shot with each kind and option), not from memory.
16. Look at composited frames (`preview_frames.py`), element by element: inside the frame, readable on its
    background, not covering a face, the subject, a map label or another graphic; cut-outs clean; slide layout
    balanced for 2, 3 and 4 photos.
17. If something expected is missing from a frame, inspect the file (frame count, pixel format, alpha) before
    changing code.
18. Count before you trust pictures: 20 sprites expected, 20 cut, none absurdly large.
19. When automatic detection fails (map pins), draw a grid, look, and type the coordinates.
20. A look that leads to no change must still be a real look. In the original, the final sheet still showed a
    sticker crowding a flight panel and a caption over a map label; such things should be fixed before reporting,
    or reported.

## Verifying

21. Every download: print size and real duration, compare with what was ordered.
22. Every render: `validate.py` must print `bad 0`; also read the end of the render output.
23. Every Resolve step: placed against expected, each item's start and length against the edit list, items per
    track, total length, failures, saved. Subtitles: count, first start, last end.
24. Frames exported from the finished timeline, at least one per element type and per request; look; send the sheet.
25. Finish with `r08_summary`: it lists every timeline, so "earlier versions are intact" is a checked fact.
26. For what you cannot perceive, give the numbers you can (track placements, dip depths) and still say that nobody
    listened.

## Safety

27. Originals are read-only. Write copies and renders into the project folder. Delete only files you made in this
    session, by exact path; move superseded assets to an `unused` folder.
28. Install nothing without the user's approval; prefer a few lines of code. Record every install in `PROGRESS.md`.
29. When a service refuses (forbidden, not found), try once more at most, then use an allowed route or a
    substitute, and disclose it. Do not look for a way round.
30. Do not accept update prompts or change settings in the user's applications. Tell the user about anything you
    opened and could not close.
31. Keep personal details (names, faces, account names) out of prompts sent to outside services. Ask image tools
    for no text and no logos; add names and brand wording yourself as captions.
32. Watch the project folder's size against the user's limit and report it.

## Progress notes

`<P>\PROGRESS.md` is rewritten at the end of every version (and kept current in between). Sections:

```
# <Project> — Progress (updated <date>)
## Requests            numbered, user's words, status, where each is satisfied
## Status              project and timeline name, size, fps, length, shots, transitions; earlier versions still present
| Track | Contents |   one row per track with counts
## What changed from <previous version>
## Not verified — please check
## Files               folders, counts, disk used against the limit
## Tools installed this project
## Notes               assumptions, itinerary contradictions, technical pitfalls met
```

Also save a short memory note (project state, why the user wanted what they wanted, how to apply it next time)
that points at `PROGRESS.md`.

## Reporting

- While working: one or two sentences at each milestone: what finished (with a number), what is next, any problem
  and its fix. Say "most" until it is "all".
- Final message: the template in `SKILL.md`. First lines: where the result is, how it was checked, the biggest
  thing not verified, earlier versions untouched. Then one bullet per request with a count or example and the
  actual corrections made. Then the numbered "please check" list with timecodes and remedies.
- Never write "verified" for something you only applied. Separate "applied to all 68 clips" from "reviewed".
- Only numbers that came from a read-back go in the message, and the notes must agree with the message.
- Plain words, short sentences; the user reads this on a phone.

## Final checklist

- [ ] Every request in the list has a bullet in the report (done, partly done with reason, or not done with reason)
- [ ] `build_edl.py`: 0 errors; every flag fixed or explained
- [ ] Test frames looked at for every element type
- [ ] `validate.py`: `bad 0`
- [ ] Music bed length equals video length; warnings explained; reported as unheard
- [ ] Resolve steps r01–r06 all returned expected numbers
- [ ] Timeline frames exported, looked at, sheet sent to the user
- [ ] `r08_summary` matches the edit list; earlier timelines listed
- [ ] `PROGRESS.md` and memory note updated; `project.json`, `edl_<version>.py`, `music_plan.json` kept in the project
- [ ] "Please check" list complete: sound, transcribed speech, assumed facts, unlabelled uncertain items, stabiliser
