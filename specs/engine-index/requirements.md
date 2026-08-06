---
autonomy: auto
ci: wait
---

# Engine index — requirements

## Purpose

`ssc index` builds `dist/` out of a workspace: the sheet, atlas or tileset an engine
actually loads for each kind, and one `index.json` describing all of it. `ssc preview`
renders what that index declares, so a person can see the numbers are right before an engine
believes them. Both are for the point at which the art is finished and has to reach Pixi,
Phaser or Godot.

## R1 · What gets indexed

- **R1.1** The `ssc` CLI shall index every asset recorded under `assets/`, whatever its kind.
- **R1.2** The `ssc` CLI shall group indexed assets by kind and take each kind's artefact from
  that kind's profile: a kind that animates gives one sheet per asset, a kind whose atlas
  layout is `bin` gives one atlas per kind, and a kind whose atlas layout is `grid` gives one
  tileset per kind.
- **R1.3** The `ssc` CLI shall publish an asset's last recorded image stage.
- **R1.4** Where `--stage` is given, the `ssc` CLI shall publish that stage instead.
- **R1.5** If an asset records no image at the published stage, then the `ssc` CLI shall skip
  it, report the reason, and index the rest.
- **R1.6** The `ssc` CLI shall write the image files the index names and `dist/index.json` in
  one run, so no entry names a file that run did not write.
- **R1.7** The `ssc` CLI shall write nothing outside `dist/` while building the index.
- **R1.8** When it runs a second time over an unchanged workspace, the `ssc` CLI shall write
  byte-identical files.
- **R1.9** Where `--dry-run` is given, the `ssc` CLI shall report every file it would write and
  shall write none of them.

## R2 · Sheets

- **R2.1** The `ssc` CLI shall carry on a sheet entry the cell size, the columns, the rows,
  the frame count and the anchor's position within the cell.
- **R2.2** If the frames of a sheet did not share one anchor, then the `ssc` CLI shall report
  that sheet's anchor as unaligned rather than omit it.
- **R2.3** The `ssc` CLI shall carry on a sheet entry a frame rate and a playback mode, the
  mode being one of `loop`, `ping-pong` and `reverse`.
- **R2.4** Where an asset declares named sections, the `ssc` CLI shall carry each section's
  name, its first frame and its last frame on that asset's sheet entry.
- **R2.5** If a section names a frame the sheet does not have, then the `ssc` CLI shall refuse,
  naming the section and the frame count.

## R3 · Atlases, tilesets and panels

- **R3.1** The `ssc` CLI shall carry on an atlas entry each member asset's id, rect and
  anchor, and the padding and the extrusion the atlas was packed with.
- **R3.2** The `ssc` CLI shall carry on a tileset entry the tile size, the columns, the rows,
  and each tile's id with its column and row.
- **R3.3** Where a kind's checks include `nineslice`, the `ssc` CLI shall carry the four
  stretch borders on each of that kind's entries.

## R4 · Where playback comes from

- **R4.1** The `ssc` CLI shall read an asset's frame rate, playback mode and named sections
  from `asset.yaml` beside that asset's `meta.json`.
- **R4.2** Where an asset declares no frame rate, the `ssc` CLI shall use the frame rate on
  its kind's profile.
- **R4.3** If `asset.yaml` is malformed, then the `ssc` CLI shall refuse, naming the file and
  the key at fault — malformed being a file that is not a map, a key that is not a playback
  key, or a playback mode that is not one of the three.
- **R4.4** The `ssc` CLI shall neither record `asset.yaml` in `meta.json` nor delete it, since
  it is authored rather than produced.

## R5 · Formats

- **R5.1** The `ssc` CLI shall emit its own `generic` shape, carrying everything R2 and R3
  require, when no format is named.
- **R5.2** Where `--format pixi` is given, the `ssc` CLI shall emit for each sheet and each
  atlas the spritesheet data PixiJS parses: `frames` keyed by frame name, `animations`, and
  `meta` naming the image and its size.
- **R5.3** Where `--format phaser` is given, the `ssc` CLI shall emit the JSON Hash texture
  atlas Phaser's texture manager adds.
- **R5.4** Where `--format godot` is given, the `ssc` CLI shall emit the region, the margin,
  the frame rate and the loop flag a Godot loader needs to build an `AtlasTexture` and a
  `SpriteFrames`.
- **R5.5** The `ssc` CLI shall describe the same image files and the same rects in every
  format, so changing format changes `index.json` and nothing else on disk.
- **R5.6** If `--format` names a format `ssc` does not emit, then the `ssc` CLI shall refuse,
  listing the formats it does.

## R6 · Preview

- **R6.1** The `ssc` CLI shall render an animated GIF at the frame rate and in the playback
  order the index declares for the asset it was given.
- **R6.2** Where `--contact` is given, the `ssc` CLI shall render a contact sheet instead,
  labelling each frame with its index.
- **R6.3** Where a kind declares the `seam` check, the `ssc` CLI shall render its assets
  tiled 2×2.
- **R6.4** Where `--section` is given, the `ssc` CLI shall render only that section's frames.
- **R6.5** If there is no `dist/index.json`, then the `ssc` CLI shall refuse to preview,
  naming `ssc index` as the fix.
- **R6.6** The `ssc` CLI shall write nothing outside `dist/preview/` while rendering a
  preview.
- **R6.7** (ADDED) The `ssc` CLI shall render a preview through the same renderer `ssc tool preview` uses, and shall grow no second renderer for the index path.

## R7 · Per-frame data

Delta from `plans/ssc-completion.md` group 3, which moved per-frame boxes and markers out
of this spec's "out of scope" and into it.

- **R7.1** (ADDED) The `ssc` CLI shall read hitboxes, hurtboxes and markers from the
  sidecar's `frames:` block, one entry per frame of the set.
- **R7.2** (ADDED) If a `frames:` block's length differs, then the `ssc` CLI shall refuse
  the sheet, naming the block's length and the set's frame count.
- **R7.3** (ADDED) The `ssc` CLI shall derive each frame's alpha bounding box from its
  pixels, with no authoring at all.
- **R7.4** (ADDED) The `ssc` CLI shall emit each sheet's per-frame bounds, hitboxes,
  hurtboxes and markers into `dist/index.json`, carrying authored values only and inventing
  none.
- **R7.5** (ADDED) If a non-animating kind's asset authors one, then the `ssc` CLI shall skip that asset, saying why.
- **R7.6** (ADDED) When `tool curate` drops frames of an asset, the `ssc` CLI shall keep
  exactly the kept frames' authored entries, in the kept order.
- **R7.7** (ADDED) If `tool curate` cannot line a block up, then the `ssc` CLI shall refuse
  before writing anything.

## Out of scope

- **`ssc tool preview`**, which renders a frame set with no workspace and no index — that is
  `specs/frame-preview/`, which owns the renderer this leaf renders through (R6.7) rather than
  growing a second one.
- **Engine-native resource files.** `ssc` emits JSON and PNG; a `.tres`, `.atlas` or `.plist`
  is the engine importer's job.
- **Running the pipeline.** `ssc index` reads what is on disk, produces no stage, and opens no
  gate.
