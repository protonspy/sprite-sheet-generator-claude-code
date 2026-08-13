"""R2.1 to R2.7 — the seven detectors, against arrays whose defect is known by construction.

Every case here is built rather than loaded, so the expected number follows from the
construction rather than from what the code happened to return. The fixtures on disk
(`tests/core/doctor/test_fixtures.py`) are the other half: these say the arithmetic is
right, those say it survives a real PNG.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.doctor import (
    BleedParams,
    Check,
    FlickerParams,
    PaletteParams,
    PixelGridParams,
    SilhouetteParams,
    Status,
    check_bleed,
    check_drift,
    check_flicker,
    check_halo,
    check_palette,
    check_pixel_grid,
    check_silhouette,
    detect_pixel_size,
)

RED = (200, 60, 70)
BLUE = (60, 120, 200)


def solid(height: int, width: int, colour: tuple[int, int, int], alpha: int = 255) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = colour
    image[:, :, 3] = alpha
    return image


def blocks(pixel_size: int, cells_high: int = 4, cells_wide: int = 4) -> np.ndarray:
    """Real pixel art: every cell one flat colour, edges exactly on the grid."""
    small = np.zeros((cells_high, cells_wide, 4), dtype=np.uint8)
    small[:, :, 3] = 255
    for row in range(cells_high):
        for column in range(cells_wide):
            small[row, column, :3] = ((row * 37) % 256, (column * 53) % 256, 90)
    return np.repeat(np.repeat(small, pixel_size, axis=0), pixel_size, axis=1)


# ── pixel_grid · R2.1 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("pixel_size", [2, 4, 8])
def test_the_detected_pixel_size_is_the_one_the_art_was_drawn_at(pixel_size: int) -> None:
    assert detect_pixel_size(blocks(pixel_size)) == pixel_size


def test_real_pixel_art_sits_on_its_own_grid() -> None:
    finding = check_pixel_grid(blocks(4))
    assert finding.status is Status.OK
    assert finding.measurement["off_grid_ratio"] == 0.0


def test_a_gradient_inside_every_cell_is_off_the_grid() -> None:
    """Fake pixel art: the blocks are there, but each one is a ramp rather than a colour."""
    art = blocks(4).copy()
    ramp = np.arange(art.shape[1], dtype=np.uint8)
    art[:, :, 0] = ramp[None, :]
    finding = check_pixel_grid(art)
    assert finding.status is Status.DEFECT
    assert finding.measurement["off_grid_ratio"] > 0


def test_a_pixel_grid_defect_names_snap_as_the_fix() -> None:
    """R1.4 — a defect nobody can act on is a judgement wearing a number's clothes."""
    art = blocks(4).copy()
    art[:, :, 0] = np.arange(art.shape[1], dtype=np.uint8)[None, :]
    assert check_pixel_grid(art).fix == "ssc tool snap"


def test_no_grid_at_all_is_reported_as_off_the_grid_rather_than_perfect() -> None:
    """A detected size of one means no grid was found; calling that 0.0 off-grid would
    report noise as flawless."""
    noise = np.zeros((16, 16, 4), dtype=np.uint8)
    noise[:, :, :3] = np.random.default_rng(1).integers(0, 255, size=(16, 16, 3), dtype=np.uint8)
    noise[:, :, 3] = 255
    finding = check_pixel_grid(noise)
    assert finding.status is Status.DEFECT


def test_the_threshold_is_a_parameter_not_a_truth() -> None:
    art = blocks(4).copy()
    art[0, 0, 0] = 1
    assert check_pixel_grid(art, PixelGridParams(max_off_grid=0.0)).status is Status.DEFECT
    assert check_pixel_grid(art, PixelGridParams(max_off_grid=0.9)).status is Status.OK


# ── halo · R2.4 ───────────────────────────────────────────────────────────────────────


def test_halo_counts_pixels_that_are_neither_transparent_nor_opaque() -> None:
    image = solid(4, 4, RED)
    image[0, 0, 3] = 0
    image[1, 1, 3] = 128
    image[2, 2, 3] = 7
    finding = check_halo(image)
    assert finding.measurement["semi_transparent_px"] == 2
    assert finding.status is Status.DEFECT
    assert finding.fix == "ssc tool bgremove --edge-pass"


def test_a_hard_edged_mask_has_no_halo() -> None:
    image = solid(4, 4, RED)
    image[0, :, 3] = 0
    assert check_halo(image).status is Status.OK


def test_halo_is_skipped_with_a_reason_when_there_is_no_alpha() -> None:
    """R1.3 — skipped is an outcome, not silence."""
    finding = check_halo(np.zeros((4, 4, 3), dtype=np.uint8))
    assert finding.status is Status.SKIPPED
    assert finding.reason is not None


# ── palette · R2.5 ────────────────────────────────────────────────────────────────────


def test_palette_counts_the_distinct_opaque_colours() -> None:
    image = solid(4, 4, RED)
    image[0, :, :3] = BLUE
    assert check_palette(image).measurement["colours"] == 2


