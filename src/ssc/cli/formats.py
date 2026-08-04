"""One model, four ways of saying it.

Nothing here reads a workspace, opens a file or touches a pixel: an emitter takes the `Built`
model from `cli/index.py` and renames its fields. That is what makes R5.5 checkable — the
images and the rects are decided once, upstream, and a format cannot disagree with them
because it never computes one.

**An engine format bakes the playback mode into the frame order; `generic` states it.** Pixi's
`animations` is a list of frame names and Godot's `SpriteFrames` carries a loop flag and no
mode, so neither can express `ping-pong` or `reverse` as a mode. Emitting the frames in the
order the mode implies is the only mapping that plays correctly, and `core.preview.order` is
the one place that order is worked out — the same call `ssc preview` renders through.
"""

from __future__ import annotations

from typing import Any

from ssc.cli.errors import UsageError
from ssc.cli.index import Built, SheetEntry, TilesetEntry
from ssc.core.atlas import Rect
from ssc.core.preview import order

#: What `--format` accepts. `generic` is first because it is the default and the only one
#: that carries everything R2 and R3 require.
FORMATS = ("generic", "pixi", "phaser", "godot")
DEFAULT_FORMAT = "generic"

#: The version of the shape, not of `ssc`. A consumer that reads this can tell a field it
#: does not know from a field that was removed.
SCHEMA = 1


def emit(built: Built, *, name: str = DEFAULT_FORMAT) -> dict[str, Any]:
    """The whole index, in the named format (R5.1, R5.6)."""
    emitters = {
        "generic": generic,
        "pixi": pixi,
        "phaser": phaser,
        "godot": godot,
    }
    chosen = emitters.get(name)
    if chosen is None:
        raise UsageError(
            "unknown-format",
            f"{name!r} is not a format ssc emits",
            fix=f"one of: {', '.join(FORMATS)}",
        )
    return {"schema": SCHEMA, "format": name, **chosen(built)}


def generic(built: Built) -> dict[str, Any]:
    """ssc's own shape: every artefact, with the numbers as they were measured (R5.1)."""
    return {
        "sheets": [sheet.as_dict() for sheet in built.sheets],
        "atlases": [atlas.as_dict() for atlas in built.atlases],
        "tilesets": [tileset.as_dict() for tileset in built.tilesets],
        "skipped": [one.as_dict() for one in built.skipped],
    }


def frame_names(sheet: SheetEntry) -> list[str]:
    """`hero_0000.png` … — the name a frame is addressed by in an atlas-shaped format.

    The `.png` is not a file: TexturePacker's exports name frames after the source images
    they were cut from, and both Pixi and Phaser are read by people who have seen that shape.
    """
    return [f"{sheet.key}_{number:04d}.png" for number in range(sheet.frames)]


def cell_rect(sheet: SheetEntry, number: int) -> dict[str, int]:
    """Where frame `number` sits on its sheet, in pixels.

    Derived from the grid rather than stored per frame: equal cells are the whole reason a
    sheet is a sheet, and storing N rects for a grid is N places for one to be wrong.
    """
    row, column = divmod(number, sheet.columns)
    return {
        "x": column * sheet.cell[0],
        "y": row * sheet.cell[1],
        "w": sheet.cell[0],
        "h": sheet.cell[1],
    }


def as_frame(rect: Rect) -> dict[str, int]:
    """A rect in the `x y w h` spelling both Pixi and Phaser read.

    `Rect.as_dict` says `width` and `height`, which is the right name for a number ssc
    reports and the wrong one for a field TexturePacker's format defines. Converted here
    rather than renamed there: `generic` is not going to start speaking TexturePacker.
    """
    return {"x": rect.x, "y": rect.y, "w": rect.width, "h": rect.height}


def fraction(anchor: tuple[int, int], size: tuple[int, int]) -> dict[str, float]:
    """An anchor as a fraction of its cell, which is how Pixi and Phaser take one.

    Kept in pixels everywhere else: a fraction cannot be turned back into the pixel it came
    from, so the conversion happens once, at the boundary that asked for it.
    """
    return {"x": anchor[0] / size[0], "y": anchor[1] / size[1]}


