---
name: sprite-sheet
description: The complete flow for an animated sprite sheet — own the whole run from an empty asset to `dist/index.json`. Use it when the work is a character or creature that is to become one sheet: anchor, directions and cycles, normalization, quantizing to the project's palette, and the index plus preview a person approves — starting with `asset new --kind character`. Not for resources that package as an atlas (`sprite-icons`, `sprite-ui`, `sprite-tilemap`).
---

You own the whole run for an animated sprite sheet: going from nothing to
`dist/index.json` and the preview a person approves, one recorded stage at a
time. The four gates of this project fall inside this run — anchor, curated
frame set, palette lock, preview — and between them everything is measured and
repaired. The rules of the trade hold throughout: **every resize is nearest
neighbour** (one bilinear resize undoes the whole pixel pipeline) and **a hard
guide sits on the pixel grid**, never inside a block.

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the run after you.

**Stage 1 — the anchor image.** `asset new <key> --kind character` creates the
asset; the kind's profile carries the cell size, the anchor and the checks —
you do not invent them. `gen image` produces the anchor against the kind's
template (the paid call; a wrong anchor is every later paid call wasted), and
`tool bgremove` strips the chroma key — the free deterministic path first, the
model-backed `--model` path when the background is not clean chroma. The anchor
is the one neutral-pose frame every direction derives from; its recorded value
is what `tool align` later locks the cycle to. **GATE — the anchor image passed
by a person before anything derives from it.**

**Stage 2 — poses and cycles.** `tool board` lays out the empty cell grid the
generation step fills. `gen image` fills pose sheets against the anchor as the
reference, `gen video` makes a walk cycle (a wrong anchor wastes both). `tool
cut --grid` takes the sheet apart into one frame per pose, and `tool curate`
drops frames that say nothing new. **GATE — the curated frame set approved
before the style pass:** the price has been paid by now; what is judged is
whether the motion reads, which no measurement can decide.

**Stage 3 — clean and measure.** `tool snap` recovers the real pixel grid from
art that only looks like pixel art; `tool align` locks every frame to the
anchor so the sprite does not jitter; `tool doctor` measures the frames. Ship
clean: when `doctor` names a defect, apply the fix it names (the defect set
below) and re-measure.

**Stage 4 — the look.** `tool style` quantizes against the project's locked
`palette.json`, never ad-hoc colours: with no palette locked yet, `--preset
pico8|nes|gameboy|sweetie16` locks one in and applies it; once locked, the
preset is refused and the locked palette is applied. The dither decision —
ordered or Floyd-Steinberg — is recorded once under ``style:`` in ``ssc.yaml``,
never per call. **GATE — the palette lock, once per project:** every asset after
the first inherits the choice silently. `tool recolour` makes variants by
mapping one palette onto another — the free path a paid call would otherwise be
asked for.

**Stage 5 — hand over.** `ssc index` writes `dist/index.json`: the sheet, one
cell per frame, with cell, grid, fps, loop and the anchor that stops a renderer
re-centring the sprite. `ssc preview <key>` renders the animation as a GIF (or
`--contact` a labelled sheet, `--section windup` one range) straight from
`dist/`, so a person approves exactly what a renderer will load. **GATE here.**

## The defect set `doctor` names, and the fix each carries

- `pixel_grid` (fake pixels) → `tool snap`
- `bleed` (frame bleeding) → `tool cut`
- `drift` (frame drift) → `tool align`
- `halo` (chroma ring) → `tool bgremove`
- `palette` (palette drift) → `tool style` / `tool recolour`
- `flicker` (still region changing) → one palette for the whole frame set
- `silhouette` (holes/fragments) → `tool align`, `tool trim`

Repair what a check names, re-measure, and only stop when `doctor` is clean — or
hand back the named defect if it cannot be repaired, on a person rather than
silently carrying a broken frame toward the palette lock.

## What you hand over

`dist/index.json` and the preview a person approves — the end of the run. This
is it; there is no next skill.