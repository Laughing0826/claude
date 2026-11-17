# claude
For Claude Code

## Skills

### travel-vlog-builder

Builds or revises a long-form travel vlog from your own photos and clips as an editable DaVinci Resolve timeline:
verified dates, edit list, VHS rewind intro, day cards, tags, labels, stickers, bilingual captions, documentary
sequences, scrapbook slides, illustrated motion graphics, music bed, transitions and stabilisation.
It records the procedure used for the South Africa vlog so the same result can be reached with any Claude model.

Location: `.claude/skills/travel-vlog-builder/` (`SKILL.md`, `references/`, `scripts/`, `assets/`).

**Install on a PC (so every Claude Code session can use it):** copy the folder `travel-vlog-builder` into
`%USERPROFILE%\.claude\skills\` (Windows) or `~/.claude/skills/` (macOS/Linux). Or open the packaged
`travel-vlog-builder.skill` file in the Claude app and choose "Save skill".

**Use:** ask for the video in plain words ("make a vlog of my trip from this folder", "add music to the vlog",
"make a v4 with more wildlife"), or type `/travel-vlog-builder`.

**Needs on the PC:** Python 3.9+ with Pillow and numpy, ffmpeg, DaVinci Resolve with its MCP connector;
optionally the Epidemic Sound connector and an image-generation skill.

**Tested:** every script was run end to end on synthetic footage (inventory, edit list, renders, overlays,
validation, previews, music mix, sprite cutting). The Resolve steps reuse the calls that worked in the original
session but could not be run in the cloud; the first run on the PC is their test.
