"""`recipe.yaml` — the inherited recipe a derived asset carries (plans/ssc-completion 6.1).

Authored intent stays in `asset.yaml`; the recipe is derived, so it has its own file and
its own closed vocabulary. These cover the data, the parse refusals, and the file I/O —
the command surface is in `test_asset_derivation.py`.
"""

from __future__ import annotations

import pytest

from ssc.cli import recipe
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError

WHERE = "assets/character/hero/recipe.yaml"
ANCHOR = recipe.AnchorRef(asset="character/hero", stage="style")


def recipe_text(**overrides: object) -> str:
    base = {
        "extends": "character/hero",
        "anchor": {"asset": "character/hero", "stage": "style"},
        "kind": "character",
        "pixel_size": 4,
        "palette": "pico8",
        "cell": {"width": 64, "height": 64},
        "frames": 8,
        "fps": 12,
    }
    base.update(overrides)
    lines = []
    for key, value in base.items():
        if value is None:
            lines.append(f"{key}:")
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"  {k}: {v}" for k, v in value.items())
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def parse(text: str) -> recipe.Recipe:
    return recipe.parse(text.encode("utf-8"), WHERE)


def refusal(text: str) -> SscError:
    with pytest.raises(SscError) as raised:
        parse(text)
    assert raised.value.code == "invalid-recipe"
    assert WHERE in raised.value.message
    return raised.value


# the data


def test_as_document_is_in_reading_order() -> None:
    doc = recipe.Recipe(
        extends="character/hero",
        anchor=ANCHOR,
        kind="character",
        pixel_size=4,
        palette="pico8",
        cell=(64, 64),
        frames=8,
        fps=12,
    ).as_document()
    assert list(doc) == [
        "extends",
        "anchor",
        "kind",
        "pixel_size",
        "palette",
        "cell",
        "frames",
        "fps",
    ]
    assert doc["anchor"] == {"asset": "character/hero", "stage": "style"}
    assert doc["cell"] == {"width": 64, "height": 64}


def test_reanchored_keeps_values_and_rewrites_extends() -> None:
    parent = recipe.Recipe(
        extends="character/root",
        anchor=recipe.AnchorRef(asset="character/root", stage="gen"),
        kind="character",
        pixel_size=4,
        palette="pico8",
        cell=(64, 64),
        frames=8,
        fps=12,
    )
    child = parent.reanchored("character/hero")
    assert child.extends == "character/hero"
    # the anchor stays pointed at the root's anchor image, not rewritten to the
    # immediate parent — a grandchild generates from the same anchor as its parent.
    assert child.anchor == parent.anchor
    assert (child.kind, child.pixel_size, child.palette, child.cell, child.frames, child.fps) == (
        parent.kind,
        parent.pixel_size,
        parent.palette,
        parent.cell,
        parent.frames,
        parent.fps,
    )


# parse — what a well-formed recipe says


def test_a_full_recipe_is_read() -> None:
    read = parse(recipe_text())
    assert read.extends == "character/hero"
    assert read.anchor == ANCHOR
    assert read.kind == "character"
    assert read.pixel_size == 4
    assert read.palette == "pico8"
    assert read.cell == (64, 64)
    assert read.frames == 8
    assert read.fps == 12


def test_a_cell_as_a_pair_is_read() -> None:
    read = parse(recipe_text(cell=[32, 32]))
    assert read.cell == (32, 32)


def test_a_null_palette_is_read() -> None:
    read = parse(recipe_text(palette=None))
    assert read.palette is None


# parse — refusals


def test_a_non_map_is_refused() -> None:
    refusal("extends: character/hero\n")


def test_an_unknown_key_is_refused() -> None:
    refusal(recipe_text(unknown=1))


def test_a_missing_field_is_refused() -> None:
    with pytest.raises(SscError) as raised:
        parse("extends: character/hero\nkind: character\n")
    assert "missing" in raised.value.message


def test_an_empty_extends_is_refused() -> None:
    refusal(recipe_text(extends=""))


def test_a_bool_pixel_size_is_refused() -> None:
    refusal(recipe_text(pixel_size=True))


def test_an_out_of_range_fps_is_refused() -> None:
    refusal(recipe_text(fps=0))


def test_a_cell_with_extra_keys_is_refused() -> None:
    refusal(recipe_text(cell={"width": 64, "height": 64, "depth": 1}))


def test_a_non_string_palette_is_refused() -> None:
    refusal(recipe_text(palette=4))


# parse — the anchor image reference


def test_an_anchor_that_is_not_a_map_is_refused() -> None:
    refusal(recipe_text(anchor="character/hero@style"))


def test_an_anchor_with_extra_keys_is_refused() -> None:
    refusal(recipe_text(anchor={"asset": "character/hero", "stage": "style", "frame": 1}))


def test_an_anchor_with_an_empty_asset_is_refused() -> None:
    refusal(recipe_text(anchor={"asset": "", "stage": "style"}))


def test_an_anchor_with_an_empty_stage_is_refused() -> None:
    refusal(recipe_text(anchor={"asset": "character/hero", "stage": ""}))


def test_a_missing_anchor_is_refused() -> None:
    with pytest.raises(SscError) as raised:
        parse(
            "extends: character/hero\nkind: character\npixel_size: 4\n"
            "cell: [64, 64]\nframes: 8\nfps: 12\n"
        )
    assert "anchor" in raised.value.message


# file I/O


def test_write_and_load_roundtrip(tmp_path: object) -> None:
    asset_dir = tmp_path
    original = recipe.Recipe(
        extends="character/hero",
        anchor=ANCHOR,
        kind="character",
        pixel_size=4,
        palette="pico8",
        cell=(64, 64),
        frames=8,
        fps=12,
    )
    with Directory.open(asset_dir) as held:
        recipe.write(held, original)
        loaded = recipe.load(held)
    assert loaded == original


def test_load_returns_none_where_there_is_no_recipe(tmp_path: object) -> None:
    asset_dir = tmp_path
    with Directory.open(asset_dir) as held:
        assert recipe.load(held) is None


def test_write_refuses_an_existing_recipe(tmp_path: object) -> None:
    asset_dir = tmp_path
    one = recipe.Recipe(
        extends="character/hero",
        anchor=ANCHOR,
        kind="character",
        pixel_size=4,
        palette=None,
        cell=(64, 64),
        frames=1,
        fps=12,
    )
    with Directory.open(asset_dir) as held:
        recipe.write(held, one)
        with pytest.raises(SscError) as raised:
            recipe.write(held, one)
        assert raised.value.code == "file-exists"
