# CLAUDE.md

## The project

This workspace is built by `ssc`, the sprite sheet generator. It turns AI-generated art
into game-ready 2D assets: real pixels on a real grid, aligned frames, a transparent
background, metadata an engine can read. The art arrives with defects — fake pixels,
frame bleeding, drift, halos, palette drift, flicker, seams — and each one is **measured**,
then **repaired** with the command that fixes it. Never a judgement about whether art
"looks right": read the numbers and run the named command.

## The domain

- **Asset** — one piece of work, at `assets/<kind>/<key>/`, with `meta.json` recording
  each file's stage, class (`source` / `derived` / `output`) and provenance. A file's
  three-digit prefix orders a chain; a stage name is its address.
- **Kind** — the profile behind an asset: cell size, anchor, frame rate, applicable
  `doctor` checks, generation template. Built-in kinds: `character`, `icon`, `tile`, `ui`,
  `banner`, `map`, `background`, `box-art`.
- **The defects `doctor` measures**, and the command that repairs each:
  - `pixel_grid` (fake pixels) → `tool snap` or `tool pixelart`
  - `bleed` (frame bleeding) → `tool slice`, `tool cut`
  - `drift` (frame drift) → `tool align`
  - `halo` (chroma ring) → `tool bgremove`
  - `palette` (palette drift) → `tool style` / `tool recolour`
  - `flicker` (still region changing) → one palette for the whole frame set
  - `silhouette` (holes/fragments) → `tool align`, `tool trim`
  - `seam` (tiles) → `tool tile`
  - `nineslice` (UI) → `tool ninepatch`
- **The run** — a run goes from nothing to `dist/index.json`, one recorded stage at a
  time: anchor → directions/cycles → cleanup → style → integrate. Four per-type skills
  (`sprite-sheet`, `sprite-icons`, `sprite-tilemap`, `sprite-ui`) each drive a whole run
  end to end for one kind of creation; `ssc tool doctor` measures at each point.
- **Two rules of the trade**: every resize is **nearest neighbour** — one bilinear resize
  undoes the pixel pipeline; and a hard guide (a nine-patch line) sits **on the pixel
  grid**, never inside a block.

## Driving `ssc`

`tool` commands are local, free, synchronous; `gen` commands bill the provider. Every
command emits **one JSON object** on stdout. Exit codes: `0` ok, `1` error, `2` invalid
usage, `3` a gate is pending. `--dry-run` writes nothing. Nothing overwrites — a mistake
is `git checkout`.

`ssc --help` and `ssc tool --help` list everything; `ssc tool doctor <asset>` measures a
work item and names the fix for each defect it finds.

## Choosing a model

`ssc model list` names every model, the media it makes, which one is the default and which
have a published price. `ssc model show <id>` gives one model's options with their types and
ranges, plus the provider's own price text. That text is **indicative** — it is the sentence
the provider published, not a quote, and `ssc` parses no number out of it. What a run cost
is what `ssc budget` recorded.

Defaults, used when neither `ssc.yaml` nor the kind names a model:

- **image** — `openai/gpt-image-2`
- **video** — `xai/grok-imagine-video/image-to-video`

Four options move what a call costs, and they are the four to decide **before** spending:

- `--count` — multiplies it outright. Four images cost four times one.
- `--size` — a larger tier costs more, and past the kind's cell size it buys nothing: the
  frame is downsampled to the grid anyway.
- `--quality` — where the model has one. The steepest lever on GPT Image 2, which bills by
  token and defaults to `high`.
- `--seconds` — video only, and video is priced per second of output.

Match them to the work rather than to a habit:

- **The frame everything else derives from** — the anchor — is the one to pay properly for:
  one image, the quality up, the size the kind asks for. A wrong anchor wastes every paid
  call after it.
- **Choosing between candidates** is the opposite call: raise `--count`, drop `--quality`
  and the size tier. You are judging a composition, not shipping pixels; regenerate the one
  you picked at full quality.
- **Anything a `tool` command can do is not a paid call.** `tool recolour` makes a variant,
  `tool style` restyles, `tool bgremove` has a free deterministic path before its `--model`
  one. Reaching for `gen` where a `tool` exists is the commonest way to pay for something
  this workspace already had.
- **Video costs by the second.** Generate the shortest clip that shows the cycle and loop
  it, rather than a long one to cut down.

A model that maps no `--size` — the three image-to-video models other than the default do
not — still takes its own fields through `--opt`, checked against its schema:
`--opt resolution=720p`, `--opt duration=5`. `ssc model show <id>` lists what each accepts.

## Skills — `.claude/skills/`

The runs the harness drives live here: `sprite-sheet`, `sprite-icons`, `sprite-tilemap`,
`sprite-ui`. Each owns the whole run for one kind of creation — an animated sheet, a set
of icons, a tile set, a stretchable panel. When one of those is next, open its `SKILL.md`
and follow it.