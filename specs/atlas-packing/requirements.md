---
autonomy: auto
ci: wait
---

# Atlas packing — requirements

## Purpose

An animation is a grid of equal cells addressable by index. Everything else — an icon set, a
set of map pieces, a row of banners — is a set of differently sized images sharing one
texture, and addressing those by index is exactly wrong: the cell has to be the largest
entry, so most of the atlas is empty. This feature packs them by size instead, and reports
the rectangle each one landed in, which is what an engine reads. It is for the same two
callers as the rest of `ssc`: an operator who wants one texture instead of forty files, and
an agent that has to know where each entry went without opening the image.

The GPU is why two of these requirements exist. A renderer sampling at an entry's edge reads
the neighbouring texel, and at any filtering or scale other than 1:1 that shows up as a seam
of the wrong colour along one side of the sprite — from a file that looks perfect in an
image viewer.

## R1 · The atlas

- **R1.1** The `ssc` CLI shall place every input image into one atlas image at its own rectangle, moving pixels without resampling any.
- **R1.2** The `ssc` CLI shall report, for each entry, its id, its rectangle in the atlas, and its anchor within that rectangle.
- **R1.3** The `ssc` CLI shall derive an entry's id from its source filename, so that adding or removing one entry does not change another entry's id.
- **R1.4** If two inputs resolve to the same id, then the `ssc` CLI shall refuse the pack and name both files.
- **R1.5** The `ssc` CLI shall place the same inputs in the same rectangles on every run.
- **R1.6** If an entry cannot be placed within the atlas' bounds, then the `ssc` CLI shall refuse the pack and name the entry that did not fit.

## R2 · The gap between entries

- **R2.1** Where `--padding` is given, the `ssc` CLI shall leave that many pixels between an entry's rectangle and every other entry's, and between an entry's rectangle and the atlas edge.
- **R2.2** Where `--extrude` is given, the `ssc` CLI shall repeat each entry's border pixels that far outwards from its rectangle.
- **R2.3** If `--extrude` is larger than `--padding`, then the `ssc` CLI shall refuse the pack, because an extrusion wider than the gap writes into a neighbour.
- **R2.4** The `ssc` CLI shall report an entry's rectangle as the entry's own pixels, excluding anything extruded from them.

## R3 · Which sets are atlases

- **R3.1** Where a kind is named, the `ssc` CLI shall take the layout from that kind's profile.
- **R3.2** If a kind that animates is packed as an atlas, then the `ssc` CLI shall refuse and name the equal-cell sheet as the command that fits.

## Out of scope

**Rotating an entry to make it fit**, and **trimming an entry's transparent margin**. Both
buy space, both stop the reported rectangle from being the thing that was passed in, and
both need an engine that reads a per-entry transform. Whether they are worth that is a
question the index format should answer first — `specs/engine-index/` — not this leaf.

**A second page when one atlas will not hold everything.** R1.6 refuses instead, naming the
entry, because a caller handed two files back has to decide which one an entry is in, and
nothing downstream can express that yet.