def test_a_transparent_pixel_does_not_contribute_a_colour() -> None:
    """What is invisible cannot drift; counting it would make the number unusable."""
    image = solid(4, 4, RED)
    image[0, 0, :3] = (1, 2, 3)
    image[0, 0, 3] = 0
    assert check_palette(image).measurement["colours"] == 1


def test_pixels_outside_a_given_palette_are_counted() -> None:
    image = solid(4, 4, RED)
    image[0, :, :3] = BLUE
    finding = check_palette(image, PaletteParams(allowed=(RED,)))
    assert finding.measurement["off_palette_px"] == 4
    assert finding.status is Status.DEFECT


def test_a_palette_that_covers_everything_is_clean() -> None:
    image = solid(4, 4, RED)
    image[0, :, :3] = BLUE
    assert check_palette(image, PaletteParams(allowed=(RED, BLUE))).status is Status.OK


def test_too_many_colours_against_a_limit_is_a_defect() -> None:
    image = solid(4, 4, RED)
    image[0, :, :3] = BLUE
    assert check_palette(image, PaletteParams(limit=1)).status is Status.DEFECT


def test_without_a_limit_palette_counts_and_judges_nothing() -> None:
    """The limit is a project decision; assuming one here would make the check an opinion."""
    image = solid(4, 4, RED)
    image[0, :, :3] = BLUE
    assert check_palette(image).status is Status.OK


# ── silhouette · R2.7 ─────────────────────────────────────────────────────────────────


def body(size: int = 8) -> np.ndarray:
    image = solid(size, size, RED, alpha=0)
    image[1:-1, 1:-1, 3] = 255
    return image


def test_one_solid_body_with_no_holes_is_clean() -> None:
    finding = check_silhouette(body(), SilhouetteParams(cell=(8, 8)))
    assert finding.status is Status.OK
    assert finding.measurement == {"holes": 0, "fragments": 1, "cell": [8, 8]}


def test_a_hole_punched_through_the_body_is_a_defect() -> None:
    """Background removal that took too much — the opposite side of `halo`."""
    image = body()
    image[3:5, 3:5, 3] = 0
    finding = check_silhouette(image, SilhouetteParams(cell=(8, 8)))
    assert finding.measurement["holes"] == 1
    assert finding.status is Status.DEFECT


def test_a_body_broken_into_islands_is_a_defect() -> None:
    image = body()
    image[:, 3:5, 3] = 0
    finding = check_silhouette(image, SilhouetteParams(cell=(8, 8)))
    assert finding.measurement["fragments"] == 2
    assert finding.status is Status.DEFECT


def test_a_hole_that_vanishes_at_the_played_size_is_not_a_defect() -> None:
    """The reason the mask is reduced before it is measured: a two-pixel gap in a 32px
    render that does not survive the reduction to 8px was never going to be seen."""
    image = solid(32, 32, RED, alpha=0)
    image[2:30, 2:30, 3] = 255
    image[16, 16, 3] = 0
    assert check_silhouette(image, SilhouetteParams(cell=(8, 8))).status is Status.OK


def test_silhouette_is_skipped_without_a_target_cell() -> None:
    """R3.3 — a default here would silently decide the project's visual era."""
    finding = check_silhouette(body(), None)
    assert finding.status is Status.SKIPPED
    assert "cell" in (finding.reason or "")


def test_an_empty_mask_is_a_defect_not_a_pass() -> None:
    """Nothing left is the worst case of taking too much, and it has zero holes."""
    finding = check_silhouette(solid(8, 8, RED, alpha=0), SilhouetteParams(cell=(8, 8)))
    assert finding.status is Status.DEFECT


# ── drift · R2.3 ──────────────────────────────────────────────────────────────────────


def figure(size: int, top: int, left: int) -> np.ndarray:
    image = solid(size, size, RED, alpha=0)
    image[top : top + 4, left : left + 2, 3] = 255
    return image


def test_frames_standing_still_do_not_drift() -> None:
    frames = [figure(16, 8, 7) for _ in range(4)]
    finding = check_drift(frames)
    assert finding.status is Status.OK
    assert finding.measurement["max_drift_px"] == 0.0


def test_a_frame_that_moved_is_measured_in_pixels() -> None:
    frames = [figure(16, 8, 7), figure(16, 8, 7), figure(16, 8, 10), figure(16, 8, 7)]
    finding = check_drift(frames)
    assert finding.status is Status.DEFECT
    assert finding.measurement["max_drift_px"] == pytest.approx(3.0)
    assert finding.measurement["worst_frame"] == 2
    assert finding.fix == "ssc tool align --anchor feet"


def test_drift_measures_the_feet_and_not_the_mass() -> None:
    """An arm swinging moves the centroid without moving the character. Measuring the
    centroid would report every animation as drifting."""
    still, swinging = figure(16, 8, 7), figure(16, 8, 7)
    swinging[2, 10:14, 3] = 255
    assert check_drift([still, swinging]).status is Status.OK


