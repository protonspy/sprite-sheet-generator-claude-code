"""The `scale` check — plan `sprite-normalisation-gate` 4.3.

The cross-set number: the variation in visible height across the sets of one asset, with
`tool normalise` named as its fix. Pinned by the simple cases — one set is skipped, two sets
on one height are clean, the two-pixel gap is the defect, and a blank set is not averaged in.
"""

from __future__ import annotations

import numpy as np

from ssc.core.doctor import Status, check_scale


def sprite_set(height: int, *, frames: int = 2, canvas: int = 16) -> list[np.ndarray]:
    """A set of `frames` identical RGBA frames holding an opaque rectangle of `height`.

    Every frame the same so the set's median visible height is exactly `height`, with no
    within-set jitter to muddle the cross-set comparison.
    """
    sequence: list[np.ndarray] = []
    for _ in range(frames):
        image = np.zeros((canvas, canvas, 4), dtype=np.uint8)
        image[1 : 1 + height, 1 : 1 + height, :3] = 200
        image[1 : 1 + height, 1 : 1 + height, 3] = 255
        sequence.append(image)
    return sequence


def test_a_single_set_is_skipped() -> None:
    """There is nothing cross-set to vary when only one set is given."""
    finding = check_scale([sprite_set(8)])

    assert finding.status is Status.SKIPPED
    assert finding.reason


def test_two_sets_on_one_height_are_clean() -> None:
    finding = check_scale([sprite_set(8), sprite_set(8)])

    assert finding.status is Status.OK
    assert finding.measurement["variation_px"] == 0.0
    assert finding.measurement["heights"] == [8, 8]
    assert finding.measurement["sets"] == 2


def test_the_two_pixel_gap_is_the_defect_and_names_normalise() -> None:
    """The sprite that grows two pixels when it starts walking — the gate's reason to exist."""
    finding = check_scale([sprite_set(4), sprite_set(6)])

    assert finding.status is Status.DEFECT
    assert finding.measurement["variation_px"] == 2.0
    assert finding.fix == "ssc tool normalise"


def test_a_one_pixel_gap_is_within_noise() -> None:
    """One pixel sits at the nearest-neighbour resampler's own ±1 rounding floor, so it is
    not a variation `tool normalise` can be asked to remove — the same line `drift` draws."""
    finding = check_scale([sprite_set(5), sprite_set(6)])

    assert finding.status is Status.OK
    assert finding.measurement["variation_px"] == 1.0


def test_a_blank_set_is_not_averaged_into_the_variation() -> None:
    """A blank set has no visible height; it is excluded rather than dragging the min to zero
    and reporting every other set as maximally varied."""
    blank = [np.zeros((16, 16, 4), dtype=np.uint8) for _ in range(2)]
    finding = check_scale([sprite_set(8), blank])

    # Only one set has a height, so there is nothing to compare — skipped, not a defect.
    assert finding.status is Status.SKIPPED
    assert finding.reason


def test_three_sets_vary_by_their_range() -> None:
    """Heights 4, 5, 6 vary by 2 — the range, not the gap between neighbours."""
    finding = check_scale([sprite_set(4), sprite_set(5), sprite_set(6)])

    assert finding.status is Status.DEFECT
    assert finding.measurement["variation_px"] == 2.0
    assert finding.measurement["sets"] == 3
