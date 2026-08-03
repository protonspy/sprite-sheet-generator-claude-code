---
autonomy: auto
ci: wait
---

# UI assets — requirements

## Purpose

A panel or a button is drawn once and displayed at a hundred sizes. What makes that possible
is a nine-patch: four guides dividing the image into corners that never stretch, edges that
stretch along one axis, and a centre that stretches both ways. This feature produces those
guides, measures whether the art can survive being stretched at them, and packs a control's
states into one sheet. It is for whoever has a panel that looks wrong at 200 pixels wide, and
for an agent that needs the four numbers an engine wants.

The command is `ninepatch` and not `slice`, because `specs/frame-recovery/` already owns
`slice` for a different operation.

## R1 · The guides

- **R1.1** When `ssc tool ninepatch` runs, the `ssc` CLI shall report the four guides — left, right, top and bottom — that divide the image into nine regions.
- **R1.2** The `ssc` CLI shall place every guide on the art's pixel grid, because a guide inside a block makes an engine stretch part of one pixel-art pixel.
- **R1.3** Where guides are given, the `ssc` CLI shall use them; where none are, it shall derive them from the art's pixel size.
- **R1.4** If a guide falls outside the image, or the two guides on one axis meet or cross, then the `ssc` CLI shall refuse and report the guides it was given.
- **R1.5** The `ssc` CLI shall report the size of each of the nine regions.
- **R1.6** If the guides given are not four whole numbers within the range a distance in pixels may take, then the `ssc` CLI shall refuse them and say how to write them.

## R2 · Measuring the stretch

- **R2.1** The `ssc` CLI shall measure `nineslice` as the variation within each stretched region along the axis that region stretches on.
- **R2.2** When `nineslice` finds variation above its threshold, the `ssc` CLI shall name `ssc tool ninepatch` as the fix.
- **R2.3** Where `nineslice` was not asked for, the `ssc` CLI shall report it as skipped rather than leaving it out.
- **R2.4** If the guides it needs were not given, then the `ssc` CLI shall report `nineslice` as skipped, with the reason.

## R3 · States

- **R3.1** When `ssc tool states` runs, the `ssc` CLI shall write one sheet holding a control's states in a fixed order, and shall report each state's name and rectangle.
- **R3.2** If a file names a state it does not know, then the `ssc` CLI shall refuse the set and report the states it knows.
- **R3.3** If the states are not all one size, then the `ssc` CLI shall refuse and report the sizes it found.
- **R3.4** If two files name the same state, then the `ssc` CLI shall refuse the set and name both files.

## Out of scope

**Deciding where the guides belong by looking at the art.** Finding the corner of a drawn
border is an edge-detection problem with a confident wrong answer, and a wrong guide is
invisible until the panel is stretched. R1.3's derivation is arithmetic on the pixel size,
not a reading of the picture, and a caller who knows better passes the guides.

**Stretching anything.** `ssc` reports the guides; the engine stretches. What a stretched
panel looks like belongs with the other previews in `specs/engine-index/`.
