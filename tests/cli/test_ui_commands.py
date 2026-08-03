"""`ssc tool ninepatch`, `tool states`, and `doctor --check nineslice` — specs/ui-assets."""

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


def panel(path: Path, width: int = 32, height: int = 32, block: int = 4) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = 90
    image[block:-block, block:-block, :3] = 200
    image[:, :, 3] = 255
    Image.fromarray(image, mode="RGBA").save(path)
    return path


# R1.1, R1.3, R1.5 — the guides and the regions.


def test_the_guides_and_the_nine_regions_are_reported(tmp_path: Path) -> None:
    code, payload = run("tool", "ninepatch", "--in", str(panel(tmp_path / "p.png")))

    assert code == 0
    assert payload["guides"] == {"left": 4, "right": 4, "top": 4, "bottom": 4}
    assert payload["regions"]["centre"] == {"width": 24, "height": 24}
    assert len(payload["regions"]) == 9
    assert payload["derived"] is True


def test_given_guides_are_snapped_onto_the_pixel_grid(tmp_path: Path) -> None:
    """A guide inside a block makes an engine stretch part of one pixel-art pixel."""
    code, payload = run(
        "tool", "ninepatch", "--guides", "9,9,9,9", "--in", str(panel(tmp_path / "p.png"))
    )

    assert code == 0
    assert payload["guides"] == {"left": 8, "right": 8, "top": 8, "bottom": 8}
    assert payload["derived"] is False


def test_guides_that_leave_no_centre_are_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "ninepatch", "--guides", "20,20,4,4", "--in", str(panel(tmp_path / "p.png"))
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-guides"


def test_a_malformed_guide_list_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "ninepatch", "--guides", "4,4", "--in", str(panel(tmp_path / "p.png"))
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-guides"
    assert "left,right,top,bottom" in payload["error"]["fix"]


def test_a_directory_of_panels_is_refused(tmp_path: Path) -> None:
    """A nine-patch is one image; a set of them is four different answers."""
    panel(tmp_path / "panels" / "a.png")
    panel(tmp_path / "panels" / "b.png")

    code, payload = run("tool", "ninepatch", "--in", str(tmp_path / "panels"))

    assert code == 2
    assert payload["error"]["code"] == "not-one-panel"


def test_ninepatch_writes_nothing(tmp_path: Path) -> None:
    target = panel(tmp_path / "p.png")
    before = target.read_bytes()

    run("tool", "ninepatch", "--in", str(target))

    assert target.read_bytes() == before
    assert [path.name for path in tmp_path.iterdir()] == ["p.png"]


# R2.2, R2.3, R2.4 — the check, asked for.


def test_nineslice_is_skipped_unless_it_is_asked_for(tmp_path: Path) -> None:
    _, payload = run("tool", "doctor", "--in", str(panel(tmp_path / "p.png")))

    finding = next(entry for entry in payload["checks"] if entry["check"] == "nineslice")
    assert finding["status"] == "skipped"
    assert "panels" in finding["reason"]


def test_nineslice_asked_for_without_guides_says_what_it_needs(tmp_path: Path) -> None:
    _, payload = run(
        "tool", "doctor", "--check", "nineslice", "--in", str(panel(tmp_path / "p.png"))
    )

    finding = next(entry for entry in payload["checks"] if entry["check"] == "nineslice")
    assert finding["status"] == "skipped"
    assert "guides" in finding["reason"]


def test_a_panel_that_stretches_cleanly_measures_clean(tmp_path: Path) -> None:
    _, payload = run(
        "tool",
        "doctor",
        "--check",
        "nineslice",
        "--guides",
        "4,4,4,4",
        "--in",
        str(panel(tmp_path / "p.png")),
    )

    finding = next(entry for entry in payload["checks"] if entry["check"] == "nineslice")
    assert finding["status"] == "ok"
    assert finding["measurement"]["worst"] == 0


def test_an_edge_that_varies_down_its_height_is_a_defect_naming_ninepatch(tmp_path: Path) -> None:
    image = np.zeros((32, 32, 4), dtype=np.uint8)
    image[:, :, :3] = 90
    image[4:-4, 4:-4, :3] = 200
    image[8:16, 0:4, :3] = 250
    image[:, :, 3] = 255
    Image.fromarray(image, mode="RGBA").save(tmp_path / "bad.png")

    _, payload = run(
        "tool",
        "doctor",
        "--check",
        "nineslice",
        "--guides",
        "4,4,4,4",
        "--in",
        str(tmp_path / "bad.png"),
    )

    finding = next(entry for entry in payload["checks"] if entry["check"] == "nineslice")
    assert finding["status"] == "defect"
    assert finding["fix"] == "ssc tool ninepatch"
    assert finding["measurement"]["worst_region"] == "left"


