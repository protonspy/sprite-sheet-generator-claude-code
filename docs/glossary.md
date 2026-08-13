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
- **sidecar** — `asset.yaml`, beside an asset's `meta.json`: the authored half of an asset,
  holding what nobody can measure. `meta.json` records what commands did; the sidecar records
  what a person decided. Never recorded in `meta.json`, and so never reachable by `ssc
  clean`. See `adr:0009-authored-intent-lives-in-a-sidecar`.
- **index** — `dist/index.json`, the one file describing everything an engine loads out of a
  workspace: every sheet with its cell, grid, frame rate and anchor, every atlas with a rect
  per entry, every tileset with its tile size and ids.

## Geometry

- **cell** — the fixed box every frame of a sheet occupies. Uniform across the sheet,
  which is what lets an engine address a frame by number instead of by rect.
- **frame** — one image of an animation, occupying one cell.
- **sheet** — a grid of equal cells holding the frames of one animation.
  Avoid: sprite sheet, spritesheet
- **frame set** — the frames of one animation taken as one unit: the thing `tool
  normalise` puts on a common baseline, centre column and scale alongside an asset's
  other sets. A sheet is the image that holds a frame set; the set is what the gates
  measure and the normaliser treats as one.
  Avoid: animation sequence
- **atlas** — a packed image of unrelated entries at differing sizes, each carrying its own
  rect and id. What a sheet is to an animation, an atlas is to a non-animated kind.
  Avoid: texture atlas, sprite atlas
- **anchor** — the registration point of a frame: the pixel an engine positions the sprite
  by. Locked by `tool align`, recorded by `tool pack`, and emitted into the index, without
  which the engine re-centres the sprite and the drift returns at runtime.
  Avoid: pivot
- **anchor image** — the one image a character's other directions and animations derive
  from. Say it in full wherever "anchor" alone could be read as the registration point.
- **gravity** — where a computed rectangle sits inside the canvas it was fitted to:
  `centre`, `top`, `bottom`, `left`, `right` or one of the four corners, and an axis the
  name does not mention is centred. `ssc tool crop --aspect` is positioned by one. `tool
  expand --place` is the same idea for a canvas being grown rather than cut, and keeps its
  own name because it places content, not a box.
- **tile** — one square of a tileset, drawn to repeat against copies of itself.
- **tileset** — one image holding every tile of a kind in equal cells, each addressed by id
  and found by column and row. A sheet holds the frames of one animation; a tileset holds
  the tiles of one kind.
- **nine-slice** — a panel cut into nine regions so its border survives being stretched to
  any size. `ssc tool ninepatch` is the command; `nineslice` is the `doctor` check.
  Avoid: 9-slice, nine patch

## On a frame

- **marker** — a name attached to one frame, for something the game does at that instant:
  a footstep, a spawn point, the opening of a cancel window. Authored in the sidecar,
  validated against the frame count, and carried into the index. `ssc` moves the name and
  never gives it meaning. Avoid: event, keyframe
- **hitbox** — a rectangle on a frame that deals. Authored in the sidecar, because nothing
  in the pixels says where it goes. `ssc` carries the box and never invents damage or
  knockback. Avoid: attack box, damage box
- **hurtbox** — a rectangle on a frame that receives. Separate from the hitbox because one
  frame usually has both and they are rarely the same rectangle.
  Avoid: collision box, hit area

## Measurements

- **visible height** — the height of a frame's alpha bounding box: the pixels the
  sprite actually occupies, never the canvas height. The number `tool bounds` reports
  per frame and `tool normalise` equalises across the sets of one asset.
  Avoid: sprite height, content height
- **baseline** — the canvas row a frame set's feet land on. It is the anchor's row
  once `tool align` has run, and the thing that must agree between two animations of
  one asset, or the feet drift through the floor mid-animation.
  Avoid: ground row, foot row, floor line
- **centre column** — the canvas column a frame set's sprite is horizontally centred
  on, the column `tool normalise` aligns across the sets of one asset so a sprite does
  not jump sideways between animations.
  Avoid: center column, mid column

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
- **scale** — the visible-height disagreement between the frame sets of one asset: the
  sprite that grows two pixels when it starts walking. `doctor` reports it as a number,
  `tool normalise` is its fix.
  Avoid: size drift, height mismatch
