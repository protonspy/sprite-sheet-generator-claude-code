---
autonomy: auto
ci: wait
---

# Image transforms — requirements

## Purpose

Flipping and turning a frame set, as editing operations a caller reaches for directly.
`tool mirror` already exists as the free way to get East from West; this widens it to the
other axis and adds quarter-turn rotation, which `tile` and `map` work needs and which no
command offers today.

The reason this is a spec rather than two lines of numpy: **an exact transform of the
pixels is not an exact transform of the asset.** A frame carries an anchor, and later a set
of boxes and markers, and a transform that moves the pixels without moving those leaves a
record that is quietly wrong — invisible until something is drawn or hit in the wrong
place.

## R1 · The transforms

- **R1.1** The `ssc` CLI shall mirror a frame set about the vertical axis or about the horizontal axis, as the caller names.
- **R1.2** The `ssc` CLI shall rotate a frame set by one, two or three quarter turns.
- **R1.3** If a rotation is asked for that is not a whole number of quarter turns, then the `ssc` CLI shall refuse it and report that no other angle exists without resampling.
- **R1.4** The `ssc` CLI shall transform every frame of a set by the same transform.
- **R1.5** The `ssc` CLI shall trim a frame set to one box containing the opaque pixels of every frame in that set.
- **R1.6** The `ssc` CLI shall offset a frame set by a whole number of pixels on either axis.

## R2 · What travels with the pixels

- **R2.1** When a frame set is transformed, the `ssc` CLI shall apply that same transform to the set's recorded anchor.
- **R2.2** Where a frame carries per-frame boxes or markers, the `ssc` CLI shall apply that same transform to each of them.
- **R2.3** The `ssc` CLI shall record which transform produced a file in that file's provenance.
- **R2.4** If a rotation by an odd number of quarter turns would leave a frame that no longer fits its kind's cell, then the `ssc` CLI shall report the new dimensions and the cell they no longer match.

## Out of scope

**Rotation by any other angle.** Nearest neighbour is the only resampler this project has
(`workspace-foundation` R4.4, enforced by `tests/test_no_other_resampler.py`), and every
angle that is not a quarter turn needs interpolation to decide what lands on a pixel that
no source pixel maps onto. That is the sub-pixel blur `snap` exists to remove. R1.3 is the
refusal, not a gap waiting to be filled.

**Noticing that a mirror was semantically wrong.** A sheath, a scar, a pauldron or a book
under one arm moves to the wrong side when mirrored, and
`docs/wiki/anchor-and-directions.md` records that this is not detectable at a glance.
It is not detectable by this tool either — telling a costume detail from a body is a vision
problem. What is owed instead is R2.3: the provenance says the file was mirrored, so a
reader who sees the sheath on the wrong hip can find out why.

**Arbitrary per-frame transforms.** R1.4 is deliberate, and R1.5 is where it bites hardest:
trimming each frame to its *own* bounding box is the obvious implementation and it destroys
the animation, because a character that is two pixels narrower in one frame gets shifted two
pixels in that frame alone. One box across the whole set is the same reasoning that makes
`snap` and `pixelart` take a frame set rather than a file — a decision computed per frame is
a decision that disagrees with itself.

**Trim deciding it knows better than the cell.** R1.5 trims and R2.1 moves the anchor, and
that is all. It does not then re-pack, re-align or resize to fit a kind's cell: those are
`sheet-assembly`'s and they are separate commands on purpose.
