"""Nine-patch guides, and what stretching will do — specs/ui-assets R1, R2.

The TDD half is `nineslice`. What it pins is the *meaning* of the number rather than any
value: a region uniform along the axis it stretches on scores zero however busy it is in the
other direction, and one that changes along that axis scores above the threshold. Get that
backwards and the check calls every panel broken, or every panel fine, and nobody can tell
which from the number.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core import ninepatch
from ssc.core.doctor.checks import NineSliceParams, check_nineslice
from ssc.core.doctor.finding import Check, Status


def panel(width: int = 32, height: int = 32, block: int = 4) -> np.ndarray:
    """A panel with a border one block wide and a flat middle — the shape that stretches."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = 90
    image[block:-block, block:-block, :3] = 200
    image[:, :, 3] = 255
    return image


# R2.1 — what the number means.


def test_a_panel_whose_regions_are_uniform_along_their_stretch_scores_zero() -> None:
    finding = check_nineslice(panel(), NineSliceParams(guides=(4, 4, 4, 4)))

    assert finding.status is Status.OK
    assert finding.measurement["worst"] == 0


def test_busy_art_across_the_stretch_axis_is_not_a_defect() -> None:
    """A left edge may be as detailed as it likes *horizontally* — that direction is never
    stretched. Only variation down its height smears."""
    image = panel()
    image[:, 0, :3] = 10
    image[:, 1, :3] = 250
    image[:, 2, :3] = 10

    finding = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4)))

    assert finding.status is Status.OK


def test_variation_along_the_stretch_axis_is_the_defect() -> None:
    image = panel()
    image[8:16, 0:4, :3] = 250  # the left edge changes down its own height

    finding = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4)))

    assert finding.status is Status.DEFECT
    assert finding.measurement["worst"] > 0
    assert finding.measurement["worst_region"] == "left"


def test_a_corner_may_be_anything_because_a_corner_never_stretches() -> None:
    image = panel()
    image[0:4, 0:4, :3] = np.arange(4 * 4 * 3, dtype=np.uint8).reshape(4, 4, 3)

    finding = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4)))

    assert finding.status is Status.OK


def test_the_centre_is_measured_on_both_axes() -> None:
    image = panel()
    image[8:16, 6:26, :3] = 40  # a band across the middle: constant across, varying down

    finding = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4)))

    assert finding.status is Status.DEFECT
    assert finding.measurement["worst_region"] == "centre"


def test_the_threshold_decides_and_is_reported() -> None:
    image = panel()
    image[8:16, 0:4, :3] = 100  # ten levels away from 90

    strict = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4), max_variation=1))
    lenient = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4), max_variation=200))

    assert strict.status is Status.DEFECT
    assert lenient.status is Status.OK
    assert lenient.measurement["max_variation"] == 200


# R2.2, R2.4 — the fix, and the input it will not judge.


def test_a_defect_names_the_command_that_produces_guides() -> None:
    image = panel()
    image[8:16, 0:4, :3] = 250

    finding = check_nineslice(image, NineSliceParams(guides=(4, 4, 4, 4)))

    assert "tool ninepatch" in (finding.fix or "")


def test_without_guides_the_check_is_skipped_with_a_reason() -> None:
    finding = check_nineslice(panel())

    assert finding.status is Status.SKIPPED
    assert finding.reason
    assert finding.check is Check.NINESLICE


# R1.2, R1.3 — derived and snapped guides.


def test_guides_are_derived_as_one_pixel_art_pixel_a_side() -> None:
    found = ninepatch.guides_for(panel(32, 32, block=4))

    assert found == (4, 4, 4, 4)


@pytest.mark.parametrize(
    ("given", "expected"),
    [((9, 9, 9, 9), (8, 8, 8, 8)), ((4, 4, 4, 4), (4, 4, 4, 4)), ((7, 5, 6, 2), (8, 4, 8, 4))],
)
def test_a_given_guide_is_snapped_onto_the_pixel_grid(
    given: tuple[int, int, int, int], expected: tuple[int, int, int, int]
) -> None:
    """A guide inside a block makes an engine stretch part of one pixel-art pixel, which
    shimmers at some widths and not others."""
    assert ninepatch.guides_for(panel(32, 32, block=4), given) == expected


def test_a_guide_never_snaps_to_nothing() -> None:
    """Rounding 1 down to 0 with a pixel size of 4 would silently delete the border the
    caller asked for."""
    assert ninepatch.guides_for(panel(32, 32, block=4), (1, 1, 1, 1)) == (4, 4, 4, 4)


# R1.1, R1.5 — the regions.


def test_the_nine_regions_are_reported_with_their_sizes() -> None:
    described = ninepatch.describe(panel(32, 24, block=4), (4, 4, 4, 4))

    assert described["guides"] == {"left": 4, "right": 4, "top": 4, "bottom": 4}
    regions = described["regions"]
    assert regions["top_left"] == {"width": 4, "height": 4}
    assert regions["centre"] == {"width": 24, "height": 16}
    assert regions["bottom_right"] == {"width": 4, "height": 4}
    assert len(regions) == 9


# R1.4 — the guides that describe no panel.


@pytest.mark.parametrize(
    "guides",
    [
        (20, 20, 4, 4),  # left and right meet in the middle of a 32-wide image
        (16, 16, 4, 4),  # exactly meeting: a centre of zero width is not a centre
        (4, 4, 40, 4),  # past the edge
        (-4, 4, 4, 4),  # negative
    ],
)
def test_guides_that_describe_no_panel_are_refused(guides: tuple[int, int, int, int]) -> None:
    with pytest.raises(ValueError, match="guide"):
        ninepatch.describe(panel(32, 32, block=4), guides)
