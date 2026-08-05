"""Pose tracking through a cycle, reported per frame — plan task 10.1.

The model is injected: `track` holds the report and never the import, so a test hands it a
callable returning a known skeleton and the runtime's weight-loading path is exercised
elsewhere (or not at all — the extra is optional by design, as it is for `bgremove`).
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.posetrack import KEYPOINT_COUNT, KEYPOINT_NAMES, MIN_SCORE, track


def frame(width: int = 8, height: int = 8) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., 3] = 255
    return image


def a_pose(visible: int = KEYPOINT_COUNT, score: float = 0.9) -> np.ndarray:
    """A (17, 3) skeleton with `visible` landmarks present and the rest below threshold."""
    keypoints = np.zeros((KEYPOINT_COUNT, 3), dtype=np.float32)
    keypoints[:, 0] = np.arange(KEYPOINT_COUNT, dtype=np.float32)  # x
    keypoints[:, 1] = 1.0  # y
    keypoints[:, 2] = score
    if visible < KEYPOINT_COUNT:
        keypoints[visible:, 2] = 0.0  # below MIN_SCORE, so absent
    return keypoints


def test_one_pose_per_frame_with_the_visible_counted() -> None:
    model = lambda image: a_pose(visible=12)  # noqa: E731

    result = track([frame(), frame(), frame()], model)

    assert len(result.frames) == 3
    assert all(pose.visible == 12 for pose in result.frames)
    assert result.measurement["frames"] == 3
    assert result.measurement["landmarks"] == KEYPOINT_COUNT
    assert result.measurement["visible_mean"] == 12.0


def test_a_landmark_below_min_score_is_absent() -> None:
    keypoints = a_pose()
    keypoints[0, 2] = MIN_SCORE - 0.01  # nose just below threshold

    result = track([frame()], lambda image: keypoints)

    assert result.frames[0].visible == KEYPOINT_COUNT - 1


def test_the_report_carries_one_named_landmark_per_index() -> None:
    result = track([frame()], lambda image: a_pose(visible=3))

    row = result.frames[0].as_dict()
    assert row["visible"] == 3
    assert [landmark["name"] for landmark in row["landmarks"]] == list(KEYPOINT_NAMES)
    # The first three are present; the rest score below MIN_SCORE and stay in the row as
    # absent rather than being dropped — a per-frame report with a missing landmark reads
    # as "not detected", one with a missing entry reads as "not tracked".
    assert row["landmarks"][0]["score"] >= MIN_SCORE
    assert row["landmarks"][-1]["score"] < MIN_SCORE


def test_a_model_returning_the_wrong_shape_is_refused() -> None:
    with pytest.raises(ValueError):
        track([frame()], lambda image: np.zeros((7, 3), dtype=np.float32))


def test_scores_outside_zero_to_one_are_clipped_for_the_mean() -> None:
    """A model that over-shoots does not move the mean by more than it should: scores outside
    0..1 are excluded from `score_mean` rather than dragging it past 1.0."""
    keypoints = a_pose()
    keypoints[0, 2] = 5.0  # out of range, dropped from the mean

    result = track([frame()], lambda image: keypoints)

    # The 16 in-range scores are all 0.9; the out-of-range one is excluded, not
    # clipped — clipping it to 1.0 would land at ~0.906, so the exact value pins
    # the exclusion.
    assert result.measurement["score_mean"] == pytest.approx(0.9)
