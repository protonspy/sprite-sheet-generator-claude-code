---
name: sprite-ui
description: The complete flow for a UI or HUD panel — own the run from an empty asset to the nine-slice border an engine reads. Use it when the work is a `ui` asset — a panel, a button, a HUD frame, something an engine stretches — from `asset new --kind ui`, through `tool ninepatch` and the `nineslice` check, to `ssc index` plus the preview at the end. Not for animated sheets (`sprite-sheet`) and not for icons (`sprite-icons`).
---

You own the whole run for a UI or HUD panel: going from nothing to the atlas an
engine loads and the preview a person approves. UI is a resource kind — it does
not animate, so there is no anchor and no cycle — and it packages into one
**atlas** per kind, each entry carrying the four stretch borders. The one fact
specific to UI, and the thing nothing else on the relay does, is the nine-patch:
a panel is generated, its guides are reported, and an engine stretches it by
those numbers. The rules of the trade hold: **every resize is nearest neighbour**
and **a hard guide sits on the pixel grid**, never inside a block — a guide at 9
with a pixel size of 4 puts the boundary inside a block, and the border shimmers
at some widths and not others.

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the atlas after you.

**Stage 1 — the source.** `asset new <key> --kind ui` creates the asset; the
kind's profile carries the cell size and the checks — you do not invent them.
`gen image` produces the source against the kind's template (the one paid call
on this path) and `tool bgremove` strips the chroma-key background behind
the panel. Use the model-backed `--model` path only when the background is not
clean chroma.

  *The one paid call, and what to set on it.* The default image model,
  `openai/gpt-image-2`. One image at `--quality high`: a panel is stretched by
  its nine-patch rather than regenerated per size, so this call is paid once and
  reused at every size the UI asks for. Ask for the size the kind states — the
  guides in Stage 2 have to land on the pixel grid, and a resample to fit would
  move them. Raise `--count` only while the panel's design is still open — with
  the quality and the size tier down, to judge the shape — and drop back to one
  image at full quality once it is settled. `ssc model show openai/gpt-image-2`
  names the options and the price text.

  *What decides the look, and what anchors it.* `gen image --style` says how the
  art is drawn — the kind's style unless you override it — and UI is where a
  pixel-art project most often is not pixel art. `--ref` anchors a call on art
  that already exists: generate the panel, then pass it as the reference for the
  buttons and the HUD frame, so one interface does not arrive in three visual
  languages. `--board` attaches a generated board where the style names one. A
  first panel with nothing to anchor it stops at a box-art gate before anything
  derives from it — that run is `sprite-boxart`. `tool crop --inset` trims a
  margin the model left, for free; crop before Stage 2, because the guides are
  measured off the art as it stands.

**Stage 2 — the guides.** `tool ninepatch` reports the guides an engine
stretches the panel by. Omit `--guides` to read the derived one-pixel-art-pixel
ones off the art and adjust from the reported nine region sizes; a derived
guide is the smallest that can be right, not the right one for a panel with a
four-pixel bevel. The guides are the contract an engine reads, so they are a
fact about the art, not a staging choice.

**Stage 3 — clean and measure.** `tool doctor` measures the result. The
`nineslice` check reports, for each stretched region, the variation along its
own stretch axis — a left edge that changes down its height cannot be
stretched vertically without smearing, whatever its score in the direction it
does not stretch. The kind's other checks — `pixel_grid`, `halo`, `palette` —
fix the way they always do (see the defect map below). Apply the fix each named
defect carries and re-measure until clean.

**Stage 4 — the look.** `tool style` quantizes against the project's locked
`palette.json`, never ad-hoc colours: with no palette locked yet, `--preset
pico8|nes|gameboy|sweetie16` locks one in; once locked, the preset is refused
and the locked palette is applied. The dither decision is recorded once under
``style:`` in ``ssc.yaml``, never per call. **GATE — the palette lock, once per
project.**

**Stage 5 — hand over.** `ssc index` writes `dist/index.json`: one **atlas** per
`ui` kind (`atlas_layout: bin`) with a rect per asset **and** the four stretch
borders on every entry — a `ui` entry does not collapse on a hard engine
stretch. `ssc preview <address>` renders from `dist/` so a person approves
exactly what an engine will load. **GATE here.**

## The defect set, and the fix each carries

- `pixel_grid` (fake pixels) → `tool snap`
- `halo` (chroma ring) → `tool bgremove`
- `palette` (palette drift) → `tool style` / `tool recolour`
- `nineslice` (a stretch breaks, or guides fall between pixels) → `tool ninepatch`

## What you hand over

`dist/index.json` — one atlas per `ui` kind, a rect per asset, the four stretch
borders on every entry — and the preview a person approves. The end of the run;
there is no next skill.