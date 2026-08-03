"""`ssc tool cut|slice|curate` — specs/frame-recovery R1.3, R3, R4.1, R4.3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli import meta
from ssc.cli.app import main


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def new_asset(kind: str, key: str) -> None:
    CliRunner().invoke(main, ["asset", "new", key, "--kind", kind], catch_exceptions=False)


def save(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGBA").save(path)
    return path


def sheet(tmp_path: Path, columns: int = 3, rows: int = 2, cell: int = 10) -> Path:
    """A sheet with an inset block in every cell, so the layout is readable."""
    image = np.zeros((rows * cell, columns * cell, 4), dtype=np.uint8)
    for row in range(rows):
        for column in range(columns):
            y, x = row * cell, column * cell
            image[y + 1 : y + cell - 1, x + 1 : x + cell - 1] = (200, 30, 30, 255)
    return save(tmp_path / "sheet.png", image)


# R1.2, R1.3 — detect, or refuse and name the flag.


def test_cut_detects_the_layout_when_nobody_states_it(tmp_path: Path) -> None:
    code, payload = run("tool", "cut", "--in", str(sheet(tmp_path)), "--out", str(tmp_path / "out"))
    assert code == 0
    assert payload["mode"] == "detected"
    assert payload["frames"] == 6
    assert len(list((tmp_path / "out").iterdir())) == 6


def test_a_stated_grid_wins_over_a_detected_one(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "cut", "--grid", "2x1", "--in", str(sheet(tmp_path)), "--out", str(tmp_path / "o")
    )
    assert code == 0
    assert payload["mode"] == "grid"
    assert payload["frames"] == 2


def test_a_sheet_with_no_layout_is_refused_naming_the_flag(tmp_path: Path) -> None:
    """The failure to avoid is a plausible wrong grid, so this refuses instead."""
    solid = np.zeros((16, 16, 4), dtype=np.uint8)
    solid[..., 3] = 255
    written = save(tmp_path / "solid.png", solid)
    code, payload = run("tool", "cut", "--in", str(written), "--out", str(tmp_path / "o"))
    assert code == 1
    assert payload["error"]["code"] == "no-grid"
    assert "--grid" in payload["error"]["fix"]


def test_a_grid_that_does_not_fit_is_a_usage_error(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "cut", "--grid", "99x99", "--in", str(sheet(tmp_path)), "--out", str(tmp_path / "o")
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-grid"


# R3.6 — exactly one destination.


@pytest.mark.parametrize("extra", [(), ("--asset", "character/hero", "--out", "x")])
def test_neither_destination_or_both_is_refused(tmp_path: Path, extra: tuple[str, ...]) -> None:
    code, payload = run("tool", "cut", "--in", str(sheet(tmp_path)), *extra)
    assert code == 2
    assert payload["error"]["code"] == "no-destination"


# R3.1, R3.3 — into an asset, recorded.


def test_cut_into_an_asset_records_one_stage_for_the_frame_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")

    code, payload = run("tool", "cut", "--in", str(sheet(tmp_path)), "--asset", "character/hero")
    assert code == 0
    assert payload["frames"] == 6

    record = meta.load(tmp_path / "assets/character/hero")
    assert [entry.stage for entry in record.files] == ["frames"]
    assert record.files[0].file_class == "derived"
    assert record.files[0].produced_by.command == "tool cut"
    assert len(list((tmp_path / "assets/character/hero/frames").iterdir())) == 6


def test_cut_into_an_asset_that_is_not_there_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    code, payload = run("tool", "cut", "--in", str(sheet(tmp_path)), "--asset", "character/ghost")
    assert code == 2
    assert payload["error"]["code"] == "no-asset"


def test_cutting_twice_into_one_asset_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")
    run("tool", "cut", "--in", str(sheet(tmp_path)), "--asset", "character/hero")

    code, payload = run("tool", "cut", "--in", str(sheet(tmp_path)), "--asset", "character/hero")
    assert code == 1
    assert payload["error"]["code"] == "file-exists"


# R3.2 — one asset per piece.


def test_slice_writes_one_asset_per_piece(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run(
        "tool", "slice", "--kind", "icon", "--key", "coin", "--in", str(sheet(tmp_path, 2, 1))
    )
    assert code == 0
    assert payload["assets"] == 2
    assert payload["written"] == ["icon/coin-01", "icon/coin-02"]

    record = meta.load(tmp_path / "assets/icon/coin-01")
    assert record.key == "coin-01"
    assert [entry.stage for entry in record.files] == ["cut"]


def test_slice_refuses_a_key_that_already_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("icon", "coin-01")

    code, payload = run(
        "tool", "slice", "--kind", "icon", "--key", "coin", "--in", str(sheet(tmp_path, 2, 1))
    )
    assert code == 2
    assert payload["error"]["code"] == "asset-exists"


def test_slice_takes_asset_as_a_usage_error_because_it_writes_many(tmp_path: Path) -> None:
    code, payload = run("tool", "slice", "--asset", "icon/coin", "--in", str(sheet(tmp_path, 2, 1)))
    assert code == 2
    assert payload["error"]["code"] == "invalid-destination"


# R3.4 — plain files, nothing recorded.


def test_slice_outside_a_workspace_writes_plain_files(tmp_path: Path) -> None:
    code, _ = run(
        "tool",
        "slice",
        "--key",
        "coin",
        "--in",
        str(sheet(tmp_path, 2, 1)),
        "--out",
        str(tmp_path / "out"),
    )
    assert code == 0
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "coin-01.png",
        "coin-02.png",
    ]
    assert not (tmp_path / "assets").exists()


# R4.1, R4.3 — curate reports, and drops when asked.


def frames_dir(tmp_path: Path) -> Path:
    source = tmp_path / "frames"
    for index, fill in enumerate((10, 10, 200, 200)):
        image = np.zeros((8, 8, 4), dtype=np.uint8)
        image[..., :3] = fill
        image[..., 3] = 255
        save(source / f"{index:03d}.png", image)
    return source


def test_curate_reports_the_redundant_frames_without_writing(tmp_path: Path) -> None:
    code, payload = run("tool", "curate", "--in", str(frames_dir(tmp_path)))
    assert code == 0
    assert payload["redundant"] == [1, 3]
    assert payload["kept"] == [0, 2]
    assert payload["written"] == []


def test_curate_drops_when_asked(tmp_path: Path) -> None:
    code, _ = run(
        "tool", "curate", "--drop", "--in", str(frames_dir(tmp_path)), "--out", str(tmp_path / "o")
    )
    assert code == 0
    assert sorted(path.name for path in (tmp_path / "o").iterdir()) == ["000.png", "002.png"]


def test_drop_without_a_destination_is_refused(tmp_path: Path) -> None:
    code, payload = run("tool", "curate", "--drop", "--in", str(frames_dir(tmp_path)))
    assert code == 2
    assert payload["error"]["code"] == "no-destination"


@pytest.mark.parametrize("value", ["-0.1", "1.5"])
def test_a_threshold_outside_zero_to_one_is_refused(tmp_path: Path, value: str) -> None:
    code, payload = run("tool", "curate", "--threshold", value, "--in", str(frames_dir(tmp_path)))
    assert code == 2
    assert payload["error"]["code"] == "invalid-threshold"


# R1.10, R3.7 — the two ceilings, and the third route to an asset.


def test_a_grid_past_the_cell_ceiling_is_refused(tmp_path: Path) -> None:
    """`--grid` is typed, but an agent may derive it from what the image suggested, and
    columns times rows is a file each."""
    code, payload = run(
        "tool",
        "cut",
        "--grid",
        "999x999",
        "--in",
        str(sheet(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-grid"
    assert not (tmp_path / "o").exists()


def test_an_alpha_with_a_component_per_pixel_is_refused_not_ground(tmp_path: Path) -> None:
    dithered = np.zeros((200, 200, 4), dtype=np.uint8)
    dithered[::2, ::2] = (200, 30, 30, 255)
    code, payload = run(
        "tool",
        "cut",
        "--mode",
        "islands",
        "--in",
        str(save(tmp_path / "noise.png", dithered)),
        "--out",
        str(tmp_path / "o"),
    )
    assert code == 1
    assert payload["error"]["code"] == "too-many-pieces"
    assert "--grid" in payload["error"]["fix"]


def test_an_asset_reached_through_a_link_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_dir: Any
) -> None:
    """The third route to an asset directory, and the first that resolves an existing one
    and then writes into it. `listing` states the invariant: guarding one route of several
    is the same as guarding none."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    elsewhere = tmp_path / "outside" / "hero"
    elsewhere.mkdir(parents=True)
    meta.save(elsewhere, meta.AssetMeta(key="hero", kind="character"))
    (tmp_path / "assets" / "character").mkdir(parents=True)
    link_dir(tmp_path / "assets" / "character" / "hero", elsewhere)

    code, payload = run("tool", "cut", "--in", str(sheet(tmp_path)), "--asset", "character/hero")
    assert code == 1
    assert payload["error"]["code"] == "asset-escapes-workspace"
    assert not (elsewhere / "frames").exists()


