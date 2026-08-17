---
name: sprite-still
description: The complete flow for a still — one unanimated full-colour picture that packs whole. Use it when the work is a title strip, a banner or a menu header of the `banner` kind, or a world, level or minimap image of the `map` kind: `asset new --kind banner` or `--kind map`, one generation, the framing crop, the project's palette, and `ssc index` plus the preview at the end. Not for anything that animates (`sprite-sheet`), not for a scrolling backdrop in layers (`sprite-background`), and not for the concept piece a person approves before art derives from it (`sprite-boxart`).
---

You own the whole run for a still: from nothing to the atlas an engine loads and
the preview a person approves. A still is **one unanimated picture that packs
whole** — no anchor, no cycle, no cut-out on chroma, no nine-patch. Two kinds
are this run, and they differ in nothing but the numbers their profiles carry:
`banner` at `256x64` for a title strip or a menu header, `map` at `128x128` for
a world, level or minimap image. Read the size off the profile; do not type it
from memory. The rules of the trade hold: **every resize is nearest neighbour**.

One skill drives both because the stages are identical. If you find yourself
wanting a stage for one and not the other, the thing you are making is probably
neither — a background scrolls in layers (`sprite-background`) and a panel
stretches by guides (`sprite-ui`).

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the atlas after you.

**Stage 1 — the source.** `asset new <key> --kind banner` — or `--kind map` —
creates the asset; the kind's profile carries the cell size and the checks.
`gen image` produces the picture against the kind's template, and `gen image
--style` decides how it is drawn: the kind's style unless you override it, and a
still is where a project that is pixel art everywhere else often is not. Anchor
it with `--ref` where the still has to match art that already exists — a menu
header that shares nothing with the game it heads is the ordinary failure here,
and one reference fixes it. `--board` attaches a generated board where the style
names one.

  *The paid call, and what to set on it.* The default image model,
  `openai/gpt-image-2`. Raise `--count` while the composition is open — with
  `--quality` tiered down, because you are judging layout and not finish — then
  one image at `--quality high` for the one you keep. A still is generated once
  and read at one size, so this is a call worth paying at full quality exactly
  once. `ssc model show openai/gpt-image-2` names the options and the price
  text.

**Stage 2 — the frame.** A model returns the aspect it likes, not the aspect a
`256x64` strip is. `tool crop --aspect 4:1 --gravity centre` cuts to the shape
the kind states, and `--inset` takes a margin off every side where the model
left one. Crop before the palette, never after: a crop after quantizing throws
away colours the palette was fitted to.

**Stage 3 — clean and measure.** `tool doctor --in <file> --kind banner`
measures the result. Both kinds declare `palette` and nothing else, which says
what this run is: there is no cut-out to halo and no cell grid to fall off, and
the one thing that goes wrong is colour. What no check measures is whether the
picture reads as what it is for — a banner that is beautiful and illegible at
`256x64` passes every check there is. That judgement is Stage 5's gate, and it
is why the gate is not optional on this run.

**Stage 4 — the look.** `tool style` quantizes against the project's locked
`palette.json`, never ad-hoc colours: with no palette locked yet, `--preset
pico8|nes|gameboy|sweetie16` locks one in; once locked, the preset is refused
and the locked palette is applied. `tool recolour --from <hex> --to <hex>`
produces a variant — the same banner in the enemy faction's colours — with no
paid call at all. **GATE — the palette lock, once per project.**

**Stage 5 — hand over.** `ssc index` writes `dist/index.json`: one **atlas** per
kind (`atlas_layout: bin`) with a rect and an anchor per asset. `ssc preview
<address>` renders from `dist/` so a person approves exactly what an engine will
load, at the size it will load it. **GATE here** — and this is the gate that
answers the question no check does.

## The defect set, and the fix each carries

- `palette` (palette drift) → `tool style` / `tool recolour`
- `pixel_grid` (fake pixels, usually a resample) → `tool snap`
- the wrong aspect for the kind → `tool crop`

## What you hand over

`dist/index.json` — one atlas per kind, a rect and an anchor per asset — and the
preview a person approves. The end of the run.
