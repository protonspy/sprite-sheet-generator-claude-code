"""R2.10 — the consistency embedding, against arrays whose defect is known by construction.

The number is a mean cosine similarity over reduced shape vectors, so the cases that pin it
are the simple ones: identical frames score 1.0, disjoint silhouettes score 0.0, and a
threshold turns the number into a defect only where a project gave one.
"""

from __future__ import annotations

import numpy as np

from ssc.core.doctor import ConsistencyParams, Status, check_consistency


def blob(width: int, height: int, x0: int, y0: int, w: int, h: int) -> np.ndarray:
    """An RGBA frame with one opaque rectangle at `(x0, y0)`, transparent elsewhere."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[y0 : y0 + h, x0 : x0 + w, :3] = 200
    image[y0 : y0 + h, x0 : x0 + w, 3] = 255
    return image


def test_identical_frames_are_perfectly_consistent() -> None:
    frame = blob(16, 16, 4, 4, 8, 8)

    finding = check_consistency([frame, frame, frame])

    assert finding.status is Status.OK
    assert finding.measurement["consistency"] == 1.0
    assert finding.measurement["frames"] == 3


def test_disjoint_silhouettes_score_below_one() -> None:
    left = blob(16, 16, 0, 0, 8, 8)
    right = blob(16, 16, 8, 8, 8, 8)

    finding = check_consistency([left, right])

    assert finding.measurement["consistency"] < 1.0
    # Disjoint masks share no opaque cell once reduced, so the cosine is zero.
    assert finding.measurement["consistency"] == 0.0


def test_a_single_frame_is_skipped() -> None:
    finding = check_consistency([blob(16, 16, 4, 4, 8, 8)])

    assert finding.status is Status.SKIPPED
    assert finding.reason


def test_without_a_threshold_a_low_score_is_still_ok() -> None:
    """A walk cycle is meant to differ, so the number is reported, not graded, by default."""
    left = blob(16, 16, 0, 0, 8, 8)
    right = blob(16, 16, 8, 8, 8, 8)

    finding = check_consistency([left, right])

    assert finding.status is Status.OK
    assert finding.measurement["consistency"] == 0.0


def test_a_threshold_below_the_score_is_a_defect_that_names_a_fix() -> None:
    left = blob(16, 16, 0, 0, 8, 8)
    right = blob(16, 16, 8, 8, 8, 8)

    finding = check_consistency([left, right], ConsistencyParams(min_consistency=0.5))

    assert finding.status is Status.DEFECT
    assert finding.measurement["min_consistency"] == 0.5
    assert finding.fix == "ssc tool align --anchor feet"


def test_a_threshold_above_the_score_stays_ok() -> None:
    frame = blob(16, 16, 4, 4, 8, 8)

    finding = check_consistency([frame, frame], ConsistencyParams(min_consistency=0.5))

    assert finding.status is Status.OK
    assert finding.measurement["consistency"] == 1.0


def test_frames_without_alpha_fall_back_to_a_luminance_shape() -> None:
    """A sheet with a chroma background has no alpha, so the embedding uses luminance."""
    left = np.zeros((16, 16, 3), dtype=np.uint8)
    left[0:8, 0:8] = 200
    right = np.zeros((16, 16, 3), dtype=np.uint8)
    right[8:16, 8:16] = 200

    finding = check_consistency([left, right])

    assert finding.status is Status.OK
    assert finding.measurement["consistency"] < 1.0