def test_a_piece_filter_on_a_grid_is_refused_rather_than_ignored(tmp_path: Path) -> None:
    """R1.11 — the flags filter *found* pieces, and a grid's cells are given. Advertising
    them on every mode and then quietly doing nothing is the worse of the two options."""
    code, payload = run(
        "tool",
        "cut",
        "--grid",
        "2x1",
        "--min-size",
        "1000",
        "--in",
        str(sheet(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )
    assert code == 2
    assert payload["error"]["code"] == "filter-without-mode"
    assert not (tmp_path / "o").exists()


# specs/sheet-assembly — expand, mirror, align, pack.


def figure_at(path: Path, x: int, y: int, size: int = 12) -> Path:
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[y : y + 4, x : x + 2] = (200, 30, 30, 255)
    return save(path, image)


def a_set(tmp_path: Path) -> Path:
    source = tmp_path / "frames"
    figure_at(source / "001.png", 1, 2)
    figure_at(source / "002.png", 7, 5)
    return source


def test_expand_to_a_size(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "expand",
        "--to",
        "24x24",
        "--in",
        str(figure_at(tmp_path / "a.png", 1, 2)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0
    assert payload["size"] == {"width": 24, "height": 24}
    assert Image.open(tmp_path / "o.png").size == (24, 24)


def test_expand_never_crops(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "expand",
        "--to",
        "4x4",
        "--in",
        str(figure_at(tmp_path / "a.png", 1, 2)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-target"


def test_expand_takes_exactly_one_of_to_and_by(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "expand",
        "--in",
        str(figure_at(tmp_path / "a.png", 1, 2)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "no-target"


def test_mirror_flips_and_says_so(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "mirror",
        "--in",
        str(figure_at(tmp_path / "a.png", 0, 0)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0
    assert payload["mirrored"] is True
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    assert written[0, -1, 3] == 255
    assert written[0, 0, 3] == 0


def test_align_puts_every_frame_on_one_anchor(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "align", "--in", str(a_set(tmp_path)), "--out", str(tmp_path / "out")
    )
    assert code == 0
    assert payload["empty"] == []

    from ssc.core.doctor.masks import alpha_mask, anchor

    written = sorted((tmp_path / "out").iterdir())
    anchors = {anchor(alpha_mask(np.array(Image.open(path).convert("RGBA")))) for path in written}
    assert len(anchors) == 1


def test_align_writes_an_onion_skin_when_asked(tmp_path: Path) -> None:
    code, _ = run(
        "tool",
        "align",
        "--onion",
        str(tmp_path / "onion.png"),
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "out"),
    )
    assert code == 0
    assert (tmp_path / "onion.png").is_file()


def test_pack_reports_the_cell_the_grid_and_the_anchor(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pack",
        "--cols",
        "2",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "s.png"),
    )
    assert code == 0
    assert payload["columns"] == 2
    assert payload["rows"] == 1
    assert payload["cell"] == {"width": 12, "height": 12}
    assert "anchor" in payload
    assert Image.open(tmp_path / "s.png").size == (24, 12)


def test_a_cell_that_does_not_fit_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pack",
        "--cell",
        "4x4",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "s.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-cell"
    assert not (tmp_path / "s.png").exists()
