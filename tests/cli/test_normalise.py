"""`ssc tool normalise` — plan `sprite-normalisation-gate` 4.2.

The sets of one asset on one baseline, one centre column, one canvas and one scale —
padding delegated to `plan_alignment`'s canvas growth, layout to `pack`.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main


def run(*args: str) -> tuple[int, dict[str, object]]:
    result = CliRunner().invoke(
        main, ["tool", "normalise", "--json", *args], catch_exceptions=False
    )
    return result.exit_code, json.loads(result.stdout)


def write_set(directory: Path, sprite: tuple[int, int, int, int], count: int) -> None:
    """Fill `directory` with `count` frames holding one opaque rectangle on an 8x8 canvas."""
    directory.mkdir(parents=True, exist_ok=True)
    y, x, height, width = sprite
    for index in range(count):
        image = np.zeros((8, 8, 4), dtype=np.uint8)
        image[y : y + height, x : x + width] = (0, 0, 0, 255)
        Image.fromarray(image, mode="RGBA").save(directory / f"{index:03d}.png")


def test_two_sets_land_on_one_canvas_and_one_anchor(tmp_path: Path) -> None:
    idle = tmp_path / "idle"
    walk = tmp_path / "walk"
    out = tmp_path / "normalised"
    write_set(idle, (2, 2, 4, 3), count=2)  # visible height 4
    write_set(walk, (1, 1, 6, 3), count=2)  # visible height 6 — the two-pixel defect

    code, payload = run("--in", str(idle), "--in", str(walk), "--out", str(out))
    assert code == 0
    assert payload["target"] == 5  # median(4, 6)
    assert payload["factors"] == [pytest.approx(5 / 4), pytest.approx(5 / 6)]
    # One anchor shared across both sheets — the baseline and centre the engine pins to.
    assert "anchor" in payload
    sheets = payload["sheets"]
    assert [sheet["name"] for sheet in sheets] == ["idle", "walk"]
    # Both sheets written, both readable, both the same shape (one cell, one layout).
    idle_sheet = np.array(Image.open(out / "idle.png").convert("RGBA"))
    walk_sheet = np.array(Image.open(out / "walk.png").convert("RGBA"))
    assert idle_sheet.shape == walk_sheet.shape


def test_a_single_set_is_aligned_and_packed(tmp_path: Path) -> None:
    """One set is the degenerate case: nothing cross-set to normalise, but the set still
    leaves on one baseline and one canvas, packed as a sheet."""
    src = tmp_path / "idle"
    out = tmp_path / "normalised"
    write_set(src, (2, 2, 4, 3), count=3)

    code, payload = run("--in", str(src), "--out", str(out))
    assert code == 0
    assert len(payload["sheets"]) == 1
    assert (out / "idle.png").is_file()


def test_a_blank_set_is_refused(tmp_path: Path) -> None:
    idle = tmp_path / "idle"
    blank = tmp_path / "blank"
    out = tmp_path / "normalised"
    write_set(idle, (2, 2, 4, 3), count=2)
    blank.mkdir()
    for index in range(2):
        Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA").save(
            blank / f"{index:03d}.png"
        )

    code, payload = run("--in", str(idle), "--in", str(blank), "--out", str(out))
    assert code == 2
    assert payload["error"]["code"] == "cannot-normalise"


def test_negative_columns_are_refused(tmp_path: Path) -> None:
    src = tmp_path / "idle"
    out = tmp_path / "normalised"
    write_set(src, (2, 2, 4, 3), count=2)

    code, payload = run("--in", str(src), "--out", str(out), "--cols=-1")
    assert code == 2
    assert payload["error"]["code"] == "invalid-cols"
