---
name: sprite-tilemap
description: The complete flow for a set of seamless tiles and the tileset an engine reads — own the run from an empty asset to `dist/index.json`. Use it when the work is ground, wall or decor tiles of the `tile` kind that must wrap on every side: `asset new --kind tile`, generation, closing the wrap with `tool tile`, the `seam` check, quantizing to the project's palette, and `ssc index` plus the preview at the end. Not for animated sheets (`sprite-sheet`) and not for icons or panels (`sprite-icons`, `sprite-ui`).
---

You own the whole run for a tile set and the tileset an engine loads: going from
nothing to `dist/index.json` and the preview a person approves. Tiles are a
resource kind — they do not animate, so there is no anchor and no cycle — and
they package as one **tileset** per kind, the cell grid plus an id per tile. The
one fact specific to a tile is the wrap: the right edge must continue into the
left edge, or an engine repeats a visible seam across the floor. The rules of
the trade hold: **every resize is nearest neighbour** and **a hard guide sits on
the pixel grid**, never inside a block.

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the tileset after you.

**Stage 1 — the source.** `asset new <key> --kind tile` creates the asset; the
kind's profile carries the cell size and the checks — you do not invent them.
`gen image` produces the source against the kind's template — the one paid call
on this path — and `tool bgremove` strips the chroma-key background, the same
free path the other resource kinds use.

  *The one paid call, and what to set on it.* The default image model,
  `openai/gpt-image-2`. One image at `--quality high`, at the kind's cell size —
  a tile is judged on whether it wraps, and `tool tile` in Stage 2 closes the
  wrap for free, so paying for several candidates buys a choice you do not need.
  Raise `--count` only when the texture itself is what is in question.
  `ssc model show openai/gpt-image-2` names the options and the price text.

**Stage 2 — close the wrap.** `tool tile` makes the tile meet itself on every
side. `edge`, the default, copies the last column over the first and the last
row over the first, so across the wrap neighbouring pixels are identical by
construction — it costs one column and one row of the art, and it is the
smallest change that closes the boundary. `mirror` makes the right half the
left half flipped and the bottom half the top half flipped — both wraps close
because the tile is symmetric, and the cost is the symmetry, which reads as a
pattern on a large floor. Run this before the style pass; a tile that does not
wrap is a tile that shows seams. **Never run `tool tile` on a tile that already
wraps and expect it to stay untouched in `edge` mode — the copy is idempotent,
but run it twice over a tile that does not wrap and the second pass is a real
edit, so measure before and after with `tool doctor`.**

**Stage 3 — clean and measure.** `tool doctor` measures the result. The `seam`
check measures the mean absolute difference across each wrap boundary against
the mean difference between interior neighbours on the same axis, so one default
works for a noisy tile and a flat one alike — a tile that already wraps scores
about 1, and a hard seam scores well above. The kind's other checks —
`pixel_grid`, `palette` — fix the way they always do (see the defect map
below). Apply the fix each named defect carries and re-measure until clean.

**Stage 4 — the look.** `tool style` quantizes against the project's locked
`palette.json`, never ad-hoc colours: with no palette locked yet, `--preset
pico8|nes|gameboy|sweetie16` locks one in; once locked, the preset is refused
and the locked palette is applied. The dither decision is recorded once under
``style:`` in ``ssc.yaml``, never per call. **GATE — the palette lock, once per
project.**

**Stage 5 — hand over.** `ssc index` writes `dist/index.json`: one **tileset**
per `tile` kind — the `tile` profile declares `atlas_layout: grid` — the cell
grid plus an id per tile, all of them one size (a tileset of mixed sizes is a
refusal, not something to pad around). `ssc preview <address>` renders a tile
2×2, the smallest arrangement that puts every edge against a copy of the
opposite one — the only question a single tile raises is its seam. It reads
from `dist/` so a person approves exactly what an engine will load. **GATE
here.**

## The defect set, and the fix each carries

- `pixel_grid` (fake pixels) → `tool snap`
- `palette` (palette drift) → `tool style` / `tool recolour`
- `seam` (a tile's edges do not continue into each other) → `tool tile`

## What you hand over

`dist/index.json` — one tileset per tile kind, equal cells with an id per tile —
and the preview a person approves. The end of the run; there is no next skill.