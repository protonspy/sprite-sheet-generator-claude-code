# Sheet assembly — design

## What changes

Serves R1.4, R3.2, R3.3, R4.2, R4.4.

- **`core/assemble.py`** — pure: pad a frame, flip one, find the offsets that put a set on a
  common anchor, and lay a set out in cells. `ndarray` in, `ndarray` out.
- Three commands added to `cli/commands/recover.py`, which already holds the three that read
  a sheet apart; this is the same shape — a set in, a set or a sheet out — and putting the
  taking-apart next to the putting-back keeps `convert.py` for the four that only ever
  transform one frame at a time.

Every resize is `core.resize`, and none of these four needs one: padding, flipping, shifting
and laying out are all placements rather than resamplings. That is the point of the leaf —
**the pixels are moved, never recomputed**, so nothing here can reintroduce the blur `snap`
removed.

## The anchor is the whole of `align`

`doctor` already defines where the feet are, in `core/doctor/masks.py::anchor`: the lowest
occupied row, and the centre of the body *in that row*. Not the centroid and not the centre
of the bounding box, because both move when an arm swings, which would read as drift while
the feet stayed put. `align` reuses it rather than defining a second one — two functions
answering "where is this sprite anchored" that could disagree is the defect, not the saving.

R3.3 is the part that is easy to get wrong: once every frame's anchor is known, the common
anchor has to sit far enough inside the canvas that no frame's content is pushed off it.
That is `max` over the set of each frame's distance from its anchor to its own edges, which
is why `align` grows the canvas rather than shifting within it — a shift that fitted every
frame would only exist if the anchors happened to be arranged conveniently.

## `pack` records the anchor, and that is not decoration

A sheet without its anchor makes the engine re-centre the sprite, and the drift `align` just
removed comes back at runtime. So the cell, the grid and the anchor's position *within the
cell* are reported (R4.4) — `engine-index` will emit them, and this leaf is where they are
measured.

## Risks

**`align` can grow a canvas a lot**, and the read-side ceilings do not bound it: they bound
what comes in, not what alignment produces from it. Two frames anchored near opposite
corners need a canvas covering both, and every frame in the set gets one. `MAX_CANVAS` caps
it (R3.6), on the *result* rather than on any flag — which is the only place a cap works,
because all three of these multiply: `--cols` by the cell, `--by` by two, and the anchor
spread by nothing at all.

**`align` and `pack` have to agree on which anchor they mean.** `pack` measures the anchor
its frames share, and measuring `feet` on a set aligned by `centre` gives the wrong pixel
*and* falsely reports the set unaligned. `align` emits the mode it used and `pack --anchor`
takes it; there is no way for the two to derive it from the frames alone, so it travels
between them as a value.
