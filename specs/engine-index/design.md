# Engine index — design

## What changes

Serves R1.1, R1.2, R1.5, R4.1, R5.1, R6.1.

- **`cli/sidecar.py`** — `asset.yaml`: the authored half of an asset. Playback now; per-frame
  boxes and markers when `specs/frame-metadata/` lands. Read through the held directory and
  validated on read, the same shape `meta.py` and `jobs.py` already use.
- **`cli/index.py`** — the model. Walks the workspace into per-kind groups, resolves each
  asset's published stage, and builds a `Sheet`, an `Atlas` or a `Tileset` from the kind's
  profile. This is where the packing happens; the formats below only rename its fields.
- **`cli/formats.py`** — four emitters over that one model: `generic`, `pixi`, `phaser`,
  `godot`. Nothing here reads the workspace or an image.
- **`core/preview.py`** — pure: the frame order a playback mode implies, and the 2×2 tiling.
  Both are arithmetic on arrays and neither needs a file.
- **`cli/preview.py`** — the GIF encoder, next to `frames.encode` rather than in `core/`,
  because `core/` takes and returns arrays and a GIF is bytes.
- **`cli/commands/index.py`** — `ssc index` and `ssc preview`.
- **`cli/workspace.py`** — one new path, `dist`, alongside `assets`, `cache` and `jobs`.
- **`cli/kinds.py`** — one new profile field, `fps`, as a delta on `specs/asset-kinds/`.

## Boundaries and contracts

**`ssc index` packs; it does not look for something already packed.** `tool pack` takes
`--in`/`--out` and writes a sheet wherever the caller pointed it — nothing binds that file
to an asset, and no command records an `output`-class file into a `meta.json` today. So an
asset's terminal artefact is a recorded frame set, and the sheet an engine loads has to be
produced by whatever builds `dist/`. That makes `ssc index` a build step over `core.assemble`
and `core.atlas`, which is what `core/` is for: `tool pack` and `ssc index` are two callers
of one packer, not two packers.

**`dist/` is output, and only `ssc index` and `ssc preview` write there.** It is derived from
`assets/` in full, so deleting it loses nothing — which is the property that lets R1.7 be a
requirement rather than an aspiration. Nothing in `dist/` is recorded in a `meta.json`: an
index is not a stage of any one asset.

**Authored intent lives in the sidecar; `meta.json` stays provenance.** A frame rate is a
decision a person made, not a record of what a command did, and `meta.json` documents itself
as "what each file is and where it came from". Mixing the two would put a hand-edited value
in the file `ssc clean` reads to decide what to delete. Recorded as
`adr:0009-authored-intent-lives-in-a-sidecar` — it is hard to reverse because people will
have written these files by hand.

**An engine format bakes the playback mode into the frame order; `generic` states it.**
Pixi's `animations` is a list of frame names and Godot's `SpriteFrames` has a loop flag and
no mode, so neither can express `ping-pong` or `reverse` as a mode. Emitting the frames in
the order the mode implies is the only mapping that plays correctly, and it is why
`core.preview.order` is shared between the emitters and `ssc preview` rather than each
working it out.

## Data

`assets/<kind>/<key>/asset.yaml`, every key optional:

```yaml
playback:
  fps: 12
  mode: ping-pong          # loop | ping-pong | reverse
  sections:
    windup: [0, 2]         # first and last frame, inclusive
    hit: [3, 4]
```

`dist/index.json`, in `generic`, is a flat list per artefact shape so that ordering is a
sort and nothing nests by kind:

```json
{
  "schema": 1,
  "format": "generic",
  "sheets": [{
    "kind": "character", "key": "hero-run",
    "image": "sheets/character/hero-run.png",
    "cell": {"width": 64, "height": 64},
    "columns": 4, "rows": 2, "frames": 8,
    "anchor": {"x": 32, "y": 63}, "aligned": true,
    "playback": {"fps": 12, "mode": "loop",
                 "sections": [{"name": "windup", "first": 0, "last": 2}]}
  }],
  "atlases": [{
    "kind": "icon", "image": "atlases/icon.png",
    "width": 128, "height": 64, "padding": 2, "extrude": 1,
    "entries": [{"id": "potion", "rect": {"x": 0, "y": 0, "width": 32, "height": 32},
                 "anchor": {"x": 16, "y": 31}}]
  }],
  "tilesets": [{
    "kind": "tile", "image": "tilesets/tile.png",
    "tile": {"width": 32, "height": 32}, "columns": 4, "rows": 2,
    "tiles": [{"id": "grass", "column": 0, "row": 0}]
  }],
  "skipped": [{"kind": "banner", "key": "title", "why": "records no image"}]
}
```

The three engine formats carry the same artefacts under `spritesheets`, `textures` and
`sprite_frames` respectively, each keyed by `<kind>/<key>` for a sheet and `<kind>` for an
atlas or a tileset. A frame of a sheet is named `<key>_0000.png`, which is the name its
`animations` entry uses. Pixi's `anchor` and Phaser's `pivot` are fractions of the cell,
which is why the anchor is stored in pixels once and divided at the boundary.

`dist/` on disk:

```
dist/index.json
dist/sheets/<kind>/<key>.png
dist/atlases/<kind>.png
dist/tilesets/<kind>.png
dist/preview/<kind>/<key>.gif        · .png for a contact sheet or a 2×2
```

## Alternatives considered

**Record the packed sheet into `meta.json` and have `index` read it.** It would make `ssc
index` a pure reader, which is the shape this project prefers. Rejected because it needs a
new `output` file class in every asset and a command to produce one, which is a second
feature; and because a sheet recorded once goes stale the moment a later stage lands, where
a sheet built by the index cannot.

**Playback in `ssc.yaml`.** One file, already read, already validated. Rejected because the
frame rate differs per animation and `ssc.yaml` would grow a per-asset map keyed by strings
nothing checks against the assets that exist — the failure being a typo'd key that silently
does nothing.

**Emit `.tres` for Godot.** It is what Godot opens directly. Rejected: a `.tres` carries
resource ids and a format version tied to the editor's, so ssc would own a file that breaks
on someone else's Godot upgrade. JSON plus a twenty-line loader script is stable, and R5.4
is written against what that loader needs.

## Risks

**A format that is subtly wrong looks right.** A frame rate off by a factor, a fraction where
an engine wanted pixels, or a `y` measured from the wrong edge all load without complaint and
animate wrongly. The tests assert the numbers against a hand-worked example per format rather
than against the emitter's own output.

**The preview renderer has a second owner coming.** `specs/frame-preview/` in
`plans/sprite-normalisation-gate.md` owns `ssc tool preview` and expects `ssc preview` to
render *through* it. Keeping the composition in `core/preview.py` and the encoding in
`cli/preview.py` is what makes that a re-wiring rather than a rewrite.
