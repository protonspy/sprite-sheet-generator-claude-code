"""`ssc tool normal` — specs/normal-maps R1.3, R1.5, R2.1, R2.2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def save(path: Path, width: int = 8, height: int = 8) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((height, width, 4), dtype=np.uint8)
    for column in range(width):
        image[:, column, :3] = int(column * 255 / max(width - 1, 1))
    image[:, :, 3] = 255
    Image.fromarray(image, mode="RGBA").save(path)
    return path


@pytest.fixture
def frames(tmp_path: Path) -> Path:
    directory = tmp_path / "frames"
    save(directory / "001.png")
    save(directory / "002.png")
    return directory


def test_a_set_gets_one_map_per_frame(frames: Path, tmp_path: Path) -> None:
    code, payload = run("tool", "normal", "--in", str(frames), "--out", str(tmp_path / "n"))

    assert code == 0
    assert payload["maps"] == 2
    assert (tmp_path / "n" / "001.png").exists()
    assert (tmp_path / "n" / "002.png").exists()


def test_the_map_is_the_size_of_the_art(frames: Path, tmp_path: Path) -> None:
    run("tool", "normal", "--in", str(frames / "001.png"), "--out", str(tmp_path / "n.png"))

    assert Image.open(tmp_path / "n.png").size == (8, 8)


def test_the_convention_travels_with_the_result(frames: Path, tmp_path: Path) -> None:
    """An engine assuming the other one lights every surface backwards, and the map looks
    correct either way — so the answer cannot live in the memory of whoever ran the command."""
    _, up = run("tool", "normal", "--in", str(frames), "--out", str(tmp_path / "up"))
    _, down = run("tool", "normal", "--flip-y", "--in", str(frames), "--out", str(tmp_path / "dn"))

    assert up["convention"] == "+y-up"
    assert down["convention"] == "+y-down"


def test_the_strength_is_reported_back(frames: Path, tmp_path: Path) -> None:
    _, payload = run(
        "tool", "normal", "--strength", "2.5", "--in", str(frames), "--out", str(tmp_path / "n")
    )

    assert payload["strength"] == 2.5


@pytest.mark.parametrize("strength", ["0", "-1", "999"])
def test_a_strength_outside_the_range_is_refused(
    strength: str, frames: Path, tmp_path: Path
) -> None:
    code, payload = run(
        "tool", "normal", "--strength", strength, "--in", str(frames), "--out", str(tmp_path / "n")
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-strength"
    assert "--strength" in payload["error"]["fix"]
    assert not (tmp_path / "n").exists()


def test_a_dry_run_writes_nothing(frames: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "normal", "--dry-run", "--in", str(frames), "--out", str(tmp_path / "n")
    )

    assert code == 0
    assert payload["dry_run"] is True
    assert not (tmp_path / "n" / "001.png").exists()


def test_the_art_is_not_touched(frames: Path, tmp_path: Path) -> None:
    before = (frames / "001.png").read_bytes()

    run("tool", "normal", "--in", str(frames), "--out", str(tmp_path / "n"))

    assert (frames / "001.png").read_bytes() == before
