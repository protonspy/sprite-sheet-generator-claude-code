"""`ssc tool preview` — specs/frame-preview R1, R2, R3.

The frame-set renderer with no workspace and no index: a GIF at `--fps` in `--mode`, a sheet
cut by `--cell`/`--cols`/`--rows`, and `--contact` for a labelled sheet — all through the one
renderer `ssc preview` already uses.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main


def run(*args: str) -> tuple[int, dict[str, object]]:
    result = CliRunner().invoke(main, ["tool", "preview", "--json", *args], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def write_set(directory: Path, count: int, *, canvas: int = 8) -> Path:
    """Fill `directory` with `count` frames, each a different solid colour so the GIF keeps
    them distinct (Pillow merges identical adjacent frames and sums their durations)."""
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        image = np.zeros((canvas, canvas, 4), dtype=np.uint8)
        image[:, :] = (index * 30, 0, 0, 255)
        Image.fromarray(image, mode="RGBA").save(directory / f"{index:03d}.png")
    return directory


def write_sheet(path: Path, columns: int, rows: int, cell: int = 4) -> Path:
    """A sheet of `columns`x`rows` cells, each a solid colour keyed by frame index."""
    image = np.zeros((rows * cell, columns * cell, 4), dtype=np.uint8)
    for number in range(columns * rows):
        row, column = divmod(number, columns)
        image[row * cell : (row + 1) * cell, column * cell : (column + 1) * cell] = (
            number * 20,
            0,
            0,
            255,
        )
    Image.fromarray(image, mode="RGBA").save(path)
    return path


def gif_frames(path: Path) -> int:
    with Image.open(path) as opened:
        return int(getattr(opened, "n_frames", 1))


def test_a_frame_set_renders_as_a_gif(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=3)
    out = tmp_path / "walk.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--fps", "10")
    assert code == 0
    assert payload["frames"] == 3
    assert payload["fps"] == 10
    assert payload["mode"] == "loop"
    assert out.is_file()
    assert gif_frames(out) == 3


def test_a_single_image_is_a_one_frame_set(tmp_path: Path) -> None:
    src = tmp_path / "idle.png"
    write_set(tmp_path / "_unused", count=1)  # leave the helper; write one image directly
    Image.fromarray(np.zeros((8, 8, 4), dtype=np.uint8), mode="RGBA").save(src)
    out = tmp_path / "idle.gif"

    code, payload = run("--in", str(src), "--out", str(out))
    assert code == 0
    assert payload["frames"] == 1
    assert gif_frames(out) == 1


def test_ping_pong_plays_more_frames_than_the_set_holds(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=4)
    out = tmp_path / "walk.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--mode", "ping-pong")
    assert code == 0
    # Four frames ping-ponged is six.
    assert payload["ordered"] == 6
    assert gif_frames(out) == 6


def test_a_frame_rate_below_one_is_refused(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=2)
    out = tmp_path / "walk.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--fps", "0")
    assert code == 2
    assert payload["error"]["code"] == "invalid-fps"


def test_a_sheet_is_cut_by_its_grid_and_rendered(tmp_path: Path) -> None:
    src = write_sheet(tmp_path / "sheet.png", columns=3, rows=2)
    out = tmp_path / "sheet.gif"

    code, payload = run(
        "--in", str(src), "--out", str(out), "--cell", "4x4", "--cols", "3", "--rows", "2"
    )
    assert code == 0
    assert payload["frames"] == 6
    assert gif_frames(out) == 6


def test_a_sheet_with_a_partial_grid_is_refused(tmp_path: Path) -> None:
    src = write_sheet(tmp_path / "sheet.png", columns=2, rows=2)
    out = tmp_path / "sheet.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--cell", "4x4", "--cols", "2")
    assert code == 2
    assert payload["error"]["code"] == "incomplete-grid"


def test_a_grid_without_a_cell_is_refused(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=2)
    out = tmp_path / "walk.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--cols", "2", "--rows", "1")
    assert code == 2
    assert payload["error"]["code"] == "incomplete-grid"


def test_frames_without_a_cell_is_refused(tmp_path: Path) -> None:
    # `--frames` counts frames cut from a sheet, so without `--cell` it is a no-op a
    # caller would mistake for a limit on the set — refuse it like the other grid flags.
    src = write_set(tmp_path / "walk", count=4)
    out = tmp_path / "walk.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--frames", "2")
    assert code == 2
    assert payload["error"]["code"] == "incomplete-grid"


def test_a_grid_the_sheet_cannot_hold_is_refused(tmp_path: Path) -> None:
    src = write_sheet(tmp_path / "sheet.png", columns=2, rows=2)
    out = tmp_path / "sheet.gif"

    code, payload = run(
        "--in", str(src), "--out", str(out), "--cell", "8x8", "--cols", "2", "--rows", "2"
    )
    assert code == 2
    assert payload["error"]["code"] == "grid-mismatch"


def test_contact_renders_a_labelled_png(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=3)
    out = tmp_path / "walk.png"

    code, payload = run("--in", str(src), "--out", str(out), "--contact")
    assert code == 0
    assert payload["contact"] is True
    assert out.is_file()
    with Image.open(out) as opened:
        assert opened.format == "PNG"


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=2)
    out = tmp_path / "walk.gif"

    code, payload = run("--in", str(src), "--out", str(out), "--dry-run")
    assert code == 0
    assert payload["dry_run"] is True
    assert not out.exists()


def test_an_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    src = write_set(tmp_path / "walk", count=2)
    out = tmp_path / "walk.gif"
    out.write_bytes(b"already here")

    code, payload = run("--in", str(src), "--out", str(out))
    assert code == 1
    assert payload["error"]["code"] == "file-exists"
    assert out.read_bytes() == b"already here"
