---
autonomy: auto
ci: wait
---

# Pixel art conversion — requirements

## Purpose

Three commands that turn art into pixel art, none of which needs a workspace, an API key
or a character. `ssc tool snap` recovers the real grid from art that only looks like pixel
art. `ssc tool pixelart` converts art of any origin into true pixel art. `ssc tool board`
generates the two reference images the generation step will need, so that nobody has to
download somebody else's PNG under a licence this project does not have.

They are one leaf because they share the thing that makes them correct: a **set of frames
is converted as a set**, on one grid and one palette. Quantizing each frame on its own is
what produces `flicker`, and no post-process fixes it.

## R1 · Input and output

- **R1.1** The `ssc` CLI shall run `snap`, `pixelart` and `board` outside a workspace.
- **R1.2** Where `--in` names a directory, the `ssc` CLI shall read every image in it, ordered by filename, as one frame set.
- **R1.3** When it converts a frame set, the `ssc` CLI shall write one file per input frame under `--out`, each keeping its input filename.
- **R1.4** If an output file already exists, then the `ssc` CLI shall write nothing and exit `1`.
- **R1.5** If a frame set would decode to more pixels than the set ceiling, then the `ssc` CLI shall decode none of it and exit `1`.

## R2 · `snap`

- **R2.1** When `ssc tool snap` runs, the `ssc` CLI shall recover each frame's pixel grid with the vendored snapper.
- **R2.2** The `ssc` CLI shall return every frame of a set on one grid, being the grid most of the set resolved to.
- **R2.3** Where `--pixel-size` is given, the `ssc` CLI shall use it for every frame instead of detecting a grid.
- **R2.4** Where `--grid` is given, the `ssc` CLI shall emit each frame at its recovered grid size; otherwise it shall emit each frame at the size that frame arrived at.
- **R2.5** Where `--colors` or `--palette` is given, the `ssc` CLI shall constrain the recovered image to it.
- **R2.6** If the snapper reports a failure, then the `ssc` CLI shall exit `1` and report the message the snapper gave.
- **R2.7** Where `snap` runs inside a workspace, the `ssc` CLI shall reuse a snapped result addressed by a key covering the frame's content, the grid it was given, and every parameter that changes the result.
- **R2.8** If the snapper returns no memory for a frame, then the `ssc` CLI shall write nothing into the module and exit `1`.
- **R2.9** If the snapper traps, then the `ssc` CLI shall report it as an error carrying a code and exit `1`.

## R3 · `pixelart`

- **R3.1** When `ssc tool pixelart` runs, the `ssc` CLI shall map every frame of a set onto one palette computed across the whole set.
- **R3.2** Where `--palette` is given, the `ssc` CLI shall use exactly those colours and compute none.
- **R3.3** The `ssc` CLI shall quantize only a frame's opaque pixels and shall leave its alpha unchanged.
- **R3.4** Where `--dither ordered` or `--dither floyd-steinberg` is given, the `ssc` CLI shall apply that dithering while mapping onto the palette.
- **R3.5** The `ssc` CLI shall apply no dithering unless it is asked for.
- **R3.6** Where `--min-cluster` is given, the `ssc` CLI shall replace every group of touching same-coloured pixels smaller than it with the palette colour that most surrounds that group.
- **R3.7** Where `--outline` is given, the `ssc` CLI shall draw a one-pixel outline in that colour around each frame's opaque silhouette.

## R4 · `board`

- **R4.1** When `ssc tool board checker` runs, the `ssc` CLI shall write a black-and-white checkerboard of squares of the given size.
- **R4.2** When `ssc tool board poses` runs, the `ssc` CLI shall write a board of `<cols>`×`<rows>` cells of the given cell size, with every cell boundary visible.
- **R4.3** When it writes a board, the `ssc` CLI shall report the layout it wrote — cell size, columns, rows, and the image size in pixels.

## Out of scope

- **Which board a model actually responds to.** The two sources disagree on whether the
  checkerboard alternates every pixel or every square, and which works is an empirical
  question per model. This leaf makes both producible; `tool sweep` is what answers it.
- **Reconciling a layout against a model's allowed sizes.** R4.3 reports the layout so that
  `specs/model-registry/` and `specs/gen-fal/` can reconcile it. Nothing here knows what a
  model accepts.
- **The project's palette.** `pixelart` takes its parameters in the call. The locked
  `palette.json` and cross-asset coherence are `specs/style-and-palette/`.
- **Writing into an asset.** These three take `--in` and `--out` and record nothing. The
  leaf that runs them against a workspace asset is a later one.
