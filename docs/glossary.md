# Glossary

One canonical term per concept, and the synonyms to avoid. These are the words the
twenty-seven specs inherit: use them in requirements, in wiki pages, in JSON fields and in
identifiers. Anything obvious to anyone who has shipped a 2D game is deliberately not
here.

## The workspace

- **key** — the identifier of one asset inside its kind, and the directory that holds it:
  `assets/<kind>/<key>/`. Unique within a kind, not globally.
- **kind** — an extensible profile declaring an asset's cell, anchor mode, whether it
  animates, its atlas layout, which `doctor` checks apply to it and which generation
  template it uses. Built-ins ship with the package; a project adds its own in `ssc.yaml`.
  Never a closed enum.
- **stage** — the named step that produced a file (`snap`, `nobg`, `cut`), recorded in
  `meta.json`. A stage is how a file is addressed; the numeric prefix on the filename
  orders the chain for a human reading `ls` and is never an address.
- **source** — a file a model produced. Not reproducible, always versioned, and `ssc
  clean` refuses to touch it.
- **derived** — a file a deterministic command computed from a source with recorded
  parameters. Reproducible by re-running that command, which is what makes it the only
  class `ssc clean` may delete.
- **output** — the deliverable a pipeline ends at and an engine reads: a packed sheet, an
  atlas, `dist/index.json`.
- **lineage** — the files one file was derived from, transitively, back to the source the
  chain started at. `meta.json` records a single step per file in `derived_from`; walking
  that back is what answers "where did this come from".
- **medium** — which of the two modalities a file is, image or video, decided by its
  extension. Everything `ssc` writes is one or the other, which is why `image` and `video`
  are the two nouns a caller observes a workspace through.

## Geometry

- **cell** — the fixed box every frame of a sheet occupies. Uniform across the sheet,
  which is what lets an engine address a frame by number instead of by rect.
- **frame** — one image of an animation, occupying one cell.
- **sheet** — a grid of equal cells holding the frames of one animation.
  Avoid: sprite sheet, spritesheet
- **atlas** — a packed image of unrelated entries at differing sizes, each carrying its own
  rect and id. What a sheet is to an animation, an atlas is to a non-animated kind.
  Avoid: texture atlas, sprite atlas
- **anchor** — the registration point of a frame: the pixel an engine positions the sprite
  by. Locked by `tool align`, recorded by `tool pack`, and emitted into the index, without
  which the engine re-centres the sprite and the drift returns at runtime.
  Avoid: pivot
- **anchor image** — the one image a character's other directions and animations derive
  from. Say it in full wherever "anchor" alone could be read as the registration point.
- **tile** — one square of a tileset, drawn to repeat against copies of itself.
- **nine-slice** — a panel cut into nine regions so its border survives being stretched to
  any size. `ssc tool ninepatch` is the command; `nineslice` is the `doctor` check.
  Avoid: 9-slice, nine patch

## Defects and repairs

- **snap** — recovering the real pixel grid from art that only looks like pixel art:
  detect the implicit grid, collapse the blurred sub-pixel runs onto it, scale back up
  with nearest neighbour. Not a resize, and not `pixelart`.
- **pixelart** — converting art of any origin into true pixel art: palette quantization,
  dithering, outline emphasis, orphan-cluster cleanup. One word when it names the command;
  the art form itself is two.
- **flicker** — a region that did not move changing colour between adjacent frames,
  because each frame was quantized on its own. Fixed structurally, by quantizing a whole
  frame set against one palette.
- **seam** — the visible discontinuity where a tile's opposite edges meet as it repeats.

## Running the tool

- **job** — one provider call, recorded as a file under `jobs/` before it is considered
  made, carrying the `request_id` that lets a later process collect a result it never
  submitted. Every `gen` call produces one.
- **gate** — a decision reserved for a human, held as state in the workspace. A pending
  gate is exit code `3` and a `review/` directory, never a question asked in conversation.