def test_the_ui_kind_asks_for_nineslice_by_declaring_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The harness route, same as `seam`: name the kind, get the checks it declares."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    _, payload = run(
        "tool",
        "doctor",
        "--kind",
        "ui",
        "--guides",
        "4,4,4,4",
        "--in",
        str(panel(tmp_path / "p.png")),
    )

    finding = next(entry for entry in payload["checks"] if entry["check"] == "nineslice")
    assert finding["status"] == "ok"


# R3.1, R3.2, R3.3 — states.


@pytest.fixture
def states(tmp_path: Path) -> Path:
    directory = tmp_path / "button"
    for name in ("normal", "hover", "pressed", "disabled"):
        panel(directory / f"{name}.png", 16, 8, block=2)
    return directory


def test_the_states_are_packed_in_the_order_an_engine_expects(states: Path, tmp_path: Path) -> None:
    """Canonical order, not filename order — alphabetically `disabled` sorts first, which
    would put every state in the wrong cell."""
    code, payload = run("tool", "states", "--in", str(states), "--out", str(tmp_path / "s.png"))

    assert code == 0
    assert [entry["name"] for entry in payload["states"]] == [
        "normal",
        "hover",
        "pressed",
        "disabled",
    ]
    assert payload["states"][1]["rect"] == {"x": 16, "y": 0, "width": 16, "height": 8}
    assert Image.open(tmp_path / "s.png").size == (64, 8)


def test_a_partial_set_keeps_the_order_of_the_states_it_has(tmp_path: Path) -> None:
    directory = tmp_path / "button"
    panel(directory / "normal.png", 16, 8, block=2)
    panel(directory / "pressed.png", 16, 8, block=2)

    _, payload = run("tool", "states", "--in", str(directory), "--out", str(tmp_path / "s.png"))

    assert [entry["name"] for entry in payload["states"]] == ["normal", "pressed"]


def test_a_name_that_is_not_a_state_is_refused_naming_the_ones_that_are(tmp_path: Path) -> None:
    directory = tmp_path / "button"
    panel(directory / "normal.png", 16, 8, block=2)
    panel(directory / "hovver.png", 16, 8, block=2)

    code, payload = run("tool", "states", "--in", str(directory), "--out", str(tmp_path / "s.png"))

    assert code == 2
    assert payload["error"]["code"] == "unknown-state"
    assert "hovver" in payload["error"]["message"]
    assert "disabled" in payload["error"]["fix"]


def test_states_of_different_sizes_are_refused(tmp_path: Path) -> None:
    directory = tmp_path / "button"
    panel(directory / "normal.png", 16, 8, block=2)
    panel(directory / "hover.png", 24, 8, block=2)

    code, payload = run("tool", "states", "--in", str(directory), "--out", str(tmp_path / "s.png"))

    assert code == 2
    assert payload["error"]["code"] == "states-differ"
    assert "16x8" in payload["error"]["message"]
    assert "24x8" in payload["error"]["message"]


@pytest.mark.parametrize(
    "guides",
    [
        "9" * 350,  # `int()` takes it; the float division inside `snap` would not
        "\u00b2,0,0,0",  # `str.isdigit()` is true for a superscript; `int()` refuses it
        "4,4,4,x",
    ],
)
def test_a_guide_that_is_not_a_plain_number_is_refused_rather_than_crashing(
    guides: str, tmp_path: Path
) -> None:
    """Each of these used to reach an `internal-error` instead of the refusal the parser
    exists to give — one through Python's float range, one through `isdigit()` being true
    for digits `int()` does not accept."""
    code, payload = run(
        "tool", "ninepatch", "--guides", guides, "--in", str(panel(tmp_path / "p.png"))
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-guides"


def test_two_files_that_name_one_state_are_refused(tmp_path: Path) -> None:
    """The state name is lower-cased, so `Hover.png` is the hover state — which is exactly
    why a collision has to be refused rather than silently resolved."""
    directory = tmp_path / "button"
    panel(directory / "Hover.png", 16, 8, block=2)
    panel(directory / "hover.bmp", 16, 8, block=2)

    code, payload = run("tool", "states", "--in", str(directory), "--out", str(tmp_path / "s.png"))

    assert code == 2
    assert payload["error"]["code"] == "duplicate-state"
    assert "hover" in payload["error"]["message"]
