"""`ssc tool tile`, `doctor --check seam`, and the tileset — specs/tile-assets R1.5, R2.4, R3."""

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


def textured(width: int, height: int, seed: int = 3, block: int = 4) -> np.ndarray:
    generator = np.random.default_rng(seed)
    low = generator.integers(0, 256, size=(-(-height // block), -(-width // block), 3))
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = np.repeat(np.repeat(low, block, axis=0), block, axis=1)[:height, :width]
    image[:, :, 3] = 255
    return image


def save(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGBA").save(path)
    return path


@pytest.fixture
def tiles(tmp_path: Path) -> Path:
    directory = tmp_path / "tiles"
    save(directory / "grass.png", textured(16, 16, seed=1))
    save(directory / "stone.png", textured(16, 16, seed=2))
    return directory


# R1.1, R1.5 — one new file per input, and the loop the plan describes actually closes.


def test_a_set_is_closed_tile_by_tile(tiles: Path, tmp_path: Path) -> None:
    code, payload = run("tool", "tile", "--in", str(tiles), "--out", str(tmp_path / "out"))

    assert code == 0
    assert payload["tiles"] == 2
    assert len(payload["written"]) == 2
    assert payload["mode"] == "edge"
    for name in ("grass.png", "stone.png"):
        assert (tmp_path / "out" / name).exists()


def test_the_closed_tile_measures_clean_where_the_original_did_not(
    tiles: Path, tmp_path: Path
) -> None:
    """`tool tile` fixes, `doctor --check seam` says whether it worked. That loop is the
    whole point of the leaf, so it is asserted end to end rather than in halves."""
    before = run("tool", "doctor", "--check", "seam", "--in", str(tiles / "grass.png"))[1]
    run("tool", "tile", "--in", str(tiles / "grass.png"), "--out", str(tmp_path / "closed.png"))
    after = run("tool", "doctor", "--check", "seam", "--in", str(tmp_path / "closed.png"))[1]

    seam_before = next(f for f in before["checks"] if f["check"] == "seam")
    seam_after = next(f for f in after["checks"] if f["check"] == "seam")
    assert seam_before["status"] == "defect"
    assert seam_before["fix"] == "ssc tool tile"
    assert seam_after["status"] == "ok"


def test_a_tile_one_pixel_wide_is_refused_by_name(tmp_path: Path) -> None:
    save(tmp_path / "thin.png", textured(1, 8))

    code, payload = run(
        "tool", "tile", "--in", str(tmp_path / "thin.png"), "--out", str(tmp_path / "o.png")
    )

    assert code == 2
    assert payload["error"]["code"] == "not-tileable"
    assert "thin.png" in payload["error"]["message"]


def test_mirror_is_reported_as_the_mode_that_ran(tiles: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "tile", "--mode", "mirror", "--in", str(tiles), "--out", str(tmp_path / "out")
    )

    assert code == 0
    assert payload["mode"] == "mirror"


def test_a_tile_that_already_wraps_reports_nothing_moved(tmp_path: Path) -> None:
    """Re-running must be visibly a no-op, not quietly one — an operator asking "did that do
    anything" gets a number rather than a shrug."""
    flat = np.zeros((8, 8, 4), dtype=np.uint8)
    flat[:, :, :3] = 90
    flat[:, :, 3] = 255
    save(tmp_path / "flat.png", flat)

    _, payload = run(
        "tool", "tile", "--in", str(tmp_path / "flat.png"), "--out", str(tmp_path / "o.png")
    )

    assert payload["pixels_changed"] == 0


# R2.4 — asked for, or declared by the kind. Skipped everywhere else.


def test_seam_is_skipped_unless_it_is_asked_for(tiles: Path) -> None:
    _, payload = run("tool", "doctor", "--in", str(tiles / "grass.png"))

    seam = next(finding for finding in payload["checks"] if finding["check"] == "seam")
    assert seam["status"] == "skipped"
    assert "tile" in seam["reason"]


def test_a_kind_whose_profile_declares_seam_runs_it(
    tiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The harness's route: it names the asset's kind rather than knowing which checks that
    kind wants, which is what keeps the decision in `ssc.yaml`."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    _, payload = run("tool", "doctor", "--kind", "tile", "--in", str(tiles / "grass.png"))

    seam = next(finding for finding in payload["checks"] if finding["check"] == "seam")
    assert seam["status"] == "defect"


def test_a_kind_that_does_not_declare_seam_leaves_it_skipped(
    tiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    _, payload = run("tool", "doctor", "--kind", "character", "--in", str(tiles / "grass.png"))

    seam = next(finding for finding in payload["checks"] if finding["check"] == "seam")
    assert seam["status"] == "skipped"


# R3.1, R3.2 — the tileset index.


def test_packing_a_grid_kind_reports_the_tile_size_and_one_id_per_tile(
    tiles: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run(
        "tool", "pack", "--kind", "tile", "--in", str(tiles), "--out", str(tmp_path / "set.png")
    )

    assert code == 0
    assert payload["layout"] == "grid"
    assert payload["tile"] == {"width": 16, "height": 16}
    assert [entry["id"] for entry in payload["tiles"]] == ["grass", "stone"]
    assert payload["tiles"][1]["column"] == 1
    assert payload["tiles"][1]["row"] == 0


def test_tiles_of_more_than_one_size_are_refused_with_the_sizes_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pack` pads a short frame to the cell, which is right for an animation and wrong for a
    tileset: every id would resolve to a cell with the art somewhere else inside it."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    mixed = tmp_path / "mixed"
    save(mixed / "grass.png", textured(16, 16))
    save(mixed / "wall.png", textured(16, 24))

    code, payload = run(
        "tool", "pack", "--kind", "tile", "--in", str(mixed), "--out", str(tmp_path / "set.png")
    )

    assert code == 2
    assert payload["error"]["code"] == "tiles-differ"
    assert "16x16" in payload["error"]["message"]
    assert "16x24" in payload["error"]["message"]


def test_packing_without_a_kind_reports_no_tileset(tiles: Path, tmp_path: Path) -> None:
    """The sheet is unchanged for everyone who did not ask to be a tileset."""
    _, payload = run("tool", "pack", "--in", str(tiles), "--out", str(tmp_path / "s.png"))

    assert "tiles" not in payload
    assert "tile" not in payload
