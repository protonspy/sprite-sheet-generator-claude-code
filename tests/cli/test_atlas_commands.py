"""`ssc tool pack --atlas` — specs/atlas-packing R1.2, R1.3, R1.4, R1.6, R2.3, R3."""

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


def save(path: Path, width: int, height: int, colour: int = 200) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :] = (colour, colour, colour, 255)
    Image.fromarray(image, mode="RGBA").save(path)
    return path


@pytest.fixture
def icons(tmp_path: Path) -> Path:
    directory = tmp_path / "icons"
    save(directory / "sword.png", 16, 24)
    save(directory / "shield.png", 20, 20)
    save(directory / "potion.png", 12, 16)
    return directory


# R1.2, R1.3 — an entry is addressed by name and carries its own rect and anchor.


def test_every_entry_is_reported_with_its_id_rect_and_anchor(icons: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "pack", "--atlas", "--in", str(icons), "--out", str(tmp_path / "a.png")
    )

    assert code == 0
    assert payload["layout"] == "bin"
    by_id = {entry["id"]: entry for entry in payload["entries"]}
    assert sorted(by_id) == ["potion", "shield", "sword"]
    assert by_id["sword"]["rect"]["width"] == 16
    assert by_id["sword"]["rect"]["height"] == 24
    assert set(by_id["sword"]["anchor"]) == {"x", "y"}
    assert Image.open(tmp_path / "a.png").size == (payload["width"], payload["height"])


def test_an_id_is_the_filename_and_survives_a_neighbour_leaving(
    icons: Path, tmp_path: Path
) -> None:
    """R1.3's whole point: the index an engine holds must not shift because a set lost one
    entry. An id derived from position would renumber every entry after the gap."""
    _, before = run("tool", "pack", "--atlas", "--in", str(icons), "--out", str(tmp_path / "a.png"))
    (icons / "shield.png").unlink()
    _, after = run("tool", "pack", "--atlas", "--in", str(icons), "--out", str(tmp_path / "b.png"))

    assert sorted(entry["id"] for entry in after["entries"]) == ["potion", "sword"]
    kept = {entry["id"] for entry in before["entries"]} & {
        entry["id"] for entry in after["entries"]
    }
    assert kept == {"potion", "sword"}


def test_two_files_that_resolve_to_one_id_are_refused_by_name(tmp_path: Path) -> None:
    directory = tmp_path / "clash"
    save(directory / "sword.png", 8, 8)
    save(directory / "sword.bmp", 8, 8)

    code, payload = run(
        "tool", "pack", "--atlas", "--in", str(directory), "--out", str(tmp_path / "a.png")
    )

    assert code == 2
    assert payload["error"]["code"] == "duplicate-id"
    assert "sword.bmp" in payload["error"]["message"]
    assert "sword.png" in payload["error"]["message"]


# R1.6, R2.3 — each refusal carries the fix that answers it, and they differ.


def test_an_entry_too_wide_for_the_atlas_is_refused(tmp_path: Path) -> None:
    directory = tmp_path / "wide"
    save(directory / "banner.png", 200, 8)

    code, payload = run(
        "tool",
        "pack",
        "--atlas",
        "--width",
        "64",
        "--in",
        str(directory),
        "--out",
        str(tmp_path / "a.png"),
    )

    assert code == 2
    assert payload["error"]["code"] == "entry-does-not-fit"
    assert "banner" in payload["error"]["message"]
    assert "--width" in payload["error"]["fix"]


def test_an_extrude_wider_than_the_padding_is_refused(icons: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pack",
        "--atlas",
        "--padding",
        "1",
        "--extrude",
        "4",
        "--in",
        str(icons),
        "--out",
        str(tmp_path / "a.png"),
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-gap"
    assert "--padding" in payload["error"]["fix"]
    assert "wider than the padding" in payload["error"]["message"]


def test_the_padding_and_extrude_are_reported_back(icons: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pack",
        "--atlas",
        "--padding",
        "2",
        "--extrude",
        "2",
        "--in",
        str(icons),
        "--out",
        str(tmp_path / "a.png"),
    )

    assert code == 0
    assert (payload["padding"], payload["extrude"]) == (2, 2)


def test_a_dry_run_reports_the_placement_and_writes_nothing(icons: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "pack", "--atlas", "--dry-run", "--in", str(icons), "--out", str(tmp_path / "a.png")
    )

    assert code == 0
    assert payload["dry_run"] is True
    assert len(payload["entries"]) == 3
    assert not (tmp_path / "a.png").exists()


# R3.1, R3.2 — the layout comes from the kind, and an animation is not an atlas.


def test_a_kind_that_animates_cannot_be_packed_as_an_atlas(
    icons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run(
        "tool",
        "pack",
        "--atlas",
        "--kind",
        "character",
        "--in",
        str(icons),
        "--out",
        str(tmp_path / "a.png"),
    )

    assert code == 2
    assert payload["error"]["code"] == "kind-animates"
    assert "without --atlas" in payload["error"]["fix"]


def test_a_kind_declaring_bin_packs_as_an_atlas_without_the_flag(
    icons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3.1 — the profile is where a project decides this, so it decides it."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run(
        "tool", "pack", "--kind", "icon", "--in", str(icons), "--out", str(tmp_path / "a.png")
    )

    assert code == 0
    assert payload["layout"] == "bin"
    assert len(payload["entries"]) == 3


def test_a_kind_declaring_grid_refuses_to_be_overridden_into_an_atlas(
    icons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run(
        "tool",
        "pack",
        "--atlas",
        "--kind",
        "tile",
        "--in",
        str(icons),
        "--out",
        str(tmp_path / "a.png"),
    )

    assert code == 2
    assert payload["error"]["code"] == "layout-is-grid"


def test_the_cell_sheet_is_untouched_by_any_of_this(icons: Path, tmp_path: Path) -> None:
    """The other half: `pack` without `--atlas` is the command that existed before."""
    code, payload = run(
        "tool", "pack", "--cols", "3", "--in", str(icons), "--out", str(tmp_path / "s.png")
    )

    assert code == 0
    assert payload["columns"] == 3
    assert "entries" not in payload


def test_naming_an_animating_kind_still_packs_an_ordinary_sheet(
    icons: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3.2 refuses the *atlas*, not the kind. Checking `animates` while merely reading the
    profile refused `--kind character --cols 3` — a plain sheet of the commonest animating
    kind — with a fix naming a flag the caller never passed."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run(
        "tool",
        "pack",
        "--kind",
        "character",
        "--cols",
        "3",
        "--in",
        str(icons),
        "--out",
        str(tmp_path / "s.png"),
    )

    assert code == 0
    assert payload["columns"] == 3
    assert "entries" not in payload


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (["--padding", "100"], "invalid-gap"),
        (["--padding", "1", "--extrude", "4"], "invalid-gap"),
    ],
)
def test_an_out_of_range_gap_is_told_apart_from_an_extrude_past_its_padding(
    argv: list[str], code: str, icons: Path, tmp_path: Path
) -> None:
    """Routing by message rather than by type sent "padding and extrude are capped at 64"
    to the extrusion's refusal, whose fix says to raise the padding that is already too
    large."""
    exit_code, payload = run(
        "tool", "pack", "--atlas", *argv, "--in", str(icons), "--out", str(tmp_path / "a.png")
    )

    assert exit_code == 2
    assert payload["error"]["code"] == code
