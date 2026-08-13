"""The framing geometry — specs/frame-cropping R1.4, R1.5, R1.7."""

from __future__ import annotations

import pytest

from ssc.core.crop import aspect_rect, inset_rect
from ssc.core.recover import Rect

# R1.4 — the largest rectangle of a stated ratio, positioned by gravity.


def test_a_ratio_the_canvas_already_has_is_the_whole_canvas() -> None:
    assert aspect_rect((16, 16), (1, 1)) == Rect(0, 0, 16, 16)


def test_a_ratio_wider_than_the_canvas_is_limited_by_the_width() -> None:
    """32x32 at 16:9 keeps all 32 columns and gives up rows."""
    fitted = aspect_rect((32, 32), (16, 9))
    assert fitted.width == 32
    assert fitted.height == 18


def test_a_ratio_taller_than_the_canvas_is_limited_by_the_height() -> None:
    fitted = aspect_rect((32, 32), (9, 16))
    assert fitted.height == 32
    assert fitted.width == 18


@pytest.mark.parametrize(
    ("canvas", "ratio"),
    [((32, 32), (16, 9)), ((40, 24), (3, 2)), ((17, 31), (5, 4)), ((7, 7), (1, 3))],
)
def test_the_fitted_rectangle_is_inside_the_canvas_and_maxes_one_side(
    canvas: tuple[int, int], ratio: tuple[int, int]
) -> None:
    """Inside the canvas, or `crop` refuses it; maxing a side, or it is not the largest."""
    fitted = aspect_rect(canvas, ratio)

    assert fitted.x >= 0 and fitted.y >= 0
    assert fitted.right <= canvas[0] and fitted.bottom <= canvas[1]
    assert fitted.width == canvas[0] or fitted.height == canvas[1]


def test_opposite_gravities_land_against_opposite_edges() -> None:
    canvas, ratio = (32, 32), (16, 9)

    assert aspect_rect(canvas, ratio, "top").y == 0
    assert aspect_rect(canvas, ratio, "bottom").bottom == 32
    assert aspect_rect(canvas, ratio, "left").x == 0
    assert aspect_rect(canvas, ratio, "right").right == 32


def test_a_corner_gravity_pins_both_axes() -> None:
    fitted = aspect_rect((40, 40), (2, 1), "bottom-right")

    assert fitted == Rect(0, 20, 40, 20)


def test_centre_splits_what_is_left_over_between_the_two_sides() -> None:
    """The leftover is odd, so the two margins differ by one and neither is the whole of it."""
    fitted = aspect_rect((10, 10), (10, 3))

    assert fitted.height == 3
    assert fitted.y == 3
    assert fitted.bottom == 6


def test_an_axis_the_gravity_does_not_name_is_centred() -> None:
    """`top` says nothing about x, so x is centred — not left by default."""
    fitted = aspect_rect((40, 40), (1, 2), "top")

    assert fitted.y == 0
    assert fitted.x == 10


# R1.7 — a rectangle with no pixels in it is not a crop.


def test_a_ratio_too_extreme_for_the_canvas_is_refused() -> None:
    with pytest.raises(ValueError, match="no pixels"):
        aspect_rect((4, 4), (100, 1))


@pytest.mark.parametrize("ratio", [(0, 1), (1, 0), (-2, 1)])
def test_a_ratio_with_a_side_of_zero_or_less_is_refused(ratio: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="ratio"):
        aspect_rect((16, 16), ratio)


def test_a_gravity_nobody_defined_is_refused() -> None:
    with pytest.raises(ValueError, match="gravity"):
        aspect_rect((16, 16), (1, 1), "sideways")


# R1.5 — the same number off every side, or four numbers clockwise from the top.


def test_one_inset_comes_off_all_four_sides() -> None:
    assert inset_rect((20, 20), (3, 3, 3, 3)) == Rect(3, 3, 14, 14)


def test_four_insets_are_read_clockwise_from_the_top() -> None:
    """Top 1, right 2, bottom 3, left 4 — each side losing its own number and no other."""
    assert inset_rect((20, 20), (1, 2, 3, 4)) == Rect(4, 1, 14, 16)


def test_an_inset_of_nothing_is_the_whole_canvas() -> None:
    assert inset_rect((8, 5), (0, 0, 0, 0)) == Rect(0, 0, 8, 5)


# R1.7 — again, and by the other route into it.


def test_an_inset_that_meets_itself_is_refused() -> None:
    with pytest.raises(ValueError, match="no pixels"):
        inset_rect((10, 10), (5, 0, 5, 0))


def test_an_inset_past_the_far_side_is_refused() -> None:
    with pytest.raises(ValueError, match="no pixels"):
        inset_rect((10, 10), (0, 12, 0, 0))


def test_a_negative_inset_is_refused_rather_than_padding() -> None:
    with pytest.raises(ValueError, match="padding is tool expand"):
        inset_rect((10, 10), (-2, 0, 0, 0))
