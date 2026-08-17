---
name: sprite-background
description: The complete flow for a scrolling background — own the run from an empty asset to the layer stack an engine scrolls. Use it when the work is a parallax backdrop of the `background` kind, the one kind whose profile is layered: `asset new --kind background`, one generation per layer, a common size, the project's palette, and `tool layers` reporting the scroll factor each layer moves at. Not for a single flat picture that never scrolls — a banner or a world map is `sprite-still` — and not for tiles that wrap (`sprite-tilemap`).
---

You own the whole run for a scrolling background: from nothing to the stack an
engine parallaxes and the preview a person approves. `background` is the one
kind whose profile says `layered`, and everything specific about this run
follows from that: a background is **several images that scroll at different
speeds**, not one image with depth in it. The rules of the trade hold: **every
resize is nearest neighbour** and **every layer is one size**, because they all
scroll across one viewport.

**Layers are an input, never a derivation.** Nothing here separates a flat
painting into depth planes. That is a computer-vision problem that is wrong
often and confidently, and a background that looks right until the camera moves
is worse than one that never shipped. You generate the sky, you generate the
hills, you generate the foreground — three calls, three files, in that order.

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the stack after you.

**Stage 1 — the layers.** `asset new <key> --kind background` creates the asset;
the kind's profile carries the cell size and the checks — you do not invent
them. Then one `gen image` per layer, far to near, each at the same size, each
naming what is at that depth and nothing else: a hills layer with a sky painted
behind it cannot scroll, because the sky is now moving at the hills' speed.
`gen image --style` decides how the art is drawn — the kind's style unless you
override it — and a background is one of the places a non-pixel style earns its
keep. Pass the layer before it with `--ref` when the palette or the light has to
carry across, and say which of the two you are anchoring.

  *The paid call, and what to set on it.* The default image model,
  `openai/gpt-image-2`. Raise `--count` while the composition is still open —
  with `--quality` tiered down, to judge the shape of the horizon — then drop
  back to one image at `--quality high` for the layer you keep. Ask for the size
  the kind states. A layer regenerated at a different size cannot join the stack
  without a resample, and a resampled background is where fake pixels enter a
  run that had none. `ssc model show openai/gpt-image-2` names the options and
  the price text.

**Stage 2 — one size.** `tool layers` refuses a stack whose images are not all
one size, and reports the sizes it found. `tool expand --to <width>x<height>`
brings a short layer up to the viewport rather than scaling it: a layer is
extended with what is around it, never stretched, because stretching moves every
edge in it off the grid.

**Stage 3 — clean and measure.** `tool doctor --in <dir> --kind background`
measures the result. The kind declares `palette`, which is the check that
matters across a stack: three layers generated in three calls drift apart in
colour, and drift between layers reads as haze the moment they move at different
speeds. Apply the fix each named defect carries and re-measure until clean.

**Stage 4 — the look.** `tool style` quantizes against the project's locked
`palette.json`, never ad-hoc colours: with no palette locked yet, `--preset
pico8|nes|gameboy|sweetie16` locks one in; once locked, the preset is refused
and the locked palette is applied. Run it over every layer, not the hero layer
alone. **GATE — the palette lock, once per project.**

**Stage 5 — the stack.** `tool layers --in <dir> --scroll 0.2,0.5,1` reports the
layers in order, each with its file and its scroll factor. Give the factors far
to near, one per layer; omit `--scroll` and one is derived per layer from its
position, which is a starting point and not a decision. A factor outside zero to
one is refused: zero is infinitely far away and one moves with the camera.

**Stage 6 — hand over.** `ssc index` writes `dist/index.json`, where the
background lands as an atlas entry like any other unanimated asset, and `ssc
preview <address>` renders from `dist/` so a person approves what an engine will
load. **The index carries no scroll factor** — the `tool layers` report is where
that number lives, and the engine's scroller is what reads it. Say so when you
hand over, rather than letting the next person look for it in the index.
**GATE here.**

## The defect set, and the fix each carries

- `palette` (palette drift, within a layer or between them) → `tool style` / `tool recolour`
- `pixel_grid` (fake pixels, usually a resample) → `tool snap`
- layers of different sizes (`tool layers` refuses the stack) → `tool expand`

## What you hand over

The layer files in order, the `tool layers` report carrying a scroll factor per
layer, `dist/index.json`, and the preview a person approves. The end of the run;
you do not scroll anything, and neither does `ssc`.
