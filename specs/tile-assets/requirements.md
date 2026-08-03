---
autonomy: auto
ci: wait
---

# Tile assets — requirements

## Purpose

A tile is judged by what happens at its edges: laid next to copies of itself, its right edge
meets its own left edge, and any discontinuity there reads as a grid of visible lines across
the whole floor. No image model closes that wrap on request, so this is the fix-and-measure
half of the loop the plan describes — `tool tile` closes the wrap, and `doctor`'s `seam`
check says whether it actually closed. It is for whoever has a tile that does not tile, and
for an agent that cannot look at four copies of it and judge.

## R1 · Closing the wrap

- **R1.1** When `ssc tool tile` runs, the `ssc` CLI shall write an image whose opposite edges meet without a discontinuity, by copying pixels and never by blending them.
- **R1.2** Where `--mode mirror` is given, the `ssc` CLI shall make the tile symmetric about both axes instead of copying its edges.
- **R1.3** The `ssc` CLI shall report which edges it changed and how many pixels that changed.
- **R1.4** If the input is smaller than two pixels on a side, then the `ssc` CLI shall refuse it, because there an edge and its opposite are the same pixel.
- **R1.5** Where `--in` names a set, the `ssc` CLI shall close each image's wrap independently.

## R2 · Measuring the seam

- **R2.1** The `ssc` CLI shall measure `seam` as the difference across each wrap boundary, expressed against the same difference measured between the image's own neighbouring rows and columns.
- **R2.2** When `seam` reports a discontinuity above its threshold, the `ssc` CLI shall name `ssc tool tile` as the fix.
- **R2.3** If the input is smaller than two pixels on a side, then the `ssc` CLI shall report `seam` as skipped, with the reason.
- **R2.4** Where `seam` was not asked for, the `ssc` CLI shall report it as skipped rather than leaving it out.

## R3 · The tileset

- **R3.1** Where a kind declaring the grid layout is packed, the `ssc` CLI shall report the tile size and one id per tile, each id derived from its source filename.
- **R3.2** If the tiles of such a set are not all one size, then the `ssc` CLI shall refuse the pack and report the sizes it found.

## Out of scope

**Autotile — Wang tiles, bitmask variants, terrain transitions.** A shipping paid competitor
has none either, which is not proof the deferral is right but does mean leaving it out is
not a gap against the market.

**A blend mode.** Averaging across the wrap is the usual way to close a seam, and it is
wrong here twice over: it invents colours that are not in the palette, and it softens
exactly the hard edges `snap` exists to produce. Both modes here move pixels that already
exist.

**The 2×2 tiled preview.** It belongs with everything else `ssc preview` renders — see
`specs/engine-index/`. The measurement is what an agent acts on and is this leaf's; the
picture is what a person trusts, and it arrives with the other pictures.
