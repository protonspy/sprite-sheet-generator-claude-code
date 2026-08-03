"""R4.1 · R4.2 — the fixtures with measured defects, and the numbers they measure to.

Every check has one input carrying its defect and one free of it. These numbers are the
contract: `doctor` is validated against them, and everything downstream depends on
`doctor` being right. A change here means a detector changed, and that is the thing to
look at — never the fixture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ssc.cli.commands.doctor import load_input, measure
from ssc.core.doctor import Check, Status

FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures/doctor"

CELL = (8, 8)


def finding(name: str, check: Check, **options: Any) -> Any:
    report = measure(load_input(FIXTURES / name), **options)
    return next(f for f in report.findings if f.check is check)


# ── one clean and one defective input per check ───────────────────────────────────────


@pytest.mark.parametrize(
    ("check", "clean", "defective", "options"),
    [
        (Check.PIXEL_GRID, "pixel-grid-clean.png", "pixel-grid-defect.png", {}),
        (Check.HALO, "halo-clean.png", "halo-defect.png", {}),
        (Check.PALETTE, "palette-clean.png", "palette-defect.png", {"colour_limit": 8}),
        (Check.SILHOUETTE, "silhouette-clean.png", "silhouette-holes.png", {"cell": CELL}),
        (Check.SILHOUETTE, "silhouette-clean.png", "silhouette-split.png", {"cell": CELL}),
        (Check.BLEED, "bleed-clean.png", "bleed-defect.png", {"grid": (2, 1)}),
        (Check.DRIFT, "drift-clean", "drift-defect", {}),
        (Check.FLICKER, "flicker-clean", "flicker-defect", {}),
    ],
)
def test_each_check_separates_its_defect_from_its_clean_counterpart(
    check: Check, clean: str, defective: str, options: dict[str, Any]
) -> None:
    assert finding(clean, check, **options).status is Status.OK, f"{clean} should be clean"
    assert finding(defective, check, **options).status is Status.DEFECT, f"{defective} is not"


# ── the measured numbers ──────────────────────────────────────────────────────────────


def test_real_pixel_art_is_detected_at_the_size_it_was_drawn() -> None:
    """8x8 art blocked up 4x: the grid is there and every cell is one colour."""
    measured = finding("pixel-grid-clean.png", Check.PIXEL_GRID).measurement
    assert measured == {"pixel_size": 4, "off_grid_ratio": 0.0}


def test_a_bicubic_upscale_has_no_grid_left() -> None:
    """The same art through a filter that ramps every block edge. A detected size of 1 is
    the honest answer — there is no grid — and the ratio says so rather than passing."""
    measured = finding("pixel-grid-defect.png", Check.PIXEL_GRID).measurement
    assert measured == {"pixel_size": 1, "off_grid_ratio": 1.0}


def test_a_feathered_edge_is_forty_semi_transparent_pixels() -> None:
    assert finding("halo-defect.png", Check.HALO).measurement["semi_transparent_px"] == 40
    assert finding("halo-clean.png", Check.HALO).measurement["semi_transparent_px"] == 0


def test_an_unquantized_ramp_is_forty_eight_colours_against_a_budget_of_eight() -> None:
    measured = finding("palette-defect.png", Check.PALETTE, colour_limit=8).measurement
    assert measured == {"colours": 48, "limit": 8}
    assert finding("palette-clean.png", Check.PALETTE, colour_limit=8).measurement["colours"] == 3


def test_a_hole_and_a_split_are_different_numbers() -> None:
    """Two failures, told apart. Over-removal that punched through, against over-removal
    that cut the body in two."""
    holed = finding("silhouette-holes.png", Check.SILHOUETTE, cell=CELL).measurement
    split = finding("silhouette-split.png", Check.SILHOUETTE, cell=CELL).measurement
    assert (holed["holes"], holed["fragments"]) == (1, 1)
    assert (split["holes"], split["fragments"]) == (0, 2)


def test_an_arm_across_the_cell_boundary_touches_both_cells() -> None:
    measured = finding("bleed-defect.png", Check.BLEED, grid=(2, 1)).measurement
    assert measured == {"cells_touching_a_boundary": 2, "cells": 2}


def test_one_frame_slid_three_pixels() -> None:
    measured = finding("drift-defect", Check.DRIFT).measurement
    assert measured == {"max_drift_px": 3.0, "worst_frame": 2, "frames": 4}


def test_a_requantized_frame_wobbles_over_the_whole_body() -> None:
    measured = finding("flicker-defect", Check.FLICKER).measurement
    assert measured["flicker_px"] == 384
    assert measured["worst_pair"] == 1


def test_sliding_a_frame_is_not_reported_as_flicker() -> None:
    """The drift fixture moves a frame by three pixels — a large colour change at every
    edge, which is motion. If `flicker` fired here the threshold would be meaningless."""
    assert finding("drift-defect", Check.FLICKER).status is Status.OK


def test_requantizing_a_frame_is_not_reported_as_drift() -> None:
    """And the mirror: the flicker fixture does not move, so the anchor does not move."""
    assert finding("flicker-defect", Check.DRIFT).status is Status.OK
