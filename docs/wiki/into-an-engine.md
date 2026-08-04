# Into an engine

Everything before this page is about making the art right. This one is about handing it over.
`ssc index` walks the workspace and writes `dist/`: the image files an engine loads, and one
`index.json` that says what is in them.

## Why the index is built rather than recorded

`ssc tool pack` writes a sheet wherever you point it, and nothing binds that file to the asset
it came from. That is right for a tool — it works on loose PNGs outside a workspace — and it
means an asset's own record ends at a frame set. So the sheet an engine loads has to be
produced by whatever builds the deliverable, and that is `ssc index`.

The consequence worth knowing: **`dist/` is output, in full.** Delete it and nothing is lost;
run `ssc index` twice over an unchanged workspace and the bytes are identical. Nothing under
`dist/` is recorded in any `meta.json`, because an index is not a stage of any one asset.

## What each kind becomes

Read off the kind's profile, never off its name:

| The profile says | The engine gets |
|---|---|
| `animates: true` | one **sheet** per asset — equal cells, addressed by frame number |
| `atlas_layout: bin` | one **atlas** per kind — a rect and an anchor per asset |
| `atlas_layout: grid` | one **tileset** per kind — equal cells, an id per tile |

A kind whose `checks` name `nineslice` carries the four stretch borders on every entry as
well, which is how `ui` panels survive being stretched.

The anchor travels in pixels, and the index says whether the frames of a sheet actually
*shared* one. An unaligned sheet still has an anchor — what it does not have is one every
frame agrees on, and an engine told nothing re-centres the sprite and brings back at runtime
exactly the drift [[frame-normalisation]] removed.

## Playback is authored, not measured

Nothing in an image says it plays at twelve frames per second. That, the playback mode and
the named sections live in the asset's sidecar:

```yaml
# assets/character/hero/asset.yaml
playback:
  fps: 12
  mode: ping-pong        # loop | ping-pong | reverse
  sections:
    windup: [0, 2]       # first and last frame, both inclusive
    hit: [3, 4]
```

Every key is optional. An asset that declares no frame rate plays at its kind's, which a
project sets per kind in `ssc.yaml` — a project's icons and its characters do not animate at
one speed.

Sections are checked against the frames that are really there. A section running to frame 8
of a six-frame set is refused by name, because no engine would complain: it would simply play
the wrong frames, and only somebody watching would notice.

## The four formats

`--format generic` is ssc's own shape and the only one `ssc preview` reads back. The other
three are the engine's own conventions, and they describe the same files and the same rects —
changing format changes `index.json` and nothing else on disk.

- **`pixi`** — the spritesheet data PixiJS's `Spritesheet` parses: `frames` by name,
  `animations`, `meta`. The anchor becomes a fraction of the cell here, because that is what
  Pixi's `anchor` is; handing it a pixel would put the origin sixteen cells to the right.
- **`phaser`** — the JSON Hash texture atlas Phaser's texture manager adds, with `pivot`
  where Pixi says `anchor`, and the animation under `anims` where a loader reads it.
- **`godot`** — the region, margin, speed and loop flag a twenty-line GDScript loader needs
  to build an `AtlasTexture` and a `SpriteFrames`. Not a `.tres`: a Godot resource file
  carries ids and a format version tied to the editor's, so ssc would own a file that breaks
  on somebody else's upgrade.

**An engine format bakes the playback mode into the frame order.** Pixi's `animations` is a
list of names and Godot's `SpriteFrames` has a loop flag and no mode, so neither can say
`ping-pong`. The frames come out in the order the mode implies, which is the only mapping
that plays right — and it is why a six-frame ping-pong animation appears with ten entries.

## Seeing it before an engine does

```bash
ssc preview character/hero              # an animated GIF, at the declared rate and order
ssc preview hero --contact              # every frame on one sheet, labelled by index
ssc preview hero --section windup       # just that range
ssc preview grass                       # a tile, 2x2, so its seams are visible
```

`ssc preview` renders from `dist/` rather than from `assets/`, on purpose: it exists to show
what an engine will load, so it reads the same file and believes the same numbers. A preview
built from the source art would still look right when the index was wrong.

A tile is previewed tiled because that is the only question a single tile raises — see
[[game-ready-defects]] on `seam`. Two by two is the smallest arrangement that puts every edge
against a copy of the opposite one.

## What the index does not carry

Per-frame hit boxes, hurt boxes and markers are `specs/frame-metadata/`'s, authored into the
same sidecar and emitted into the same index. `ssc` will carry those values; it will never
invent damage or knockback.
