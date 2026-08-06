"""The frame order a playback mode implies — specs/engine-index R6.1, R6.4.

Written before `core/preview.py` existed, and watched fail. It is TDD because it is the one
piece of arithmetic every consumer of the index shares: `ssc preview` renders through it and
the Pixi and Godot emitters bake it into their frame lists, since neither format can express
a mode. `ping-pong` over four frames is six frames, not eight, and an engine handed the wrong
one does not complain — it stutters at the ends, and only a person watching notices.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core import preview


def test_loop_is_the_frames_in_order() -> None:
    assert preview.order(4, "loop") == [0, 1, 2, 3]


def test_reverse_is_the_frames_backwards() -> None:
    assert preview.order(4, "reverse") == [3, 2, 1, 0]


def test_ping_pong_does_not_repeat_either_end() -> None:
    # Six, not eight: playing 3 twice at the turn is the stutter, and so is playing 0 twice
    # when the loop comes round.
    assert preview.order(4, "ping-pong") == [0, 1, 2, 3, 2, 1]


def test_ping_pong_over_two_frames_is_just_the_two() -> None:
    assert preview.order(2, "ping-pong") == [0, 1]


@pytest.mark.parametrize("mode", ["loop", "reverse", "ping-pong"])
def test_a_single_frame_is_itself_whatever_the_mode(mode: str) -> None:
    assert preview.order(1, mode) == [0]


@pytest.mark.parametrize("mode", ["loop", "reverse", "ping-pong"])
def test_no_frames_is_no_order(mode: str) -> None:
    assert preview.order(0, mode) == []


# R6.4 — a section is a range of the same set, and the mode applies inside it.


def test_a_section_is_the_frames_it_covers() -> None:
    assert preview.order(8, "loop", section=(3, 5)) == [3, 4, 5]


def test_a_section_played_backwards() -> None:
    assert preview.order(8, "reverse", section=(3, 5)) == [5, 4, 3]


def test_a_section_ping_ponged_within_itself() -> None:
    assert preview.order(8, "ping-pong", section=(2, 5)) == [2, 3, 4, 5, 4, 3]


def test_a_section_of_one_frame() -> None:
    assert preview.order(8, "loop", section=(4, 4)) == [4]


def test_a_mode_nobody_defined_is_refused() -> None:
    with pytest.raises(ValueError, match="bounce"):
        preview.order(4, "bounce")


def test_a_section_outside_the_set_is_refused() -> None:
    # `cli/index.py` refuses this earlier with a message naming the section; core refuses it
    # too, because a pure function that trusts its caller is a pure function with a hole.
    with pytest.raises(ValueError):
        preview.order(4, "loop", section=(2, 9))


# `frames_from_sheet` — cutting a sheet by its grid (frame-preview R1.2, R1.4).


def sheet(columns: int, rows: int, cell: tuple[int, int]) -> np.ndarray:
    """A sheet of `columns`x`rows` cells, each cell a solid colour keyed by its frame index.

    Each frame a different shade so a cut that picked the wrong cell is visible in the pixels
    rather than only in the count.
    """
    width, height = cell
    image = np.zeros((rows * height, columns * width, 4), dtype=np.uint8)
    for number in range(columns * rows):
        row, column = divmod(number, columns)
        image[row * height : (row + 1) * height, column * width : (column + 1) * width] = (
            number * 10,
            0,
            0,
            255,
        )
    return image


def test_a_sheet_is_cut_into_its_frames_in_grid_order() -> None:
    cut = preview.frames_from_sheet(sheet(3, 2, (4, 4)), (4, 4), 3, 2, 6)

    assert len(cut) == 6
    # Frame 0 is the top-left cell; frame 1 the next to its right; frame 3 wraps to row 1.
    assert cut[0][0, 0, 0] == 0
    assert cut[1][0, 0, 0] == 10
    assert cut[3][0, 0, 0] == 30


def test_a_frame_count_below_the_grid_cuts_only_that_many() -> None:
    """Trailing cells may be padding; `--frames` says how many are real."""
    cut = preview.frames_from_sheet(sheet(3, 2, (4, 4)), (4, 4), 3, 2, 4)

    assert len(cut) == 4


def test_a_grid_the_sheet_cannot_hold_is_refused() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        preview.frames_from_sheet(sheet(2, 2, (4, 4)), (8, 8), 2, 2, 4)


def test_a_frame_count_the_grid_cannot_hold_is_refused() -> None:
    with pytest.raises(ValueError, match="do not fit"):
        preview.frames_from_sheet(sheet(2, 2, (4, 4)), (4, 4), 2, 2, 9)