def pixi(built: Built) -> dict[str, Any]:
    """The spritesheet data PixiJS's `Spritesheet` parses (R5.2).

    `frames` maps a name to a rect, `animations` maps a name to an ordered list of those
    names, and `meta` says which image and how big. `anchor` is a `PointData` in the 0..1
    space, and `borders` is Pixi's own nine-slice field — which is why a `ui` atlas needs no
    second mechanism to carry one.
    """
    sheets: dict[str, Any] = {}
    for sheet in built.sheets:
        names = frame_names(sheet)
        sheets[sheet.id] = {
            "frames": {
                name: {
                    "frame": cell_rect(sheet, number),
                    "sourceSize": {"w": sheet.cell[0], "h": sheet.cell[1]},
                    "spriteSourceSize": {
                        "x": 0,
                        "y": 0,
                        "w": sheet.cell[0],
                        "h": sheet.cell[1],
                    },
                    "anchor": fraction(sheet.anchor, sheet.cell),
                }
                for number, name in enumerate(names)
            },
            # One animation per sheet, named after the asset, in the order its mode implies.
            "animations": {
                sheet.key: [names[number] for number in order(sheet.frames, sheet.mode)]
            },
            "meta": {
                "image": sheet.image,
                "size": {"w": sheet.columns * sheet.cell[0], "h": sheet.rows * sheet.cell[1]},
                "scale": "1",
                # Not Pixi's, and deliberately kept: the frame rate has nowhere else to go in
                # this shape, and an `AnimatedSprite` needs one. `meta` is documented as
                # open, so a reader that ignores it loses nothing.
                "fps": sheet.fps,
            },
        }

    atlases = {
        atlas.id: {
            "frames": {
                item.id: {
                    "frame": as_frame(item.rect),
                    "sourceSize": {"w": item.rect.width, "h": item.rect.height},
                    "spriteSourceSize": {
                        "x": 0,
                        "y": 0,
                        "w": item.rect.width,
                        "h": item.rect.height,
                    },
                    "anchor": fraction(item.anchor, (item.rect.width, item.rect.height)),
                    **(
                        {}
                        if item.borders is None
                        else {
                            "borders": {
                                "left": item.borders[0],
                                "right": item.borders[1],
                                "top": item.borders[2],
                                "bottom": item.borders[3],
                            }
                        }
                    ),
                }
                for item in atlas.items
            },
            "meta": {
                "image": atlas.image,
                "size": {"w": atlas.width, "h": atlas.height},
                "scale": "1",
            },
        }
        for atlas in built.atlases
    }
    for tileset in built.tilesets:
        atlases[tileset.id] = _tileset_as_frames(tileset)

    return {"spritesheets": sheets | atlases, "skipped": [one.as_dict() for one in built.skipped]}


def _tileset_as_frames(tileset: TilesetEntry) -> dict[str, Any]:
    """A tileset in the same rect-per-name shape, since a tile is a rect like any other."""
    return {
        "frames": {
            tile.id: {
                "frame": {
                    "x": tile.column * tileset.tile[0],
                    "y": tile.row * tileset.tile[1],
                    "w": tileset.tile[0],
                    "h": tileset.tile[1],
                },
                "sourceSize": {"w": tileset.tile[0], "h": tileset.tile[1]},
                "spriteSourceSize": {"x": 0, "y": 0, "w": tileset.tile[0], "h": tileset.tile[1]},
            }
            for tile in tileset.tiles
        },
        "meta": {
            "image": tileset.image,
            "size": {
                "w": tileset.columns * tileset.tile[0],
                "h": tileset.rows * tileset.tile[1],
            },
            "scale": "1",
        },
    }


