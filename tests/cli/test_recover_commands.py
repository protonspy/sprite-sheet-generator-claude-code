"""`ssc tool cut|slice|curate` — specs/frame-recovery R1.3, R3, R4.1, R4.3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from click.testing import CliRunner
from conftest import load_meta, save_meta
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

    record = load_meta(tmp_path / "assets/character/hero")
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

    record = load_meta(tmp_path / "assets/icon/coin-01")
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


# plans/ssc-completion.md 3.2 — a dropped frame takes its authored entry with it.


def asset_with_sidecar(tmp_path: Path, frames_block: str | None) -> Path:
    """An asset directory holding the four curate frames and, optionally, a sidecar."""
    asset = tmp_path / "hero"
    for index, fill in enumerate((10, 10, 200, 200)):
        image = np.zeros((8, 8, 4), dtype=np.uint8)
        image[..., :3] = fill
        image[..., 3] = 255
        save(asset / "frames" / "cut" / f"{index:03d}.png", image)
    (asset / "meta.json").write_text("{}", encoding="utf-8")
    if frames_block is not None:
        (asset / "asset.yaml").write_text(frames_block, encoding="utf-8")
    return asset


FOUR_ENTRIES = (
    "playback:\n"
    "  fps: 8\n"
    "frames:\n"
    "- markers: [a0]\n"
    "- markers: [a1]\n"
    "- markers: [a2]\n"
    "- markers: [a3]\n"
)


def curate_drop(asset: Path) -> tuple[int, dict[str, Any]]:
    return run(
        "tool",
        "curate",
        "--drop",
        "--in",
        str(asset / "frames" / "cut"),
        "--out",
        str(asset / "frames" / "curated"),
    )


def test_curate_drop_carries_the_frames_block(tmp_path: Path) -> None:
    asset = asset_with_sidecar(tmp_path, FOUR_ENTRIES)
    code, payload = curate_drop(asset)
    assert code == 0
    assert payload["sidecar"] == str(asset / "asset.yaml")
    document = yaml.safe_load((asset / "asset.yaml").read_text(encoding="utf-8"))
    assert document["frames"] == [{"markers": ["a0"]}, {"markers": ["a2"]}]
    # The rest of the sidecar is not curate's, and it survives.
    assert document["playback"] == {"fps": 8}


def test_curate_without_a_frames_block_rewrites_nothing(tmp_path: Path) -> None:
    asset = asset_with_sidecar(tmp_path, "playback:\n  fps: 8\n")
    before = (asset / "asset.yaml").read_bytes()
    code, payload = curate_drop(asset)
    assert code == 0
    assert payload["sidecar"] is None
    assert (asset / "asset.yaml").read_bytes() == before


def test_curate_outside_an_asset_rewrites_nothing(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "curate",
        "--drop",
        "--in",
        str(frames_dir(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )
    assert code == 0
    assert payload["sidecar"] is None


def test_curate_writing_outside_the_asset_leaves_its_sidecar_alone(tmp_path: Path) -> None:
    # The asset's own frames did not change, so its sidecar must not either.
    asset = asset_with_sidecar(tmp_path, FOUR_ENTRIES)
    code, payload = run(
        "tool",
        "curate",
        "--drop",
        "--in",
        str(asset / "frames" / "cut"),
        "--out",
        str(tmp_path / "elsewhere"),
    )
    assert code == 0
    assert payload["sidecar"] is None
    document = yaml.safe_load((asset / "asset.yaml").read_text(encoding="utf-8"))
    assert len(document["frames"]) == 4


def test_curate_refuses_a_block_it_cannot_line_up(tmp_path: Path) -> None:
    short = "frames:\n- markers: [a0]\n- markers: [a1]\n"
    asset = asset_with_sidecar(tmp_path, short)
    code, payload = curate_drop(asset)
    # Exit 1, not 2: the call was fine, the data was not — the same code every
    # `invalid-sidecar` refusal carries.
    assert code == 1
    assert payload["error"]["code"] == "invalid-sidecar"
    # Nothing half-done: no curated frames on disk, and the block still has its entries.
    assert not (asset / "frames" / "curated").exists()
    document = yaml.safe_load((asset / "asset.yaml").read_text(encoding="utf-8"))
    assert len(document["frames"]) == 2


def test_a_dry_run_carries_nothing(tmp_path: Path) -> None:
    asset = asset_with_sidecar(tmp_path, FOUR_ENTRIES)
    code, payload = run(
        "tool",
        "curate",
        "--drop",
        "--dry-run",
        "--in",
        str(asset / "frames" / "cut"),
        "--out",
        str(asset / "frames" / "curated"),
    )
    assert code == 0
    assert payload["sidecar"] is None
    document = yaml.safe_load((asset / "asset.yaml").read_text(encoding="utf-8"))
    assert len(document["frames"]) == 4


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
    save_meta(elsewhere, meta.AssetMeta(key="hero", kind="character"))
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
    # the default is the vertical axis, so a call with no flag keeps the horizontal
    # flip it always had — existing scripts do not change meaning.
    assert payload["axis"] == "vertical"
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    assert written[0, -1, 3] == 255
    assert written[0, 0, 3] == 0


def test_mirror_about_the_horizontal_axis_flips_top_to_bottom(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "mirror",
        "--axis",
        "horizontal",
        "--in",
        str(figure_at(tmp_path / "a.png", 0, 0)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0
    assert payload["axis"] == "horizontal"
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    # the opaque pixel was at the top; a horizontal-axis flip moves it to the bottom.
    assert written[-1, 0, 3] == 255
    assert written[0, 0, 3] == 0


def test_mirror_refuses_an_unknown_axis(tmp_path: Path) -> None:
    # A bad axis is refused by the choice itself before the command runs, the way
    # every `click.Choice` in the tool does; that surfaces as a usage error, not a
    # JSON object, so the check is on the exit code and the unwritten file.
    result = CliRunner().invoke(
        main,
        [
            "tool",
            "mirror",
            "--axis",
            "diagonal",
            "--in",
            str(figure_at(tmp_path / "a.png", 0, 0)),
            "--out",
            str(tmp_path / "o.png"),
            "--json",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code != 0
    assert not (tmp_path / "o.png").exists()


def test_rotate_90_swaps_width_and_height(tmp_path: Path) -> None:
    source = save(tmp_path / "tall.png", np.zeros((16, 8, 4), dtype=np.uint8))
    code, payload = run(
        "tool", "rotate", "--angle", "90", "--in", str(source), "--out", str(tmp_path / "o.png")
    )
    assert code == 0, payload
    assert payload["angle"] == 90
    assert payload["turns"] == 1
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    # the source was 16 tall by 8 wide; a 90° turn makes it 8 tall by 16 wide.
    assert written.shape[:2] == (8, 16)


def test_rotate_180_keeps_the_dimensions(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool", "rotate", "--angle", "180", "--in", str(source), "--out", str(tmp_path / "o.png")
    )
    assert code == 0, payload
    assert payload["turns"] == 2
    src = np.array(Image.open(source).convert("RGBA"))
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    assert written.shape == src.shape


def test_rotate_reports_the_cell_an_odd_turn_stopped_matching(tmp_path: Path) -> None:
    # a frame packed to a 16x8 cell (width 16, height 8); a quarter turn makes it 8 wide by
    # 16 tall, so the cell it came from no longer fits and the one that does is reported.
    source = save(tmp_path / "wide.png", np.zeros((8, 16, 4), dtype=np.uint8))
    code, payload = run(
        "tool",
        "rotate",
        "--angle",
        "90",
        "--cell",
        "16x8",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["size"] == {"width": 8, "height": 16}
    assert payload["cell"] == {"width": 16, "height": 8}
    assert payload["cell_matches"] is False
    assert payload["turned_cell"] == {"width": 8, "height": 16}


def test_rotate_cell_still_matches_an_even_turn(tmp_path: Path) -> None:
    source = save(tmp_path / "wide.png", np.zeros((8, 16, 4), dtype=np.uint8))
    code, payload = run(
        "tool",
        "rotate",
        "--angle",
        "180",
        "--cell",
        "16x8",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["cell_matches"] is True
    assert "turned_cell" not in payload


def test_rotate_without_a_cell_reports_no_cell(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool", "rotate", "--angle", "90", "--in", str(source), "--out", str(tmp_path / "o.png")
    )
    assert code == 0, payload
    assert "cell" not in payload
    assert "cell_matches" not in payload


def test_rotate_refuses_an_angle_that_is_not_a_quarter_turn(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "rotate",
        "--angle",
        "45",
        "--in",
        str(figure_at(tmp_path / "a.png", 0, 0)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "not-a-quarter-turn"
    # the resampler is the stated reason, so a reader knows why other angles are refused.
    assert "nearest neighbour" in payload["error"]["fix"]
    assert not (tmp_path / "o.png").exists()


def test_rotate_refuses_zero_as_a_no_turn(tmp_path: Path) -> None:
    code, _ = run(
        "tool",
        "rotate",
        "--angle",
        "0",
        "--in",
        str(figure_at(tmp_path / "a.png", 0, 0)),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code != 0
    assert not (tmp_path / "o.png").exists()


def test_trim_crops_every_frame_to_one_shared_box(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "trim", "--in", str(a_set(tmp_path)), "--out", str(tmp_path / "out")
    )
    assert code == 0, payload
    # one box covers the opaque pixels of both frames — the left block (cols 1..2,
    # rows 2..5) and the right (cols 7..8, rows 5..8) — so x=1, y=2, 8 wide, 7 tall.
    assert payload["box"] == {"x": 1, "y": 2, "width": 8, "height": 7}
    assert payload["size"] == {"width": 8, "height": 7}
    written = sorted(path.name for path in (tmp_path / "out").iterdir())
    assert written == ["001.png", "002.png"]
    for name in written:
        assert np.array(Image.open(tmp_path / "out" / name).convert("RGBA")).shape[:2] == (7, 8)


def test_trim_refuses_a_set_with_no_opaque_pixels(tmp_path: Path) -> None:
    empty = np.zeros((8, 8, 4), dtype=np.uint8)
    source = tmp_path / "frames"
    save(source / "001.png", empty)
    code, payload = run("tool", "trim", "--in", str(source), "--out", str(tmp_path / "out"))
    assert code == 1
    assert payload["error"]["code"] == "nothing-to-trim"
    assert not (tmp_path / "out").exists()


def test_offset_moves_content_by_whole_pixels(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)  # opaque block at x=0..1, y=0..3
    code, payload = run(
        "tool",
        "offset",
        "--x",
        "3",
        "--y",
        "2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["dx"] == 3
    assert payload["dy"] == 2
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    # the block moved from the top-left to x=3..4, y=2..5
    assert written[2:6, 3:5, 3].all()
    assert written[:2, :, 3].sum() == 0
    # the canvas keeps its size
    assert written.shape == (12, 12, 4)


def test_offset_negative_moves_left_and_up(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 10, 8)  # block at the bottom-right
    code, payload = run(
        "tool",
        "offset",
        "--x",
        "-4",
        "--y",
        "-2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    src = np.array(Image.open(source).convert("RGBA"))
    assert int(written[..., 3].sum()) == int(src[..., 3].sum())


def test_offset_drops_content_shifted_off_the_canvas(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)  # block at the very top-left
    code, payload = run(
        "tool",
        "offset",
        "--x",
        "11",
        "--y",
        "0",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    src = np.array(Image.open(source).convert("RGBA"))
    # the block was 2px wide; shifted right by 11 on a 12px canvas, one column survives.
    assert written.shape == (12, 12, 4)
    assert int(written[..., 3].sum()) == int(src[..., 3].sum()) - 4 * 255


def test_offset_refuses_a_no_op_shift(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool",
        "offset",
        "--x",
        "0",
        "--y",
        "0",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "no-offset"
    assert not (tmp_path / "o.png").exists()


# the recorded anchor moves with the transform — the point an engine pins the sprite to
# has to land where the sprite's pixels did.


def test_mirror_moves_the_recorded_anchor_by_width_minus_one_minus_x(tmp_path: Path) -> None:
    # a 12-wide frame; the anchor at x=1 mirrors to 12-1-1=10, not 11 — the -1 is the
    # one-pixel jitter the task exists to stop.
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool",
        "mirror",
        "--axis",
        "vertical",
        "--anchor",
        "1,2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["anchor"] == {"x": 10, "y": 2}


def test_mirror_moves_the_anchor_about_the_horizontal_axis(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)  # 12 tall
    code, payload = run(
        "tool",
        "mirror",
        "--axis",
        "horizontal",
        "--anchor",
        "1,2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["anchor"] == {"x": 1, "y": 9}


def test_rotate_moves_the_recorded_anchor(tmp_path: Path) -> None:
    # 90° on a 12-wide frame: (1, 2) -> (2, 12-1-1) = (2, 10).
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool",
        "rotate",
        "--angle",
        "90",
        "--anchor",
        "1,2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["anchor"] == {"x": 2, "y": 10}


def test_offset_moves_the_recorded_anchor(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool",
        "offset",
        "--x",
        "3",
        "--y",
        "2",
        "--anchor",
        "1,2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert payload["anchor"] == {"x": 4, "y": 4}


def test_trim_moves_the_recorded_anchor_by_the_box_origin(tmp_path: Path) -> None:
    # a_set's union box is (1, 2, 8, 7); an anchor at (5, 6) moves to (4, 4).
    code, payload = run(
        "tool",
        "trim",
        "--anchor",
        "5,6",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "out"),
    )
    assert code == 0, payload
    assert payload["anchor"] == {"x": 4, "y": 4}


def test_a_transform_without_an_anchor_reports_none(tmp_path: Path) -> None:
    # the anchor is optional; where it is not given, the payload carries no anchor key,
    # so a caller does not mistake an absent anchor for one at (0, 0).
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool",
        "mirror",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 0, payload
    assert "anchor" not in payload


def test_an_invalid_anchor_is_refused(tmp_path: Path) -> None:
    source = figure_at(tmp_path / "a.png", 0, 0)
    code, payload = run(
        "tool",
        "mirror",
        "--anchor",
        "1",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "o.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-anchor"
    assert not (tmp_path / "o.png").exists()


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


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (("expand", "--by", "8192"), "canvas-too-large"),
        (("pack", "--cols", "4000"), "canvas-too-large"),
    ],
)
def test_a_canvas_past_the_ceiling_is_its_own_refusal(
    tmp_path: Path, argv: tuple[str, ...], code: str
) -> None:
    """Its own code and its own fix: `expand` and `pack` each raise several refusals, and a
    caller acting on the wrong one's `fix` is sent in the wrong direction."""
    exit_code, payload = run(
        "tool", *argv, "--in", str(a_set(tmp_path)), "--out", str(tmp_path / "o.png")
    )
    assert exit_code == 2
    assert payload["error"]["code"] == code
    assert "past" in payload["error"]["message"]


