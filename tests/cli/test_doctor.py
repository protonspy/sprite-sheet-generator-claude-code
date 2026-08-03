"""R1.1, R1.3, R3.1 to R3.5 — the command around the detectors."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ssc.cli.app import main

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures/doctor"


def run(*args: str) -> tuple[int, dict[str, object]]:
    result = CliRunner().invoke(main, ["tool", "doctor", "--json", *args], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def checks(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {entry["check"]: entry for entry in payload["checks"]}  # type: ignore[index,union-attr]


def test_all_seven_checks_appear_in_every_report() -> None:
    """R1.1 — and a check that did not apply says so rather than being left out."""
    _, payload = run("--in", str(FIXTURES / "pixel-grid-clean.png"))
    assert set(checks(payload)) == {
        "pixel_grid",
        "bleed",
        "drift",
        "halo",
        "palette",
        "flicker",
        "silhouette",
    }


def test_a_skipped_check_carries_its_reason_and_no_measurement() -> None:
    """R1.3 — silence would be indistinguishable from a clean result."""
    _, payload = run("--in", str(FIXTURES / "pixel-grid-clean.png"))
    entry = checks(payload)["drift"]
    assert entry["status"] == "skipped"
    assert entry["reason"]
    assert "measurement" not in entry


def test_a_defect_names_the_command_that_repairs_it() -> None:
    """R1.4 — the field a harness acts on."""
    _, payload = run("--in", str(FIXTURES / "pixel-grid-defect.png"))
    assert checks(payload)["pixel_grid"]["fix"] == "ssc tool snap"


def test_finding_defects_is_still_a_successful_measurement() -> None:
    """R3.4 — exiting non-zero on a defect would make a clean run and a broken tool
    indistinguishable to a caller."""
    code, payload = run("--in", str(FIXTURES / "pixel-grid-defect.png"))
    assert code == 0
    assert payload["defects"] >= 1


def test_a_directory_is_read_as_a_frame_set() -> None:
    """R3.1 — which is what makes drift and flicker measurable at all."""
    _, payload = run("--in", str(FIXTURES / "drift-defect"))
    assert checks(payload)["drift"]["status"] == "defect"
    assert checks(payload)["drift"]["measurement"]["frames"] == 4  # type: ignore[index]


def test_bleed_needs_both_halves_of_the_grid() -> None:
    """R3.3 — half a grid is not a grid, and guessing the other half would invent one."""
    _, payload = run("--in", str(FIXTURES / "bleed-defect.png"), "--cols", "2")
    assert checks(payload)["bleed"]["status"] == "skipped"

    _, payload = run("--in", str(FIXTURES / "bleed-defect.png"), "--cols", "2", "--rows", "1")
    assert checks(payload)["bleed"]["status"] == "defect"


def test_silhouette_waits_for_a_target_cell() -> None:
    _, payload = run("--in", str(FIXTURES / "silhouette-holes.png"))
    assert checks(payload)["silhouette"]["status"] == "skipped"

    _, payload = run("--in", str(FIXTURES / "silhouette-holes.png"), "--cell", "8x8")
    assert checks(payload)["silhouette"]["status"] == "defect"


def test_a_palette_is_read_as_hex() -> None:
    _, payload = run("--in", str(FIXTURES / "palette-clean.png"), "--palette", "1a1423")
    assert checks(payload)["palette"]["measurement"]["off_palette_px"] > 0  # type: ignore[index,operator]


def test_a_path_that_is_neither_file_nor_directory_is_an_error(tmp_path: Path) -> None:
    """R3.5."""
    code, payload = run("--in", str(tmp_path / "nothing-here.png"))
    assert code == 1
    assert payload["error"]["code"] == "no-input"  # type: ignore[index]


def test_a_directory_with_no_images_says_so(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("no art here")
    code, payload = run("--in", str(tmp_path))
    assert code == 1
    assert payload["error"]["code"] == "no-images"  # type: ignore[index]


def test_a_malformed_cell_is_refused_before_anything_is_measured() -> None:
    code, payload = run("--in", str(FIXTURES / "halo-clean.png"), "--cell", "sixty-four")
    assert code == 1
    assert payload["error"]["code"] == "invalid-cell"  # type: ignore[index]


def test_a_malformed_palette_colour_is_refused() -> None:
    code, payload = run("--in", str(FIXTURES / "halo-clean.png"), "--palette", "nothex")
    assert code == 1
    assert payload["error"]["code"] == "invalid-colour"  # type: ignore[index]


def test_doctor_writes_nothing(tmp_path: Path) -> None:
    """The one `tool` command with no `--out`."""
    target = tmp_path / "copy.png"
    target.write_bytes((FIXTURES / "halo-clean.png").read_bytes())
    before = target.read_bytes()
    run("--in", str(target))
    assert target.read_bytes() == before
    assert [path.name for path in tmp_path.iterdir()] == ["copy.png"]
