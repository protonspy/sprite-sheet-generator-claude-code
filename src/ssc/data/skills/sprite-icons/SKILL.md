---
name: sprite-icons
description: The complete flow for a set of icons — own the run from an empty asset to the atlas a person approves. Use it when the work is game UI icons or item/ability icons, anything of the `icon` kind, which packages as one atlas per kind rather than as a sheet: `asset new --kind icon`, generation, background removal, quantizing to the project's palette, and `ssc index` plus the preview at the end. Not for animated sheets (`sprite-sheet`) and not for stretchable panels (`sprite-ui`).
---

You own the whole run for a set of icons: going from nothing to the atlas an
engine loads and the preview a person approves. Icons are a resource kind — they
do not animate, so there is no anchor and no cycle — and they package as one
**atlas** per kind, a rect and an anchor per asset, not as a sheet. The run is
shorter than `sprite-sheet`'s and skips the gates that exist only for motion.
The rules of the trade hold: **every resize is nearest neighbour** and **a hard
guide sits on the pixel grid**, never inside a block.

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the atlas after you.

**Stage 1 — the source.** `asset new <key> --kind icon` creates the asset; the
kind's profile carries the cell size and the checks — you do not invent them.
`gen image` produces the source against the kind's template — the one paid call
on this path — and `tool bgremove` strips the chroma-key background, the same
free path an animated sheet uses. Use the model-backed `--model` path only when
the background is not clean chroma.

  *The one paid call, and what to set on it.* The default image model,
  `openai/gpt-image-2`. An icon set is the case `--count` is for: icons are
  small and a sheet of them is cheap, so generate several candidates with the
  quality and the size tier down, pick the one that reads at cell size, and
  regenerate that one at `--quality high`. Past the kind's cell size a larger
  `--size` buys nothing — the frame is downsampled to the grid anyway.
  `ssc model show openai/gpt-image-2` names the options and the price text.

  *What decides the look, and what anchors it.* `gen image --style` says how the
  art is drawn — the kind's style unless you override it — so a project whose
  icons are flat or vector asks for that here rather than fighting a pixel-art
  template. `--ref` anchors a call on art that already exists, and a set of
  icons is the case it was built for: generate the first, then pass it as the
  reference for every icon after, saying what it is anchoring — the palette and
  the line weight, not the subject. `--board` attaches a generated board where
  the style names one. A first icon with nothing to anchor it stops at a box-art
  gate before anything derives from it — that run is `sprite-boxart`. `tool crop
  --inset` takes off the margin a model leaves around a small subject, and it is
  free: never pay a second call to reframe one.

**Stage 2 — clean and measure.** `tool snap` recovers the real pixel grid where
the source came in smeared. `tool doctor` measures the result against the
kind's checks: `pixel_grid`, `halo`, `palette`, `silhouette`. Ship clean: apply
the fix each named defect carries and re-measure.

**Stage 3 — the look.** `tool style` quantizes against the project's locked
`palette.json`, never ad-hoc colours: with no palette locked yet, `--preset
pico8|nes|gameboy|sweetie16` locks one in and applies it; once locked, the
preset is refused and the locked palette is applied. The dither decision is
recorded once under ``style:`` in ``ssc.yaml``, never per call. **GATE — the
palette lock, once per project** (a project's icons inherit the first asset's
choice silently). `tool recolour` makes recoloured variants free.

**Stage 4 — hand over.** `ssc index` writes `dist/index.json`: one **atlas** per
`icon` kind — the `icon` profile declares `atlas_layout: bin` — with a rect and
an anchor per asset, one texture bind for the whole set. `ssc preview <address>`
renders from `dist/` so a person approves exactly what an engine will load.
**GATE here.**

## Your gates

Two of the four project gates fall inside this run, held as state in the
workspace — a pending one is exit code `3` and a `review/` directory, never a
question asked in conversation. You do not decide at a gate: you surface it and
stop.

1. **The palette lock**, once per project, before anything is quantized against
   the palette.
2. **The preview**, at the end, rendered from `dist/`.

There is no anchor gate and no curated-frame-set gate: nothing animates here, so
neither question is asked.

## What you hand over

`dist/index.json` — one atlas per icon kind, a rect and an anchor per asset —
and the preview a person approves. The end of the run; there is no next skill.