def test_align_reports_the_mode_so_pack_can_be_given_it(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "align",
        "--anchor",
        "centre",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "out"),
    )
    assert code == 0
    assert payload["mode"] == "centre"

    packed_code, packed = run(
        "tool",
        "pack",
        "--anchor",
        "centre",
        "--cols",
        "2",
        "--in",
        str(tmp_path / "out"),
        "--out",
        str(tmp_path / "s.png"),
    )
    assert packed_code == 0
    assert packed["aligned"] is True
    assert packed["anchor"] == payload["anchor"]


# plans/ssc-completion 7.7 — a transform into an asset is a recorded provenance step, so
# `trim` and `offset` stop being implicit moves inside `align` and `pack`.


@pytest.mark.parametrize(
    ("argv", "stage", "command", "params"),
    [
        (("mirror",), "mirror", "tool mirror", {"axis": "vertical"}),
        (("rotate", "--angle", "90"), "rotate", "tool rotate", {"angle": 90, "turns": 1}),
        (("trim",), "trim", "tool trim", None),
        (("offset", "--x", "2"), "offset", "tool offset", {"dx": 2, "dy": 0}),
    ],
)
def test_a_transform_into_an_asset_records_the_transform_in_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: tuple[str, ...],
    stage: str,
    command: str,
    params: dict[str, Any] | None,
) -> None:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")

    code, payload = run("tool", *argv, "--in", str(source), "--asset", "character/hero")
    assert code == 0, payload

    record = load_meta(tmp_path / "assets/character/hero")
    entries = [entry for entry in record.files if entry.stage == stage]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.path == f"frames/{stage}"
    assert entry.file_class == "derived"
    assert entry.produced_by.command == command
    if params is not None:
        assert entry.produced_by.params == params
    else:
        # trim's box is measured, not given; the record carries whatever box it cropped to.
        assert set(entry.produced_by.params["box"]) == {"x", "y", "width", "height"}
    written = sorted((tmp_path / f"assets/character/hero/frames/{stage}").iterdir())
    assert [path.name for path in written] == [f"{i + 1:03d}.png" for i in range(len(written))]
    assert payload["written"] == [f"frames/{stage}/{path.name}" for path in written]