def phaser(built: Built) -> dict[str, Any]:
    """The JSON Hash atlas Phaser's texture manager adds (R5.3).

    The same rects as `pixi` — Phaser's JSON Hash and TexturePacker's are one format — with
    `pivot` where Pixi says `anchor`, and no `animations`: a Phaser animation is created from
    a frame list in code, so the order goes under `anims` where a loader can read it without
    pretending to be part of the atlas.
    """
    textures: dict[str, Any] = {}
    anims: dict[str, Any] = {}

    for sheet in built.sheets:
        names = frame_names(sheet)
        textures[sheet.id] = {
            "frames": {
                name: {
                    "frame": cell_rect(sheet, number),
                    "trimmed": False,
                    "rotated": False,
                    "sourceSize": {"w": sheet.cell[0], "h": sheet.cell[1]},
                    "spriteSourceSize": {"x": 0, "y": 0, "w": sheet.cell[0], "h": sheet.cell[1]},
                    "pivot": fraction(sheet.anchor, sheet.cell),
                }
                for number, name in enumerate(names)
            },
            "meta": {
                "image": sheet.image,
                "size": {"w": sheet.columns * sheet.cell[0], "h": sheet.rows * sheet.cell[1]},
                "scale": "1",
            },
        }
        anims[sheet.id] = {
            "key": sheet.key,
            "frameRate": sheet.fps,
            "repeat": -1,
            "frames": [names[number] for number in order(sheet.frames, sheet.mode)],
        }

    for atlas in built.atlases:
        textures[atlas.id] = {
            "frames": {
                item.id: {
                    "frame": as_frame(item.rect),
                    "trimmed": False,
                    "rotated": False,
                    "sourceSize": {"w": item.rect.width, "h": item.rect.height},
                    "spriteSourceSize": {
                        "x": 0,
                        "y": 0,
                        "w": item.rect.width,
                        "h": item.rect.height,
                    },
                    "pivot": fraction(item.anchor, (item.rect.width, item.rect.height)),
                }
                for item in atlas.items
            },
            "meta": {
                "image": atlas.image,
                "size": {"w": atlas.width, "h": atlas.height},
                "scale": "1",
            },
        }

    for tileset in built.tilesets:
        textures[tileset.id] = _tileset_as_frames(tileset)

    return {
        "textures": textures,
        "anims": anims,
        "skipped": [one.as_dict() for one in built.skipped],
    }


def godot(built: Built) -> dict[str, Any]:
    """What a Godot loader needs to build an `AtlasTexture` and a `SpriteFrames` (R5.4).

    JSON rather than a `.tres`: a Godot resource file carries resource ids and a format
    version tied to the editor's, so ssc would own a file that breaks on somebody else's
    upgrade. The fields here are named after the API a twenty-line GDScript loader calls —
    `region` and `margin` on `AtlasTexture`, `speed` and `loop` on `SpriteFrames`.

    `loop` is a flag and there is no mode, so `ping-pong` and `reverse` are in the frame
    order and every animation loops. That is the only mapping that plays right, and it is
    stated here rather than left for somebody to infer from a suspiciously long frame list.
    """
    animations = [
        {
            "id": sheet.id,
            "image": sheet.image,
            "name": sheet.key,
            "speed": float(sheet.fps),
            "loop": True,
            "frames": [
                {
                    "region": cell_rect(sheet, number),
                    "margin": {"x": 0, "y": 0, "w": 0, "h": 0},
                }
                for number in order(sheet.frames, sheet.mode)
            ],
            "sections": [section.as_dict() for section in sheet.sections],
        }
        for sheet in built.sheets
    ]

    regions = [
        {
            "id": atlas.id,
            "image": atlas.image,
            "textures": [
                {
                    "name": item.id,
                    "region": {
                        "x": item.rect.x,
                        "y": item.rect.y,
                        "w": item.rect.width,
                        "h": item.rect.height,
                    },
                    "margin": {"x": 0, "y": 0, "w": 0, "h": 0},
                }
                for item in atlas.items
            ],
        }
        for atlas in built.atlases
    ]

    tilesets = [
        {
            "id": tileset.id,
            "image": tileset.image,
            "tile_size": {"w": tileset.tile[0], "h": tileset.tile[1]},
            "tiles": [tile.as_dict() for tile in tileset.tiles],
        }
        for tileset in built.tilesets
    ]

    return {
        "sprite_frames": animations,
        "atlas_textures": regions,
        "tile_sets": tilesets,
        "skipped": [one.as_dict() for one in built.skipped],
    }


def images_of(emitted: dict[str, Any]) -> set[str]:
    """Every image path a format's output names, wherever it put it (R5.5).

    Written for the test that holds the four formats to one set of files, and kept in the
    module rather than in the test because it is the definition of the promise: a format may
    move the field, and it may not name a different image.
    """
    found: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "image" and isinstance(value, str):
                    found.add(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(emitted)
    return found


__all__ = ["DEFAULT_FORMAT", "FORMATS", "SCHEMA", "emit", "images_of"]
