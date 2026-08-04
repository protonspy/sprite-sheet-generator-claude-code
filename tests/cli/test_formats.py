"""One model, four ways of saying it — specs/engine-index R5.

The Pixi tests were written first and watched fail. It is the format where the mapping from
the model is a translation rather than a rename — an anchor becomes a fraction, an animation
becomes an ordered list of frame *names*, and a rect changes spelling — so its numbers are
worked out by hand here, and the other three are checked against the same hand-worked sheet.
"""

from __future__ import annotations

from typing import Any

import pytest

from ssc.cli import formats
from ssc.cli.errors import UsageError
from ssc.cli.index import AtlasEntry, AtlasItem, Built, SheetEntry, TileItem, TilesetEntry
from ssc.cli.sidecar import Section
from ssc.core.atlas import Rect

#: Six frames of 32x32 in a 3x2 grid, anchored at the middle of the bottom row of pixels.
#: Every number below is derived from these by hand, on purpose.
SHEET = SheetEntry(
    kind="character",
    key="hero",
    image="sheets/character/hero.png",
    cell=(32, 32),
    columns=3,
    rows=2,
    frames=6,
    anchor=(16, 31),
    aligned=True,
    fps=12,
    mode="ping-pong",
    sections=(Section("windup", 0, 2),),
)

PANEL = AtlasEntry(
    kind="ui",
    image="atlases/ui.png",
    width=64,
    height=32,
    padding=2,
    extrude=1,
    items=(AtlasItem(id="panel", rect=Rect(2, 2, 24, 24), anchor=(12, 23), borders=(4, 4, 4, 4)),),
)

TILES = TilesetEntry(
    kind="tile",
    image="tilesets/tile.png",
    tile=(16, 16),
    columns=2,
    rows=1,
    tiles=(TileItem("grass", 0, 0), TileItem("stone", 1, 0)),
)

BUILT = Built(sheets=[SHEET], atlases=[PANEL], tilesets=[TILES])


def emitted(name: str) -> dict[str, Any]:
    return formats.emit(BUILT, name=name)


# R5.1, R5.6 — the default, and the refusal.


def test_generic_is_the_default_and_carries_every_artefact() -> None:
    payload = formats.emit(BUILT)
    assert payload["format"] == "generic"
    assert payload["schema"] == formats.SCHEMA
    assert payload["sheets"][0]["cell"] == {"width": 32, "height": 32}
    assert payload["atlases"][0]["entries"][0]["rect"]["width"] == 24
    assert payload["tilesets"][0]["tiles"] == [
        {"id": "grass", "column": 0, "row": 0},
        {"id": "stone", "column": 1, "row": 0},
    ]


def test_a_format_ssc_does_not_emit_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        formats.emit(BUILT, name="unity")
    assert refused.value.code == "unknown-format"
    assert "generic" in (refused.value.fix or "")


# R5.2 — Pixi. Hand-worked: frame 4 of a 3-wide grid of 32px cells is column 1, row 1.


def test_pixi_places_each_frame_by_arithmetic_on_the_grid() -> None:
    frames = emitted("pixi")["spritesheets"]["character/hero"]["frames"]
    assert frames["hero_0000.png"]["frame"] == {"x": 0, "y": 0, "w": 32, "h": 32}
    assert frames["hero_0002.png"]["frame"] == {"x": 64, "y": 0, "w": 32, "h": 32}
    assert frames["hero_0004.png"]["frame"] == {"x": 32, "y": 32, "w": 32, "h": 32}


def test_pixi_gives_the_anchor_as_a_fraction_of_the_cell() -> None:
    # 16/32 and 31/32 — Pixi's anchor is `PointData` in the 0..1 space, and handing it 16
    # would put the origin sixteen cells to the right.
    frames = emitted("pixi")["spritesheets"]["character/hero"]["frames"]
    assert frames["hero_0000.png"]["anchor"] == {"x": 0.5, "y": 31 / 32}


def test_pixi_bakes_the_playback_mode_into_the_animation() -> None:
    # `ping-pong` over six frames is ten, and the names are what Pixi looks up.
    animation = emitted("pixi")["spritesheets"]["character/hero"]["animations"]["hero"]
    assert animation == [
        "hero_0000.png",
        "hero_0001.png",
        "hero_0002.png",
        "hero_0003.png",
        "hero_0004.png",
        "hero_0005.png",
        "hero_0004.png",
        "hero_0003.png",
        "hero_0002.png",
        "hero_0001.png",
    ]


