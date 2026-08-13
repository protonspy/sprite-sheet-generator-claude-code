# AGENTS.md

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
- **The run** — a work goes from nothing to `dist/index.json`, one recorded stage at a
  time: anchor → directions/cycles → cleanup → style → integrate. Four per-type skills
  (`sprite-sheet`, `sprite-icons`, `sprite-tilemap`, `sprite-ui`) each a whole run
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

## Skills — `.opencode/skills/` (or `.codex/skills/`)

The runs the harness drives live here: `sprite-sheet`, `sprite-icons`, `sprite-tilemap`,
`sprite-ui`. Each owns the whole run for one kind of creation — an animated sheet, a set
of icons, a tile set, a stretchable panel. When one of these is next, open its `SKILL.md`
and follow it.