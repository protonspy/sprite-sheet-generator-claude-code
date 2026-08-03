---
autonomy: auto
ci: wait
---

# Frame recovery — requirements

## Purpose

Getting N pieces out of one image, in three modes, and binding them two ways.

`ssc tool cut` binds the pieces as the frames of one animation; `ssc tool slice` binds them
as N distinct assets, each with its own key and its own lineage. They are the same detector
with different output bindings, which is why they are one leaf: splitting them by binding
would have produced the same three detection modes twice.

**This is how existing material gets in**, and that is why it is M1. Without `slice`, M1's
promise — "repairs a sheet you already have" — only holds for somebody whose asset is
already cut apart, which is nobody. And a sheet of unknown origin has to be cuttable without
the caller already knowing its layout, which is why grid auto-detection is here rather than
deferred.

## R1 · Finding the pieces

- **R1.1** Where `--grid <cols>x<rows>` is given, the `ssc` CLI shall cut the image into that many equal cells.
- **R1.2** Where no mode is given, the `ssc` CLI shall detect the grid from the image.
- **R1.3** If no grid can be detected, then the `ssc` CLI shall exit `1` and report that the layout has to be given.
- **R1.4** Where `--mode chroma` is given, the `ssc` CLI shall take each piece as the bounding box of a region that is not the key colour.
- **R1.5** Where `--mode islands` is given, the `ssc` CLI shall take each piece as the bounding box of one connected opaque region.
- **R1.6** Where `--min-size` is given, the `ssc` CLI shall discard a piece smaller than it on either side.
- **R1.7** Where `--max-aspect` is given, the `ssc` CLI shall discard a piece whose longer side exceeds its shorter side by more than that ratio.
- **R1.8** The `ssc` CLI shall order the pieces top to bottom, then left to right.
- **R1.9** If an image yields more separate regions than the piece ceiling, then the `ssc` CLI shall find no pieces in it and exit `1`.
- **R1.10** If a stated grid is more cells than the cell ceiling, then the `ssc` CLI shall cut nothing and exit `2`.

## R2 · Detecting a grid

- **R2.1** When it detects a grid, the `ssc` CLI shall report the columns, rows, cell size, margin and spacing it observed.
- **R2.2** The `ssc` CLI shall report a cell that encloses the content it found, and a spacing that is the gap between one cell and the next.
- **R2.3** Where the image has margins around the grid, the `ssc` CLI shall exclude them from every cell.
- **R2.4** If the content it finds is not laid out regularly, then the `ssc` CLI shall report no grid.

## R3 · Binding the pieces

- **R3.1** When `ssc tool cut` runs, the `ssc` CLI shall write the pieces as the numbered frames of one animation.
- **R3.2** When `ssc tool slice` runs, the `ssc` CLI shall write each piece as its own asset, each carrying its own key.
- **R3.3** Where the destination is an asset, the `ssc` CLI shall record each piece's provenance, its stage and its class.
- **R3.4** Where the destination is a plain path, the `ssc` CLI shall write the pieces as files and record nothing.
- **R3.6** If neither destination is given, or both are, then the `ssc` CLI shall write nothing and exit `2`.
- **R3.7** If the named asset resolves outside the workspace's `assets/` directory, then the `ssc` CLI shall write nothing and exit `1`.
- **R3.5** When it writes pieces, the `ssc` CLI shall report how many it found and where each went.

## R4 · Curating

- **R4.1** When `ssc tool curate` runs, the `ssc` CLI shall report which frames are redundant.
- **R4.2** The `ssc` CLI shall treat a frame as redundant when it differs from the frame before it by less than the given threshold.
- **R4.3** Where `--drop` is given, the `ssc` CLI shall write only the frames it kept.
- **R4.4** The `ssc` CLI shall keep the first frame of a set always.

## Out of scope

- **Deciding how many frames an animation should have.** `curate` reports and, when asked,
  drops on a measured threshold. Which frames an action actually needs is a judgement, and
  it belongs to `sprite-animation` in M4.
- **Putting the pieces back.** `expand`, `mirror`, `align` and `pack` are
  `specs/sheet-assembly/`, which follows this leaf because it assembles what this produces.
- **Detecting the sheet's chroma for the caller.** The key is given, exactly as in
  `specs/background-removal/`, and for the same reason: a wrong guess eats the sprite.