def test_pixi_meta_names_the_image_and_its_measured_size() -> None:
    meta = emitted("pixi")["spritesheets"]["character/hero"]["meta"]
    assert meta["image"] == "sheets/character/hero.png"
    assert meta["size"] == {"w": 96, "h": 64}
    assert meta["scale"] == "1"
    assert meta["fps"] == 12


def test_pixi_carries_nine_slice_borders_in_its_own_field() -> None:
    panel = emitted("pixi")["spritesheets"]["ui"]["frames"]["panel"]
    assert panel["borders"] == {"left": 4, "right": 4, "top": 4, "bottom": 4}
    assert panel["frame"] == {"x": 2, "y": 2, "w": 24, "h": 24}


def test_pixi_leaves_borders_off_a_kind_that_has_none() -> None:
    assert "borders" not in emitted("pixi")["spritesheets"]["tile"]["frames"]["grass"]


# R5.3 — Phaser: the same rects, its own spelling.


def test_phaser_is_a_json_hash_with_the_same_rects() -> None:
    texture = emitted("phaser")["textures"]["character/hero"]
    assert texture["frames"]["hero_0004.png"]["frame"] == {"x": 32, "y": 32, "w": 32, "h": 32}
    assert texture["frames"]["hero_0000.png"]["pivot"] == {"x": 0.5, "y": 31 / 32}
    assert texture["meta"]["size"] == {"w": 96, "h": 64}


def test_phaser_puts_the_animation_where_a_loader_reads_it() -> None:
    anims = emitted("phaser")["anims"]["character/hero"]
    assert anims["frameRate"] == 12
    assert anims["repeat"] == -1
    assert (
        anims["frames"] == emitted("pixi")["spritesheets"]["character/hero"]["animations"]["hero"]
    )


# R5.4 — Godot: region, margin, speed and a loop flag.


def test_godot_gives_a_region_per_frame_in_playback_order() -> None:
    animation = emitted("godot")["sprite_frames"][0]
    assert animation["speed"] == 12.0
    assert animation["loop"] is True
    assert len(animation["frames"]) == 10, "ping-pong is baked into the order"
    assert animation["frames"][0]["region"] == {"x": 0, "y": 0, "w": 32, "h": 32}
    assert animation["frames"][0]["margin"] == {"x": 0, "y": 0, "w": 0, "h": 0}
    assert animation["sections"] == [{"name": "windup", "first": 0, "last": 2}]


def test_godot_gives_an_atlas_texture_per_entry() -> None:
    textures = emitted("godot")["atlas_textures"][0]["textures"]
    assert textures[0]["name"] == "panel"
    assert textures[0]["region"] == {"x": 2, "y": 2, "w": 24, "h": 24}


def test_godot_carries_the_tileset_by_tile_size_and_id() -> None:
    tiles = emitted("godot")["tile_sets"][0]
    assert tiles["tile_size"] == {"w": 16, "h": 16}
    assert [tile["id"] for tile in tiles["tiles"]] == ["grass", "stone"]


# R5.5 — the four describe one set of files and one set of rects.


def test_every_format_names_the_same_images() -> None:
    expected = {"sheets/character/hero.png", "atlases/ui.png", "tilesets/tile.png"}
    for name in formats.FORMATS:
        assert formats.images_of(emitted(name)) == expected, name


def test_every_format_places_the_panel_at_the_same_rect() -> None:
    # Named differently in each, which is exactly why this is worth asserting: the model
    # measured it once, and a format that recomputed it could disagree.
    assert emitted("generic")["atlases"][0]["entries"][0]["rect"] == {
        "x": 2,
        "y": 2,
        "width": 24,
        "height": 24,
    }
    assert emitted("pixi")["spritesheets"]["ui"]["frames"]["panel"]["frame"] == {
        "x": 2,
        "y": 2,
        "w": 24,
        "h": 24,
    }
    assert emitted("phaser")["textures"]["ui"]["frames"]["panel"]["frame"] == {
        "x": 2,
        "y": 2,
        "w": 24,
        "h": 24,
    }
    assert emitted("godot")["atlas_textures"][0]["textures"][0]["region"] == {
        "x": 2,
        "y": 2,
        "w": 24,
        "h": 24,
    }


def test_every_format_reports_what_was_skipped() -> None:
    from ssc.cli.index import Skipped

    built = Built(skipped=[Skipped("banner", "title", "records no image")])
    for name in formats.FORMATS:
        assert formats.emit(built, name=name)["skipped"] == [
            {"kind": "banner", "key": "title", "why": "records no image"}
        ]
