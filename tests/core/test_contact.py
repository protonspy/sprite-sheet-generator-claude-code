"""The contact sheet layout — specs/sweep-and-review R3.1, R3.3, R3.5.

The geometry is what these assert. The whole reason this is TDD rather than Unit is in
`design.md`: the contact sheet is the one artefact with no measurement behind it, so a
layout that is quietly wrong produces a green sweep and a bad human decision.
"""

from __future__ import annotations

import numpy as np

from ssc.core.contact import Cell, ContactParams, cell_for, draw_labels, sheet


def block(width: int, height: int, colour: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., :3] = colour
    image[..., 3] = 255
    return image


def test_one_cell_holds_its_image_at_its_own_size() -> None:
    art = block(8, 6, (200, 30, 30))
    params = ContactParams(columns=1, padding=2, label_height=4)
    made = sheet([Cell(art, "0")], params)

    assert made.shape == (6 + 2 * 2 + 4, 8 + 2 * 2, 4)
    # R3.3 — byte-identical, which is the property "resampling nothing" actually means.
    assert np.array_equal(made[2:8, 2:10], art)


def test_the_grid_places_cells_left_to_right_then_down() -> None:
    red, green = block(4, 4, (255, 0, 0)), block(4, 4, (0, 255, 0))
    blue = block(4, 4, (0, 0, 255))
    params = ContactParams(columns=2, padding=0, label_height=0)
    made = sheet([Cell(red, "0"), Cell(green, "1"), Cell(blue, "2")], params)

    assert made.shape == (8, 8, 4)
    assert np.array_equal(made[0:4, 0:4], red)
    assert np.array_equal(made[0:4, 4:8], green)
    assert np.array_equal(made[4:8, 0:4], blue)


def test_cells_are_sized_by_the_largest_variant_and_nothing_is_scaled() -> None:
    small, large = block(4, 4, (255, 0, 0)), block(10, 8, (0, 255, 0))
    params = ContactParams(columns=2, padding=0, label_height=0)
    made = sheet([Cell(small, "0"), Cell(large, "1")], params)

    assert made.shape == (8, 20, 4)
    # The small one keeps its own 4x4 and is not stretched into the 10x8 cell.
    assert np.array_equal(made[0:4, 0:4], small)
    assert np.array_equal(made[0:8, 10:20], large)


def test_the_space_a_smaller_variant_does_not_fill_is_background() -> None:
    small, large = block(4, 4, (255, 0, 0)), block(8, 8, (0, 255, 0))
    params = ContactParams(columns=2, padding=0, label_height=0, background=(1, 2, 3, 255))
    made = sheet([Cell(small, "0"), Cell(large, "1")], params)

    assert tuple(made[7, 7]) == (1, 2, 3, 255)


# R3.5 — a variant that failed.
def test_a_failed_variant_leaves_its_cell_empty() -> None:
    art = block(4, 4, (255, 0, 0))
    params = ContactParams(columns=2, padding=0, label_height=0, background=(9, 9, 9, 255))
    made = sheet([Cell(art, "0"), Cell(None, "1 failed")], params)

    assert made.shape == (4, 8, 4)
    assert np.array_equal(made[0:4, 0:4], art)
    assert np.all(made[0:4, 4:8] == np.array([9, 9, 9, 255], dtype=np.uint8))


def test_every_variant_failing_still_produces_a_sheet() -> None:
    params = ContactParams(columns=2, padding=0, label_height=0)
    made = sheet([Cell(None, "0 failed"), Cell(None, "1 failed")], params)
    assert made.ndim == 3
    assert made.shape[0] > 0 and made.shape[1] > 0


def test_columns_default_to_something_near_square() -> None:
    cells = [Cell(block(4, 4, (255, 0, 0)), str(index)) for index in range(9)]
    made = sheet(cells, ContactParams(padding=0, label_height=0))
    assert made.shape == (12, 12, 4)


def test_a_row_that_is_not_full_still_gets_a_full_canvas() -> None:
    cells = [Cell(block(4, 4, (255, 0, 0)), str(index)) for index in range(3)]
    made = sheet(cells, ContactParams(columns=2, padding=0, label_height=0))
    # Two rows, the second holding one cell and one cell's worth of background.
    assert made.shape == (8, 8, 4)


def test_padding_surrounds_every_cell() -> None:
    art = block(4, 4, (255, 0, 0))
    params = ContactParams(columns=1, padding=3, label_height=0, background=(0, 0, 0, 255))
    made = sheet([Cell(art, "0")], params)

    assert made.shape == (10, 10, 4)
    assert np.array_equal(made[3:7, 3:7], art)
    assert tuple(made[0, 0]) == (0, 0, 0, 255)


def test_the_label_strip_is_reserved_below_the_art() -> None:
    art = block(4, 4, (255, 0, 0))
    params = ContactParams(columns=1, padding=0, label_height=5)
    made = sheet([Cell(art, "0")], params)

    assert made.shape == (9, 4, 4)
    assert np.array_equal(made[0:4, 0:4], art)


# R3.2 — the labels.
def test_a_label_marks_its_own_strip_and_leaves_the_art_alone() -> None:
    art = block(40, 8, (255, 0, 0))
    params = ContactParams(columns=1, padding=0, label_height=12)
    made = draw_labels(sheet([Cell(art, "0 tol-60")], params), [Cell(art, "0 tol-60")], params)

    # The art is untouched...
    assert np.array_equal(made[0:8, 0:40], art)
    # ...and something was written in the strip below it.
    assert not np.all(made[8:20, 0:40] == np.array(params.background, dtype=np.uint8))


def test_labels_do_not_mutate_the_canvas_they_were_given() -> None:
    art = block(40, 8, (255, 0, 0))
    params = ContactParams(columns=1, padding=0, label_height=12)
    cells = [Cell(art, "0 tol-60")]
    canvas = sheet(cells, params)
    before = canvas.copy()
    draw_labels(canvas, cells, params)
    assert np.array_equal(canvas, before)


def test_a_failed_cell_still_gets_its_label() -> None:
    art = block(40, 8, (255, 0, 0))
    params = ContactParams(columns=2, padding=0, label_height=12)
    cells = [Cell(art, "0 ok"), Cell(None, "1 failed")]
    made = draw_labels(sheet(cells, params), cells, params)
    assert not np.all(made[8:20, 40:80] == np.array(params.background, dtype=np.uint8))


def test_no_label_strip_means_nothing_is_drawn() -> None:
    art = block(8, 8, (255, 0, 0))
    params = ContactParams(columns=1, padding=0, label_height=0)
    cells = [Cell(art, "0")]
    assert np.array_equal(draw_labels(sheet(cells, params), cells, params), sheet(cells, params))


# R3.4 — a variant's first frame is what the sheet shows.
def test_a_multi_frame_variant_shows_its_first_frame() -> None:
    first, second = block(4, 4, (255, 0, 0)), block(4, 4, (0, 255, 0))
    assert np.array_equal(cell_for([first, second], "0").image, first)


def test_a_variant_that_produced_no_frames_has_no_image() -> None:
    assert cell_for([], "0 failed").image is None
