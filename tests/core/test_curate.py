"""Redundant frames — specs/frame-recovery R4.2, R4.4."""

from __future__ import annotations

import numpy as np

from ssc.core.curate import differences, distance, kept


def frame(fill: int, size: int = 8) -> np.ndarray:
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[..., :3] = fill
    image[..., 3] = 255
    return image


def test_a_frame_is_zero_away_from_itself() -> None:
    assert distance(frame(10), frame(10)) == 0.0


def test_a_wholly_different_frame_is_one_away() -> None:
    assert distance(frame(10), frame(200)) == 1.0


def test_distance_is_a_share_so_one_threshold_fits_every_size() -> None:
    small, large = frame(0, size=4), frame(0, size=64)
    small[0, 0] = (255, 255, 255, 255)
    large[0, 0] = (255, 255, 255, 255)
    assert distance(frame(0, 4), small) > distance(frame(0, 64), large)


def test_frames_of_different_sizes_are_entirely_different() -> None:
    """Resampling one to compare them would be inventing the answer."""
    assert distance(frame(10, size=8), frame(10, size=16)) == 1.0


def test_the_first_frame_is_never_redundant() -> None:
    found = differences([frame(10), frame(10), frame(10)], threshold=0.5)
    assert found[0].redundant is False
    assert found[1].redundant is True


def test_a_frame_that_moved_enough_is_kept() -> None:
    assert kept([frame(10), frame(200)], threshold=0.5) == [0, 1]


def test_an_identical_frame_is_dropped() -> None:
    assert kept([frame(10), frame(10), frame(200)], threshold=0.5) == [0, 2]


def test_a_slow_pan_is_not_dropped_entirely() -> None:
    """Compared against the last frame *kept*, not the immediate predecessor: a pan that
    moves a little per frame moves a lot over five, and comparing neighbours would call
    every frame redundant and drop the whole movement."""
    frames = []
    for step in range(6):
        image = np.zeros((10, 10, 4), dtype=np.uint8)
        image[:, step : step + 4, 3] = 255
        frames.append(image)

    surviving = kept(frames, threshold=0.25)
    assert len(surviving) > 2
    assert surviving[0] == 0


def test_a_threshold_of_zero_keeps_everything() -> None:
    assert kept([frame(10), frame(10)], threshold=0.0) == [0, 1]


def test_one_frame_is_kept() -> None:
    assert kept([frame(10)], threshold=0.9) == [0]


def test_no_frames_is_no_frames() -> None:
    assert kept([], threshold=0.5) == []
