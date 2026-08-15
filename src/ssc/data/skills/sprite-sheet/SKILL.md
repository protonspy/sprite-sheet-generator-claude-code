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

**Stage 0 — the brief, when there is nothing to derive from.** `gen boxart`
produces the concept piece: what the character *is*, at full fidelity, before
anything decides how it is drawn. Only when the caller has no art of their own —
a commission, an earlier character, a sketch answers the same question for free.
**GATE — a person says yes, that is the character, before four directions and
five animations are derived from it.** The sprite then comes from it with `tool
pixelart`; never pass it as a reference to Stage 1, which `ssc` now refuses.

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
cut --grid` takes the sheet apart into one frame per pose, `tool clip` takes the
clip apart — it finds where the cycle closes and samples 8 to 12 frames across
that one repetition, never both ends of it — and `tool curate` drops frames that
say nothing new. **GATE — the curated frame set approved
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

## The paid calls, and what to set on each

Three of the stages above spend; nothing else in this run does. `ssc model show <id>`
gives a model's options and the provider's price text before you commit to either.

- **Stage 1, the anchor** — `gen image` on the default image model,
  `openai/gpt-image-2`. One image, `--quality high`, the size the kind asks for. This is
  the frame every other paid call derives from, so it is the one to pay properly for.
  **How it is drawn is a decision, not a default.** The kind carries the look — `pixel-art`
  unless the project declared otherwise under `kinds.<kind>.style` — and `--style` names
  another for one call: `pixel-art`, `vector`, `hand-painted`, `3d-render`, `flat`, or free
  text for anything else. Set it once at the anchor and leave it alone: every later frame
  derives from that image, and a style changed mid-run is a character that changes with it.
  Add `--board` here and only here — it attaches the checkerboard `pixel-art` names, which is
  what makes the anchor come back as blocks rather than as a painting of blocks. Every later
  call points at the approved anchor instead: `--ref <path>:identity`, repeatable, with
  `:palette` or `:pose` where a second image is doing a different job.
- **Stage 2, the pose sheets** — `gen image` again, and this is the call where `--count`
  earns its cost: generate several boards cheaply (`--count 3-4`, quality and size tier
  down), pick the composition that reads, then regenerate that one at full quality.
- **Stage 2, the walk cycle** — `gen video` on the default video model,
  `xai/grok-imagine-video/image-to-video`. Video bills per second of output, so generate
  the shortest clip that shows the cycle and loop it rather than cutting a long one down.
  `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` and
  `bytedance/seedance-2.5/image-to-video` are the alternatives when the default's motion
  does not hold; both take `--opt duration=…` rather than `--size`.

Everything after Stage 2 is a `tool` command: free, local, deterministic. A restyle is
`tool style`, a variant is `tool recolour`, a background is `tool bgremove` — never a
second paid call.

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