def test_a_dry_run_transform_records_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")

    code, payload = run(
        "tool", "offset", "--x", "1", "--in", str(source), "--asset", "character/hero", "--dry-run"
    )
    assert code == 0, payload
    assert not (tmp_path / "assets/character/hero/frames").exists()
    record = load_meta(tmp_path / "assets/character/hero")
    assert [entry for entry in record.files if entry.stage == "offset"] == []


# plans/ssc-completion 7.8 — a transform into an asset moves the asset's authored boxes by
# the same transform; markers name moments, not places, and ride their frame untouched.


def author_sidecar(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "assets/character/hero/asset.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def test_a_transform_into_an_asset_moves_the_authored_boxes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")
    path = author_sidecar(
        tmp_path,
        {"frames": [{"hitboxes": [[1, 2, 2, 2]], "markers": ["footstep"]}, None]},
    )

    code, payload = run("tool", "mirror", "--in", str(source), "--asset", "character/hero")
    assert code == 0, payload
    assert payload["sidecar"] == str(path)

    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    # the frames are 12 wide: a box spanning [x, x + w) mirrors to [12 - x - w, 12 - x)
    assert document["frames"][0]["hitboxes"] == [[9, 2, 2, 2]]
    assert document["frames"][0]["markers"] == ["footstep"]
    assert document["frames"][1] is None


def test_a_box_the_transform_dropped_leaves_the_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")
    path = author_sidecar(tmp_path, {"frames": [{"hurtboxes": [[0, 0, 2, 2]]}, None]})

    code, payload = run(
        "tool", "offset", "--x", "-4", "--in", str(source), "--asset", "character/hero"
    )
    assert code == 0, payload
    # shifted entirely off the canvas, the box is gone with the pixels it covered
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert document["frames"] == [None, None]


def test_a_frames_block_that_cannot_line_up_refuses_the_whole_transform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")
    author_sidecar(tmp_path, {"frames": [{"hitboxes": [[1, 2, 2, 2]]}]})

    code, payload = run("tool", "mirror", "--in", str(source), "--asset", "character/hero")
    assert code == 1
    assert payload["error"]["code"] == "invalid-sidecar"
    # planned before the frames land, so a refusal costs nothing on disk
    assert not (tmp_path / "assets/character/hero/frames").exists()


def test_a_transform_without_a_frames_block_rewrites_no_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    new_asset("character", "hero")

    code, payload = run("tool", "mirror", "--in", str(source), "--asset", "character/hero")
    assert code == 0, payload
    assert payload["sidecar"] is None
