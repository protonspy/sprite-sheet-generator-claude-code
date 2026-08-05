"""`ssc tool recolour` — the free variant path (task 5.3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner

from ssc.cli.app import main
from ssc.cli.frames import encode


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def swatch(colour: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[:, :] = (*colour, 255)
    return image


@pytest.fixture
def frames(tmp_path: Path) -> Path:
    directory = tmp_path / "frames"
    directory.mkdir()
    (directory / "001.png").write_bytes(encode(swatch((255, 0, 0))))
    (directory / "002.png").write_bytes(encode(swatch((0, 200, 0))))
    return directory


def test_recolour_maps_red_to_blue(frames: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "recolour",
        "--in",
        str(frames),
        "--out",
        str(tmp_path / "out"),
        "--from",
        "ff0000,00c800",
        "--to",
        "0000ff,c8c800",
    )
    assert code == 0, payload

    from PIL import Image

    def top(path: Path) -> tuple[int, int, int]:
        return tuple(np.asarray(Image.open(path).convert("RGB"))[0, 0])  # type: ignore[return-value]

    assert top(tmp_path / "out" / "001.png") == (0, 0, 255)
    assert top(tmp_path / "out" / "002.png") == (200, 200, 0)


def test_mismatched_palette_lengths_are_refused(frames: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "recolour",
        "--in",
        str(frames),
        "--out",
        str(tmp_path / "out"),
        "--from",
        "ff0000,00c800",
        "--to",
        "0000ff",
    )
    assert code != 0
    assert payload["error"]["code"] == "palette-length"


def test_an_empty_palette_is_refused(frames: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "recolour",
        "--in",
        str(frames),
        "--out",
        str(tmp_path / "out"),
        "--from",
        "",
        "--to",
        "0000ff",
    )
    assert code != 0
    assert payload["error"]["code"] == "empty-palette"


def test_a_dry_run_writes_nothing(frames: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "recolour",
        "--in",
        str(frames),
        "--out",
        str(tmp_path / "out"),
        "--from",
        "ff0000",
        "--to",
        "0000ff",
        "--dry-run",
    )
    assert code == 0, payload
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("*"))
