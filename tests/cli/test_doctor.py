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


def test_every_check_appears_in_every_report() -> None:
    """R1.1 — and a check that did not apply says so rather than being left out.

    `seam` is in the report too, and skipped. It arrived as `specs/tile-assets/`'s delta and
    is meaningful only on something meant to tile, so it is asked for rather than run — but
    *present and skipped* is the same contract every other inapplicable check already has.
    """
    _, payload = run("--in", str(FIXTURES / "pixel-grid-clean.png"))
    assert set(checks(payload)) == {
        "pixel_grid",
        "bleed",
        "drift",
        "halo",
        "palette",
        "flicker",
        "silhouette",
        "seam",
        "nineslice",
        "consistency",
        "scale",
    }
    assert checks(payload)["seam"]["status"] == "skipped"
    assert checks(payload)["seam"]["reason"]
    assert checks(payload)["nineslice"]["status"] == "skipped"
    # `scale` is cross-set; a single image has nothing to vary, so it is skipped rather
    # than left out — the same contract every inapplicable check already has.
    assert checks(payload)["scale"]["status"] == "skipped"


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


def test_an_image_over_the_pixel_ceiling_is_refused_before_it_is_decoded(tmp_path: Path) -> None:
    """R3.7 — doctor reads art a model produced, unattended. A fine checkerboard that is
    small on disk decodes to hundreds of megabytes, and every detector then walks it."""
    from PIL import Image

    # The ceiling moved to `cli.frames` when `snap` and `pixelart` gained the same
    # exposure; one reader, one limit. This still asserts what it always did — the
    # command refuses before decoding — through the module that now owns the number.
    from ssc.cli import frames

    huge = tmp_path / "huge.png"
    Image.new("RGBA", (64, 64)).save(huge)
    original = frames.MAX_PIXELS
    try:
        frames.MAX_PIXELS = 100
        code, payload = run("--in", str(huge))
    finally:
        frames.MAX_PIXELS = original
    assert code == 1
    assert payload["error"]["code"] == "image-too-large"  # type: ignore[index]


def test_a_cell_past_the_ceiling_is_refused(tmp_path: Path) -> None:
    """The silhouette mask is built at the *target* size, so an unbounded cell allocates
    an unbounded array from a tiny input."""
    code, payload = run("--in", str(FIXTURES / "halo-clean.png"), "--cell", "99999x99999")
    assert code == 1
    assert payload["error"]["code"] == "invalid-cell"  # type: ignore[index]


def test_a_zero_cell_is_refused() -> None:
    code, _ = run("--in", str(FIXTURES / "halo-clean.png"), "--cell", "0x8")
    assert code == 1


def test_bleed_keys_on_chroma_where_the_sheet_has_no_alpha(tmp_path: Path) -> None:
    """R3.6 — M1's promise is repairing a sheet somebody already has, and such a sheet is
    flat green with no alpha at all."""
    import numpy as np
    from PIL import Image

    art = np.zeros((16, 32, 3), dtype=np.uint8)
    art[:, :] = (0, 255, 0)
    art[4:12, 3:20] = (200, 60, 70)
    path = tmp_path / "green.png"
    Image.fromarray(art, mode="RGB").save(path)

    _, payload = run("--in", str(path), "--cols", "2", "--rows", "1", "--chroma", "00ff00")
    assert checks(payload)["bleed"]["status"] == "defect"


def _write_set(directory: Path, height: int, *, frames: int = 2) -> None:
    """Fill `directory` with `frames` PNGs holding one opaque rectangle of `height`."""
    import numpy as np
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    for index in range(frames):
        image = np.zeros((16, 16, 4), dtype=np.uint8)
        image[1 : 1 + height, 1 : 1 + height, :3] = 200
        image[1 : 1 + height, 1 : 1 + height, 3] = 255
        Image.fromarray(image, mode="RGBA").save(directory / f"{index:03d}.png")


def test_scale_reports_the_cross_set_variation_and_names_normalise(tmp_path: Path) -> None:
    """Plan 4.3 — the sets of one asset given with repeated `--in`; the two-pixel gap is the
    defect, and `tool normalise` is the fix."""
    idle = tmp_path / "idle"
    walk = tmp_path / "walk"
    _write_set(idle, 4)
    _write_set(walk, 6)

    _, payload = run("--in", str(idle), "--in", str(walk))
    entry = checks(payload)["scale"]
    assert entry["status"] == "defect"
    assert entry["measurement"]["variation_px"] == 2.0  # type: ignore[index]
    assert entry["fix"] == "ssc tool normalise"


def test_scale_is_skipped_on_a_single_set(tmp_path: Path) -> None:
    """The seven checks run on the first `--in`; `scale` needs a second set to vary against."""
    idle = tmp_path / "idle"
    _write_set(idle, 4)

    _, payload = run("--in", str(idle))
    entry = checks(payload)["scale"]
    assert entry["status"] == "skipped"
    assert entry["reason"]