def test_drift_needs_more_than_one_frame() -> None:
    finding = check_drift([figure(16, 8, 7)])
    assert finding.status is Status.SKIPPED
    assert finding.reason is not None


# ── flicker · R2.6 ────────────────────────────────────────────────────────────────────


def test_a_still_region_changing_colour_slightly_is_flicker() -> None:
    first = solid(8, 8, RED)
    second = first.copy()
    second[2:4, 2:4, :3] = (205, 64, 74)
    finding = check_flicker([first, second])
    assert finding.measurement["flicker_px"] == 4
    assert finding.status is Status.DEFECT


def test_two_identical_frames_do_not_flicker() -> None:
    first = solid(8, 8, RED)
    assert check_flicker([first, first.copy()]).status is Status.OK


def test_motion_is_not_flicker() -> None:
    """The separation the whole check rests on: re-quantization moves a colour a little,
    motion moves it a lot."""
    first = solid(8, 8, RED)
    second = first.copy()
    second[2:4, 2:4, :3] = BLUE
    assert check_flicker([first, second]).status is Status.OK


def test_the_worst_adjacent_pair_is_the_one_reported() -> None:
    base = solid(8, 8, RED)
    wobbled = base.copy()
    wobbled[0:4, 0:4, :3] = (203, 63, 73)
    finding = check_flicker([base, base.copy(), wobbled])
    assert finding.measurement["worst_pair"] == 1
    assert finding.measurement["flicker_px"] == 16


def test_where_the_line_sits_is_a_parameter() -> None:
    first = solid(8, 8, RED)
    second = first.copy()
    second[2:4, 2:4, :3] = (170, 60, 70)
    assert check_flicker([first, second], FlickerParams(max_distance=10)).status is Status.OK
    assert check_flicker([first, second], FlickerParams(max_distance=60)).status is Status.DEFECT


def test_flicker_needs_more_than_one_frame() -> None:
    assert check_flicker([solid(8, 8, RED)]).status is Status.SKIPPED


# ── bleed · R2.2 ----──────────────────────────────────────────────────────────────────


def sheet(cols: int, rows: int, cell: int) -> np.ndarray:
    return solid(rows * cell, cols * cell, RED, alpha=0)


def test_content_kept_inside_its_cell_does_not_bleed() -> None:
    art = sheet(2, 1, 8)
    art[2:6, 2:6, 3] = 255
    art[2:6, 10:14, 3] = 255
    finding = check_bleed(art, BleedParams(cols=2, rows=1))
    assert finding.status is Status.OK
    assert finding.measurement["cells_touching_a_boundary"] == 0


def test_content_crossing_into_a_neighbour_is_counted() -> None:
    art = sheet(2, 1, 8)
    art[2:6, 2:9, 3] = 255  # runs past x=7, the boundary between the two cells
    finding = check_bleed(art, BleedParams(cols=2, rows=1))
    assert finding.measurement["cells_touching_a_boundary"] == 2
    assert finding.status is Status.DEFECT
    assert finding.fix == "ssc tool cut --mode islands"


def test_content_at_the_outer_edge_has_nowhere_to_bleed() -> None:
    """The sheet's own border is not a boundary shared with anybody."""
    art = sheet(2, 1, 8)
    art[0:4, 0:4, 3] = 255
    assert check_bleed(art, BleedParams(cols=2, rows=1)).status is Status.OK


def test_bleed_can_key_on_chroma_when_there_is_no_alpha() -> None:
    art = np.zeros((8, 16, 3), dtype=np.uint8)
    art[:, :] = (0, 255, 0)
    art[2:6, 2:9] = RED
    finding = check_bleed(art, BleedParams(cols=2, rows=1, chroma=(0, 255, 0)))
    assert finding.measurement["cells_touching_a_boundary"] == 2


def test_bleed_is_skipped_without_a_grid() -> None:
    """R3.3 — grid auto-detection is frame-recovery's, and two detectors that could
    disagree would surface as a number nobody could reproduce."""
    finding = check_bleed(sheet(2, 1, 8), None)
    assert finding.status is Status.SKIPPED


def test_a_grid_that_does_not_divide_the_sheet_is_skipped_with_the_numbers() -> None:
    finding = check_bleed(sheet(2, 1, 8), BleedParams(cols=3, rows=1))
    assert finding.status is Status.SKIPPED
    assert "3x1" in (finding.reason or "")


# ── the shape every finding has: R1.2 to R1.5 ───────────────────────────────────────────


def test_every_check_reports_a_number_and_never_a_verdict() -> None:
    for finding in (
        check_pixel_grid(blocks(4)),
        check_halo(solid(4, 4, RED)),
        check_palette(solid(4, 4, RED)),
        check_silhouette(body(), SilhouetteParams(cell=(8, 8))),
        check_drift([figure(16, 8, 7)] * 2),
        check_flicker([solid(8, 8, RED)] * 2),
        check_bleed(sheet(2, 1, 8), BleedParams(cols=2, rows=1)),
    ):
        assert finding.measurement, f"{finding.check} reported no measurement"
        assert isinstance(finding.check, Check)