- **seam** — the visible discontinuity where a tile's opposite edges meet as it repeats.
- **dither** — approximating a colour a palette cannot hold by mixing colours it can.
  `ordered` offsets each pixel by its cell of a fixed matrix, so the same pixel is offset
  the same way in every frame and a still region cannot shimmer; `floyd-steinberg`
  diffuses each pixel's error into its neighbours, which reads better on one image and
  worse across a set.
- **board** — a reference image generated for the generation step to send to a model: a
  checkerboard, which imposes block discipline, or a pose board, which declares the frame
  layout. Generated by `ssc tool board` and never vendored, because a fixed PNG freezes a
  parameter that should track the project.

## Generating

- **style** — the look a paid generation is asked to produce: a name this package ships
  (`pixel-art`, `vector`, `hand-painted`, `3d-render`, `flat`) or free text handed to the
  model unchanged. A style is words plus, sometimes, an attachment — `pixel-art` sends the
  checkerboard board as well, because the words alone do not impose block discipline.
  **Scoped, and deliberately not unique:** `--style` on a `gen` command is this; `ssc tool
  style` is quantizing a frame set against `palette.json` and keeps its own meaning. Say
  which one is meant wherever the command does not make it obvious.
  Avoid: art style, aesthetic
- **reference image** — an image sent with a generation for the model to derive from,
  rather than the thing being generated. A board is one; so is the anchor image a
  direction is drawn from, and so is any file a caller names. More than one is ordinary:
  an anchor plus a checkerboard is how every direction after the first is made.
  Avoid: init image, image prompt, input image
- **box art** — the concept piece for a character, generated for a human to approve and
  for the pixel art to be derived from, and generated only when no reference image exists.
  Full fidelity and never pixel art, which is the point: it captures what the character is
  before anything commits to how it is drawn. A game may show it on a selection screen.
  Avoid: key art, cover art
- **paid step** — a step of a workspace's `pipeline:` whose command bills. What separates
  it from every other step is that it may not run unattended: a gate stands in front of it
  and `budget-guard` reserves against it before the call is made.
  Avoid: generation step, billed step

## Colour

- **palette** — the ordered set of colours every asset in a workspace quantizes against,
  held in `palette.json` and decided once for the project rather than passed per command.
  A palette that is an argument is why two assets generated a week apart drift apart.
  Avoid: colour set, swatch
- **preset** — a palette shipped with the package and chosen by name — `pico8`, `nes`,
  `gameboy`, `sweetie16` — instead of enumerated by hand in `palette.json`.
  Avoid: scheme, theme
- **recolour** — mapping one palette onto another, so a red slime and a blue slime are one
  asset and a colour map rather than two generations. Deterministic and free, which puts it
  on the same side of `budget-guard` as `mirror`. Avoid: palette swap, recolor

## Running the tool

- **job** — one provider call, recorded as a file under `jobs/` before it is considered
  made, carrying the `request_id` that lets a later process collect a result it never
  submitted. Every `gen` call produces one.
- **gate** — a decision reserved for a human, held as state in the workspace. A pending
  gate is exit code `3` and a `review/` directory, never a question asked in conversation.
- **sweep** — one command run once per point of a parameter range over the same input, with
  every result measured and put side by side for a person. Avoid: search, grid search
- **variant** — one result of a sweep: the output of one point, with its own `doctor`
  report and its own cell on the contact sheet. Avoid: candidate, sample
- **step** — one entry of a workspace's `pipeline:`, naming the stage it writes and the
  command that writes it. What `ssc run` executes and `ssc status` reports on. Avoid: task,
  phase
- **playback mode** — how a frame set repeats: `loop`, `ping-pong` or `reverse`. Declared in
  the sidecar, carried by the index, and baked into the frame order for the engine formats
  that cannot express it.
- **section** — a named range of frames inside one animation, both ends inclusive: an
  attack's windup, hit and recovery are three sections of one set rather than three sets.

## Where inference runs

- **device** — where a model-backed command executes: `auto`, `cpu`, `cuda`, `directml` or
  `coreml`. `auto` takes the best available; a device named explicitly fails loudly rather
  than falling back, because a silent drop to CPU reads as a hung command.
  Avoid: accelerator
- **execution provider** — `onnxruntime`'s name for the implementation that actually runs
  the graph, `CPUExecutionProvider` or `CUDAExecutionProvider` among them. Part of the
  cache key, since the same input through two of them can differ in the last bit. Say it in
  full: a provider on its own is the generation provider, which is a different thing.
