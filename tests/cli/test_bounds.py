"""`ssc tool bounds` — plan `sprite-normalisation-gate` 3.1.

Per frame, the alpha bounding box, the visible height and width, the baseline row and the
centre column, as structured output. No image, no workspace.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main


def run(*args: str) -> tuple[int, dict[str, object]]:
    result = CliRunner().invoke(main, ["tool", "bounds", "--json", *args], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def write_sprite(path: Path, canvas: tuple[int, int], sprite: tuple[int, int, int, int]) -> None:
    """Save an RGBA PNG with one opaque rectangle on a transparent canvas.

    `sprite` is `(y, x, height, width)`.
    """
    image = np.zeros((canvas[0], canvas[1], 4), dtype=np.uint8)
    y, x, height, width = sprite
    image[y : y + height, x : x + width] = (0, 0, 0, 255)
    Image.fromarray(image, mode="RGBA").save(path)


def test_one_image_reports_one_frame(tmp_path: Path) -> None:
    src = tmp_path / "idle.png"
    write_sprite(src, (10, 10), (2, 3, 4, 5))

    code, payload = run("--in", str(src))
    assert code == 0
    frames = payload["frames"]
    assert len(frames) == 1
    assert frames[0]["name"] == "idle.png"
    assert frames[0]["bounds"] == {
        "x": 3,
        "y": 2,
        "width": 5,
        "height": 4,
        "baseline": 5,
        "centre": 5.0,
    }


def test_a_directory_is_read_as_an_ordered_frame_set(tmp_path: Path) -> None:
    src = tmp_path / "walk"
    src.mkdir()
    # Same sprite in each frame; the order is the filename order, which is the animation.
    for name in ("000.png", "001.png", "002.png"):
        write_sprite(src / name, (10, 10), (1, 1, 6, 4))

    code, payload = run("--in", str(src))
    assert code == 0
    assert [frame["name"] for frame in payload["frames"]] == ["000.png", "001.png", "002.png"]
    for frame in payload["frames"]:
        assert frame["bounds"]["width"] == 4
        assert frame["bounds"]["height"] == 6


def test_a_set_reports_each_measurement_as_a_median_with_a_spread(tmp_path: Path) -> None:
    """3.2 — per set, structured output: the representative value and the within-set
    jitter, no image and no workspace."""
    src = tmp_path / "walk"
    src.mkdir()
    # Visible heights 4, 6, 5 — median 5, spread 2 — same width and baseline throughout.
    write_sprite(src / "000.png", (10, 10), (3, 1, 4, 4))
    write_sprite(src / "001.png", (10, 10), (1, 1, 6, 4))
    write_sprite(src / "002.png", (10, 10), (2, 1, 5, 4))

    code, payload = run("--in", str(src))
    assert code == 0
    summary = payload["set"]
    assert summary["height"] == {"median": 5.0, "spread": 2.0}
    assert summary["width"] == {"median": 4.0, "spread": 0.0}
    # The baseline is the lowest occupied row: 6, 6, 6 — steady, so no within-set drift.
    assert summary["baseline"] == {"median": 6.0, "spread": 0.0}


def test_a_frame_with_no_coverage_reports_null_bounds(tmp_path: Path) -> None:
    src = tmp_path / "blank.png"
    Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA").save(src)

    code, payload = run("--in", str(src))
    assert code == 0
    assert payload["frames"][0]["bounds"] is None


def test_a_path_that_is_neither_file_nor_directory_is_an_error(tmp_path: Path) -> None:
    code, payload = run("--in", str(tmp_path / "nothing.png"))
    assert code == 1
    assert payload["error"]["code"] == "no-input"


def test_a_directory_with_no_images_says_so(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("no art here")
    code, payload = run("--in", str(tmp_path))
    assert code == 1
    assert payload["error"]["code"] == "no-images"


def test_bounds_writes_nothing(tmp_path: Path) -> None:
    """Like `doctor`, the one `tool` command with no `--out`."""
    src = tmp_path / "idle.png"
    write_sprite(src, (10, 10), (2, 3, 4, 5))
    before = src.read_bytes()
    run("--in", str(src))
    assert src.read_bytes() == before
    assert [path.name for path in tmp_path.iterdir()] == ["idle.png"]
