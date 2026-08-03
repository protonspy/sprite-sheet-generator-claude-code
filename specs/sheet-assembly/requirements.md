---
autonomy: auto
ci: wait
---

# Sheet assembly — requirements

## Purpose

Putting the pieces back on a grid. `expand` pads a canvas, `mirror` flips one, `align`
locks every frame to a common anchor, and `pack` lays them out as a sheet with that anchor
recorded.

**`expand` is split from `gen expand` by what it costs, not by what it does.** Padding a
canvas is deterministic and free; outpainting is a model inventing content and bills. One
name for both would hide the price behind a flag.

It is also here because the padding already happens — implicitly, inside `align` and `pack`,
where it writes no `meta.json` entry and so cannot be reproduced or debugged. Making it a
command is what turns an invisible step into a recorded one.

## R1 · `expand`

- **R1.1** Where `--to <W>x<H>` is given, the `ssc` CLI shall place the frame on a canvas of that size.
- **R1.2** Where `--by <n>` is given, the `ssc` CLI shall add that many pixels on every side.
- **R1.3** Where `--fill` names a colour, the `ssc` CLI shall fill the added area with it; otherwise the added area shall be transparent.
- **R1.4** The `ssc` CLI shall centre the original content on the new canvas, and shall place it on the bottom edge where the anchor is `bottom` or `feet`.
- **R1.5** If the target is smaller than the frame on either side, then the `ssc` CLI shall write nothing and exit `2`.
- **R1.6** If a canvas would be larger than the canvas ceiling on either side, then the `ssc` CLI shall write nothing and exit `2`.

## R2 · `mirror`

- **R2.1** When `ssc tool mirror` runs, the `ssc` CLI shall flip each frame horizontally.
- **R2.2** When it mirrors a frame, the `ssc` CLI shall report that the result is mirrored.

## R3 · `align`

- **R3.1** The `ssc` CLI shall accept the anchor as `feet`, `bottom` or `centre`.
- **R3.2** When `ssc tool align` runs, the `ssc` CLI shall move each frame so that every frame's anchor lands on the same pixel of the canvas.
- **R3.3** The `ssc` CLI shall place that common anchor where no frame's content leaves the canvas.
- **R3.4** If a frame holds nothing opaque, then the `ssc` CLI shall leave it where it is and report it.
- **R3.5** Where `--onion` is given, the `ssc` CLI shall also write one image with every aligned frame drawn over the others.
- **R3.6** If aligning a set would need a canvas past the ceiling, then the `ssc` CLI shall write nothing and exit `2`.

## R4 · `pack`

- **R4.1** When `ssc tool pack` runs, the `ssc` CLI shall write one image holding every frame in a grid of equal cells.
- **R4.2** The `ssc` CLI shall size the cell to the largest frame unless `--cell <W>x<H>` is given.
- **R4.3** If a frame does not fit the cell, then the `ssc` CLI shall write nothing and exit `2`.
- **R4.4** When it packs, the `ssc` CLI shall report the cell, the columns, the rows and the anchor within the cell, measured from the frames.
- **R4.6** If the frames do not share one anchor, then the `ssc` CLI shall report that they do not.
- **R4.7** The `ssc` CLI shall accept the anchor `pack` measures, and shall report from `align` the one it used.
- **R4.5** If a sheet would be larger than the canvas ceiling on either side, then the `ssc` CLI shall write nothing and exit `2`.

## Out of scope

- **Aligning on eyes.** The plan names it, and it needs a detector rather than a
  measurement — `feet` is the lowest opaque row and is exact, while eyes are a model's
  guess. It belongs with the CV leaves in M6, and `--anchor` is an open set so adding it
  later costs nothing here.
- **Outpainting.** `gen expand` bills and returns a job; this leaf's `expand` is `np.pad`
  with the arithmetic written down.
- **What the engine reads.** `pack` reports the anchor and the grid; `dist/index.json` is
  `specs/engine-index/`.
