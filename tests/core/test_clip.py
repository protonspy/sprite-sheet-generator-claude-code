"""Where a cycle closes, and which frames to take — specs/clip-sampling R2, R3."""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.clip import closes_at, positions


def frame(shade: int, size: int = 8) -> np.ndarray:
    """One opaque frame of a single colour, which is enough to be near or far from another."""
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[..., :3] = shade
    image[..., 3] = 255
    return image


def walk(length: int, cycle: int) -> list[np.ndarray]:
    """A clip whose motion repeats every `cycle` frames — the shape of a walk."""
    return [frame(10 + (index % cycle) * 20) for index in range(length)]


# R2.1 — the frame the motion returns to its first at.


def test_a_clip_that_repeats_closes_where_it_repeats() -> None:
    assert closes_at(walk(24, 8)) == 8


def test_the_cycle_is_the_first_return_and_not_a_later_one() -> None:
    """A four-second clip holds the cycle three times over; the sheet wants one of them."""
    assert closes_at(walk(30, 10)) == 10


def test_a_clip_that_is_exactly_one_cycle_closes_at_its_end() -> None:
    """Nothing after the last frame returns to the first, so the whole clip is the cycle."""
    frames = walk(9, 8)

    assert closes_at(frames) == 8


# R2.2 — a cycle is not two frames.


def test_the_frame_after_the_first_is_never_the_close() -> None:
    """Frame 1 is always near frame 0. Without a floor every clip has a one-frame cycle,
    which is the plausible wrong answer this refuses to give."""
    barely = [frame(10), frame(11), frame(12), frame(200), frame(201), frame(10)]

    assert closes_at(barely) == 5


# R2.3 — a clip that does not loop.


def test_a_clip_that_never_returns_reports_none() -> None:
    """A death animation, or a model that drifted. The nearest frame to the first is still
    far from it, and guessing a cycle here would cut the motion at a meaningless place."""
    drifting = [frame(10 + index * 20) for index in range(12)]

    assert closes_at(drifting) is None


def test_a_clip_too_short_to_hold_a_cycle_reports_none() -> None:
    assert closes_at([frame(10), frame(90)]) is None


def test_frames_of_different_sizes_are_refused() -> None:
    with pytest.raises(ValueError, match="one size"):
        closes_at([frame(10), frame(20), frame(30, size=16), frame(10)])


# R3.1, R3.2 — the positions, and the end that is left out.


def test_positions_are_evenly_spaced_across_the_range() -> None:
    assert positions(4, 12) == [0, 3, 6, 9]


def test_the_end_of_the_range_is_never_taken() -> None:
    """A cycle's closing frame is its opening frame, so a sheet holding both plays the first
    pose twice — a stutter exactly at the loop point, which is where an animation is looked
    at."""
    taken = positions(8, 8)

    assert taken == [0, 1, 2, 3, 4, 5, 6, 7]
    assert 8 not in taken


def test_one_position_is_the_first_frame() -> None:
    assert positions(1, 30) == [0]


def test_every_position_is_inside_the_range_and_in_order() -> None:
    for count, over in ((3, 7), (5, 11), (9, 10), (2, 100)):
        taken = positions(count, over)

        assert len(taken) == count
        assert taken == sorted(set(taken))
        assert all(0 <= index < over for index in taken)


def test_asking_for_more_than_the_range_holds_is_refused() -> None:
    with pytest.raises(ValueError, match="9 frames"):
        positions(10, 9)


@pytest.mark.parametrize("count", [0, -1])
def test_asking_for_no_frames_is_refused(count: int) -> None:
    with pytest.raises(ValueError, match="at least one"):
        positions(count, 10)
