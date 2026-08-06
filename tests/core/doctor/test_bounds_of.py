"""`bounds_of` — the one measurement the normaliser, the `scale` check and the per-frame
box read (plan `sprite-normalisation-gate` 3.1).
"""

from __future__ import annotations

import numpy as np

from ssc.core.doctor.masks import bounds_of, summarise_bounds


def frame(rows: int, cols: int, sprite: tuple[int, int, int, int]) -> np.ndarray:
    """An `rows`x`cols` RGBA canvas, transparent everywhere except the sprite box.

    `sprite` is `(y, x, height, width)`: the top-left of a fully opaque rectangle.
    """
    image = np.zeros((rows, cols, 4), dtype=np.uint8)
    y, x, height, width = sprite
    image[y : y + height, x : x + width] = (0, 0, 0, 255)
    return image


def test_the_alpha_box_not_the_canvas() -> None:
    """Visible height and width are the alpha bounding box, never the canvas."""
    box = bounds_of(frame(10, 10, (2, 3, 4, 5)))
    assert box is not None
    assert box.x == 3
    assert box.y == 2
    assert box.width == 5
    assert box.height == 4


def test_the_baseline_is_the_lowest_occupied_row() -> None:
    """The canvas row the feet land on — the anchor's row, the thing that agrees between
    two animations or the feet drift through the floor."""
    box = bounds_of(frame(10, 10, (2, 3, 4, 5)))
    assert box is not None
    assert box.baseline == 5  # rows 2..5 inclusive


def test_the_centre_is_the_body_in_the_baseline_row() -> None:
    """The same number `anchor` returns, so the normaliser reads one implementation."""
    box = bounds_of(frame(10, 10, (2, 3, 4, 5)))
    assert box is not None
    # The baseline row (5) is occupied across cols 3..7, so the centre is their midpoint.
    assert box.centre == 5.0


def test_a_frame_with_no_coverage_has_no_bounds() -> None:
    """The one `align` reports as `empty`; the normaliser refuses to guess a position for
    it rather than averaging a zero frame into a set's baseline."""
    empty = np.zeros((8, 8, 4), dtype=np.uint8)
    assert bounds_of(empty) is None


def test_a_frame_with_no_alpha_is_wholly_opaque() -> None:
    """An RGB frame has no alpha channel, so the whole canvas is the body — the baseline
    is the bottom row and the centre is the canvas's horizontal midpoint."""
    rgb = np.full((6, 8, 3), 200, dtype=np.uint8)
    box = bounds_of(rgb)
    assert box is not None
    assert box.x == 0
    assert box.y == 0
    assert box.width == 8
    assert box.height == 6
    assert box.baseline == 5
    assert box.centre == 3.5  # (0 + 7) / 2


def test_the_set_summary_is_a_median_with_a_spread() -> None:
    """Per set, each measurement as a median and a range — the representative value the
    cross-set check compares, and the within-set jitter it has to be larger than."""
    # Three frames whose visible heights are 4, 6, 5 — median 5, spread 2.
    boxes = [
        bounds_of(frame(10, 10, (0, 0, 4, 4))),
        bounds_of(frame(10, 10, (0, 0, 6, 4))),
        bounds_of(frame(10, 10, (0, 0, 5, 4))),
    ]
    summary = summarise_bounds(boxes)
    assert summary["height"]["median"] == 5.0
    assert summary["height"]["spread"] == 2.0
    # Every measurement is summarised, not just height.
    assert set(summary) == {"x", "y", "width", "height", "baseline", "centre"}


def test_blank_frames_are_excluded_from_the_set_summary() -> None:
    """A blank frame is not a measurement of the sprite's position; including a zero
    would move the median off the sprite."""
    boxes = [
        bounds_of(frame(10, 10, (2, 3, 4, 5))),
        None,
        bounds_of(frame(10, 10, (2, 3, 4, 5))),
    ]
    summary = summarise_bounds(boxes)
    # Two identical frames: median is their value, spread is zero.
    assert summary["height"]["median"] == 4.0
    assert summary["height"]["spread"] == 0.0


def test_a_set_where_every_frame_is_blank_reports_nothing() -> None:
    """A missing field reads as 'no measurement', not as a zero a caller mistakes for a
    sprite at the origin."""
    assert summarise_bounds([None, None]) == {}
