"""Finding the pieces — specs/frame-recovery R1."""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.bgremove import PRESETS
from ssc.core.recover import (
    Rect,
    bounds_of,
    chroma_rects,
    crop,
    grid_rects,
    in_reading_order,
    island_rects,
    keep,
)

GREEN = PRESETS["green"]


def sheet(width: int = 12, height: int = 12) -> np.ndarray:
    """A transparent sheet with nothing on it yet."""
    return np.zeros((height, width, 4), dtype=np.uint8)


def blob(image: np.ndarray, rect: Rect, colour: tuple[int, int, int] = (200, 30, 30)) -> None:
    image[rect.y : rect.bottom, rect.x : rect.right, :3] = colour
    image[rect.y : rect.bottom, rect.x : rect.right, 3] = 255


# R1.1, R1.8 — a stated grid.


def test_a_grid_cuts_into_equal_cells_in_reading_order() -> None:
    rects = grid_rects(12, 8, columns=3, rows=2)
    assert len(rects) == 6
    assert rects[0] == Rect(0, 0, 4, 4)
    assert rects[1] == Rect(4, 0, 4, 4)
    assert rects[3] == Rect(0, 4, 4, 4)


def test_a_grid_with_margin_and_spacing_excludes_both() -> None:
    rects = grid_rects(20, 12, columns=2, rows=1, margin=(2, 2), spacing=(4, 0))
    assert rects[0] == Rect(2, 2, 6, 8)
    assert rects[1] == Rect(12, 2, 6, 8)


def test_a_size_that_does_not_divide_leaves_the_remainder_at_the_edge() -> None:
    """One cell short by a pixel beats every cell short by a fraction of one."""
    rects = grid_rects(10, 4, columns=3, rows=1)
    assert [rect.width for rect in rects] == [3, 3, 3]
    assert rects[-1].right == 9


@pytest.mark.parametrize(("columns", "rows"), [(0, 1), (1, 0), (-1, 2)])
def test_a_grid_of_no_cells_is_refused(columns: int, rows: int) -> None:
    with pytest.raises(ValueError, match="at least one cell"):
        grid_rects(8, 8, columns, rows)


def test_a_grid_that_does_not_fit_is_refused() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        grid_rects(4, 4, columns=8, rows=8)


# R1.4, R1.5 — the two detectors that find content rather than being told where it is.


def test_islands_finds_each_opaque_region() -> None:
    image = sheet()
    blob(image, Rect(1, 1, 3, 3))
    blob(image, Rect(7, 6, 4, 2))

    found = in_reading_order(island_rects(image))
    assert found == [Rect(1, 1, 3, 3), Rect(7, 6, 4, 2)]


def test_islands_does_not_join_two_shapes_touching_at_a_corner() -> None:
    """4-connected, because in pixel art a diagonal is a deliberate step and not a join."""
    image = sheet()
    blob(image, Rect(1, 1, 2, 2))
    blob(image, Rect(3, 3, 2, 2))
    assert len(island_rects(image)) == 2


def test_chroma_finds_each_region_that_is_not_the_key() -> None:
    image = sheet()
    image[..., :3] = GREEN
    image[..., 3] = 255
    blob(image, Rect(1, 1, 3, 3))
    blob(image, Rect(6, 6, 3, 3))

    found = in_reading_order(chroma_rects(image, GREEN, tolerance=10))
    assert found == [Rect(1, 1, 3, 3), Rect(6, 6, 3, 3)]


def test_chroma_and_islands_agree_on_a_sheet_that_has_both() -> None:
    """The pipeline runs `bgremove` before this, so a sheet often has transparent gutters
    *and* a key colour. The two detectors must not disagree about where the pieces are."""
    image = sheet()
    image[..., :3] = GREEN
    image[..., 3] = 255
    blob(image, Rect(2, 2, 4, 4))

    by_chroma = in_reading_order(chroma_rects(image, GREEN, tolerance=10))
    image[image[..., 1] == GREEN[1], 3] = 0
    by_island = in_reading_order(island_rects(image))
    assert by_chroma == by_island


def test_an_empty_sheet_yields_no_pieces() -> None:
    assert island_rects(sheet()) == []


# R1.6, R1.7 — what is not a piece.


def test_a_piece_below_min_size_is_dropped() -> None:
    rects = [Rect(0, 0, 8, 8), Rect(0, 0, 2, 8)]
    assert keep(rects, min_size=4) == [Rect(0, 0, 8, 8)]


def test_min_size_measures_the_shorter_side() -> None:
    assert keep([Rect(0, 0, 100, 2)], min_size=4) == []


def test_a_piece_past_max_aspect_is_dropped() -> None:
    """A one-pixel rule between rows is an island, and a very wide one."""
    rects = [Rect(0, 0, 8, 8), Rect(0, 0, 40, 2)]
    assert keep(rects, max_aspect=3.0) == [Rect(0, 0, 8, 8)]


def test_max_aspect_is_symmetric_in_the_two_directions() -> None:
    assert keep([Rect(0, 0, 2, 40)], max_aspect=3.0) == []


def test_no_filter_keeps_everything() -> None:
    rects = [Rect(0, 0, 1, 99), Rect(0, 0, 1, 1)]
    assert keep(rects) == rects


# R1.8 — reading order, on pieces that do not line up.


def test_pieces_on_one_row_are_ordered_left_to_right_even_when_they_do_not_align() -> None:
    """A crouching pose starts lower than a standing one; sorting on `y` alone would
    interleave two rows into an order nobody would call reading order."""
    standing = Rect(10, 0, 4, 8)
    crouching = Rect(2, 3, 4, 5)
    next_row = Rect(2, 20, 4, 4)

    assert in_reading_order([next_row, standing, crouching]) == [crouching, standing, next_row]


def test_reading_order_of_nothing_is_nothing() -> None:
    assert in_reading_order([]) == []


def test_crop_takes_exactly_the_rectangle() -> None:
    image = sheet()
    blob(image, Rect(2, 3, 4, 5))
    piece = crop(image, Rect(2, 3, 4, 5))
    assert piece.shape == (5, 4, 4)
    assert (piece[..., 3] == 255).all()


# R1.9 — a mask with a component per pixel is not a sheet.


def test_bounds_are_taken_in_one_pass_not_one_per_label() -> None:
    """A per-label `np.nonzero` scan is O(pixels x components), and a dithered alpha gives
    one component per pixel — which `bgremove`'s own edge can produce. `region_areas` one
    file over already solved this shape with a single pass; so does this."""
    mask = np.zeros((100, 100), dtype=bool)
    mask[::2, ::2] = True
    found = bounds_of(mask)
    assert len(found) == 2500
    assert all(rect.width == 1 and rect.height == 1 for rect in found)


def test_a_mask_past_the_piece_ceiling_is_refused() -> None:
    mask = np.zeros((200, 200), dtype=bool)
    mask[::2, ::2] = True
    with pytest.raises(ValueError, match="does not look like a sheet"):
        bounds_of(mask)


def test_bounds_of_nothing_is_nothing() -> None:
    assert bounds_of(np.zeros((8, 8), dtype=bool)) == []


def test_a_tall_piece_does_not_bridge_two_rows_into_one() -> None:
    """Banding on the running maximum of a band's bottoms is transitive: one tall piece in
    the middle joins two rows that never overlap each other. Pieces of differing sizes are
    the normal case for the islands and chroma modes, so this is not a corner."""
    first = Rect(0, 0, 6, 10)
    tall = Rect(20, 8, 6, 32)
    third = Rect(0, 30, 6, 15)

    assert in_reading_order([third, tall, first]) == [first, tall, third]
