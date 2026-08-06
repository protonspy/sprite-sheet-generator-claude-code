---
autonomy: auto
ci: wait
---

# Frame preview — requirements

## Purpose

`ssc tool preview` renders a frame set as an animated GIF so a person can see the animation
before an engine reads it — the same thing `ssc preview` does, but without a workspace and
without `dist/index.json`. It exists for the leg of the relay where the frames are on disk and
the index is not: right after `tool normalise` puts the sets of one asset on one scale, and
before `ssc index` has anything to point at. `ssc preview` resolves an asset out of the index
and renders through this command's renderer rather than a second one (engine-index R6).

## R1 · Input

- **R1.1** The `ssc` CLI shall accept `--in` naming one image or a directory of frames, and shall run it without a workspace.
- **R1.2** Where `--in` names a sheet and `--cell`, `--cols` and `--rows` are given, the `ssc` CLI shall cut that sheet into frames by its grid.
- **R1.3** If `--cell` is given without both `--cols` and `--rows`, or `--cols` and `--rows` without `--cell`, then the `ssc` CLI shall refuse, naming the flag that is missing.
- **R1.4** If a sheet does not divide into the given grid of cells, then the `ssc` CLI shall refuse before rendering, naming the image size and the grid.

## R2 · Playback

- **R2.1** The `ssc` CLI shall render the frames as an animated GIF at the frame rate given by `--fps`.
- **R2.2** The `ssc` CLI shall play the frames in the order given by `--mode`, the mode being one of `loop`, `ping-pong` and `reverse`.
- **R2.3** If `--fps` is less than one, then the `ssc` CLI shall refuse.
- **R2.4** If there are no frames to render, then the `ssc` CLI shall refuse.

## R3 · Output

- **R3.1** The `ssc` CLI shall write the GIF to `--out`.
- **R3.2** The `ssc` CLI shall render through `core.preview` and the project's single GIF encoder, and shall grow no second renderer.
- **R3.3** Where `--contact` is given, the `ssc` CLI shall render a contact sheet instead, labelling each frame with its index, and shall write it to `--out`.

## Out of scope

- **Resolving an asset from `dist/index.json`.** That is `ssc preview` in `specs/engine-index/`, which names this renderer, not a parallel one.
- **Kind-driven tiling.** Rendering a tile tiled 2×2 is `ssc preview`'s, read off a kind's profile; `tool preview` takes frames, not a kind.
- **Named sections.** A section is an index concept; `tool preview` plays the frames it is given.