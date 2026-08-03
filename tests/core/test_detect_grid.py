"""Detecting a grid — specs/frame-recovery R1.2, R1.3, R2.

Written before the code (TDD). The failure mode is what makes it TDD: a detector that
returns a *plausible wrong* grid cuts the sheet into frames that are each off by a few
pixels, and nothing downstream notices — `doctor`'s `check_bleed` takes the grid as a
parameter and would happily measure against the same wrong number.

So the assertions are about the layout that was actually drawn, not about whatever the
implementation finds convenient, and R1.3 — refusing rather than guessing — gets as much
attention as the successful cases.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.recover import detect_grid


def drawn(
    columns: int,
    rows: int,
    cell: int,
    *,
    margin: int = 0,
    spacing: int = 0,
) -> np.ndarray:
    """A sheet with an opaque block in every cell of a known layout."""
    width = 2 * margin + columns * cell + spacing * (columns - 1)
    height = 2 * margin + rows * cell + spacing * (rows - 1)
    image = np.zeros((height, width, 4), dtype=np.uint8)
    for row in range(rows):
        for column in range(columns):
            x = margin + column * (cell + spacing)
            y = margin + row * (cell + spacing)
            # Inset by a pixel, so the content does not itself touch the cell boundary —
            # a real sprite does not fill its cell to the edge.
            image[y + 1 : y + cell - 1, x + 1 : x + cell - 1, 3] = 255
    return image


def test_a_spaced_grid_is_detected_as_what_can_be_seen_of_it() -> None:
    """Writing this first is what showed the original assertion was undetectable.

    A sprite does not fill its cell, so a 10px cell with a 4px gutter and a 1px inset
    presents as a run of 8 and a gap of 6. Nothing in the image distinguishes that from an
    8px cell with a 6px gutter — the boundary is not observable where no content touches
    it. So the contract is the observable one: cells tight to content, spacing measured.
    """
    found = detect_grid(drawn(3, 2, cell=10, spacing=4))
    assert found is not None
    summary = (found.columns, found.rows, found.cell, found.margin, found.spacing)
    assert summary == (3, 2, (8, 8), (1, 1), (6, 6))
    # And the bands the cutting actually uses, which are where the content is rather than
    # a position re-derived from those three scalars.
    assert found.columns_at == ((1, 8), (15, 8), (29, 8))


def test_what_is_detected_tiles_back_to_the_pitch_that_was_drawn() -> None:
    """The invariant that survives the ambiguity: cell plus spacing is the pitch, whatever
    the split between them turns out to be."""
    found = detect_grid(drawn(3, 2, cell=10, spacing=4))
    assert found is not None
    assert found.cell[0] + found.spacing[0] == 14
    assert found.cell[1] + found.spacing[1] == 14


def test_a_grid_with_margins_excludes_them() -> None:
    found = detect_grid(drawn(2, 2, cell=8, margin=5, spacing=2))
    assert found is not None
    assert found.margin == (6, 6), "the drawn margin, plus the sprite's own inset"
    assert (found.columns, found.rows) == (2, 2)


def test_a_grid_with_no_spacing_is_detected_from_the_gaps_the_inset_leaves() -> None:
    """R2.2's other case: cells that abut. Their gutters are zero, so what separates the
    content is the sprites' own inset — and the pitch still comes back."""
    found = detect_grid(drawn(4, 1, cell=6, spacing=0))
    assert found is not None
    assert (found.columns, found.rows) == (4, 1)
    assert found.cell[0] + found.spacing[0] == 6


def test_a_single_cell_is_a_one_by_one_grid() -> None:
    found = detect_grid(drawn(1, 1, cell=12))
    assert found is not None
    assert (found.columns, found.rows) == (1, 1)


def test_the_detected_grid_covers_the_sheet_it_was_detected_from() -> None:
    """The property that actually matters downstream: whatever is returned has to describe
    the image it came from, or every frame cut with it is off."""
    image = drawn(3, 3, cell=9, margin=2, spacing=3)
    found = detect_grid(image)
    assert found is not None
    height, width = image.shape[:2]
    spanned_x = found.margin[0] + found.columns * found.cell[0]
    spanned_x += found.spacing[0] * (found.columns - 1)
    spanned_y = found.margin[1] + found.rows * found.cell[1]
    spanned_y += found.spacing[1] * (found.rows - 1)
    assert spanned_x <= width
    assert spanned_y <= height


# R1.3 — refusing rather than guessing.


def test_an_empty_sheet_has_no_grid() -> None:
    assert detect_grid(np.zeros((16, 16, 4), dtype=np.uint8)) is None


def test_a_sheet_that_is_one_solid_block_has_no_grid() -> None:
    """Nothing separates anything, so there is no layout to find — and inventing 1x1 for a
    sheet somebody meant to be 4x4 is exactly the plausible wrong answer to avoid."""
    image = np.zeros((16, 16, 4), dtype=np.uint8)
    image[..., 3] = 255
    assert detect_grid(image) is None


def test_irregular_content_is_not_forced_into_a_grid() -> None:
    """Three blobs at unrelated positions and sizes are not a 3x1 sheet, and saying they
    are would cut somebody's illustration into thirds."""
    image = np.zeros((40, 40, 4), dtype=np.uint8)
    image[2:9, 1:6, 3] = 255
    image[13:37, 9:31, 3] = 255
    image[4:8, 33:39, 3] = 255
    assert detect_grid(image) is None


# The three the review found, each with the scene that exposes it.


def test_an_asymmetric_margin_does_not_shift_every_cell() -> None:
    """The blocker. `grid_rects` re-derives the cell by dividing the width, which assumes
    the far margin equals the near one; a sheet padded 5px left and 15px right came back
    with 9px cells where 6px were measured, dropping content off one edge of every piece
    and pulling in its neighbour's. Asserted on pixels, not on a count — a count was green
    the whole time this was broken.
    """
    from ssc.core.recover import crop, rects_from

    image = np.zeros((20, 5 + 3 * 6 + 2 * 4 + 15, 4), dtype=np.uint8)
    for index in range(3):
        x = 5 + index * (6 + 4)
        image[6:14, x : x + 6, 3] = 255
        image[6:14, x : x + 6, 0] = 60 + index * 60  # a different red per piece

    found = detect_grid(image)
    assert found is not None
    assert found.cell[0] == 6

    pieces = [crop(image, rect) for rect in rects_from(found)]
    assert len(pieces) == 3
    for index, piece in enumerate(pieces):
        opaque = piece[piece[..., 3] > 0]
        assert opaque.size > 0, f"piece {index} is empty"
        assert set(np.unique(opaque[:, 0]).tolist()) == {60 + index * 60}, (
            f"piece {index} holds pixels from another piece"
        )


def test_two_blobs_on_a_diagonal_are_not_a_two_by_two_grid() -> None:
    """Regular across and regular down, and still not a sheet: nothing occupies the other
    two cells of the layout those two axes describe."""
    image = np.zeros((40, 40, 4), dtype=np.uint8)
    image[2:10, 2:10, 3] = 255
    image[25:33, 25:33, 3] = 255
    assert detect_grid(image) is None


def test_a_full_two_by_two_is_still_detected() -> None:
    """The other half of the occupancy check: it must not refuse a real grid."""
    found = detect_grid(drawn(2, 2, cell=10, spacing=2))
    assert found is not None
    assert (found.columns, found.rows) == (2, 2)


# The re-review's two, and the root cause they share.


def test_columns_of_differing_widths_are_each_cut_where_they_are() -> None:
    """The blocker, properly this time. `regular()` allows 25% of variation, so widths of
    10 and 8 alternating are a grid — and reconstructing every position from one maximum
    cell and one maximum gap drifts a little further out of step with every column, until
    one rectangle holds two sprites and the last runs off the image.

    The bands cannot drift, because they are measurements rather than a reconstruction.
    """
    from ssc.core.recover import crop, rects_from

    widths = [10, 8, 10, 8, 10, 8, 10, 8]
    gap = 5
    total = sum(widths) + gap * (len(widths) - 1)
    image = np.zeros((12, total, 4), dtype=np.uint8)
    x = 0
    for index, width in enumerate(widths):
        image[2:10, x : x + width, 3] = 255
        image[2:10, x : x + width, 0] = 10 + index * 20
        x += width + gap

    found = detect_grid(image)
    assert found is not None
    assert found.columns == len(widths)

    for index, piece in enumerate(crop(image, rect) for rect in rects_from(found)):
        opaque = piece[piece[..., 3] > 0]
        assert set(np.unique(opaque[:, 0]).tolist()) == {10 + index * 20}, (
            f"piece {index} holds another piece's pixels"
        )


def test_a_sheet_with_one_blank_cell_is_still_a_sheet() -> None:
    """A blink, a fade, a frame the animator left empty. Refusing the whole layout because
    one cell of it is empty was the first fix's overreach — an occupancy check cannot tell
    that apart from two shapes on a diagonal, so it is not the check to use."""
    image = np.zeros((24, 24, 4), dtype=np.uint8)
    for row, column in ((0, 0), (0, 1), (1, 0)):
        y, x = 2 + row * 12, 2 + column * 12
        image[y : y + 8, x : x + 8, 3] = 255

    found = detect_grid(image)
    assert found is not None
    assert (found.columns, found.rows) == (2, 2)


def test_a_gutter_wider_than_a_cell_is_not_a_gutter() -> None:
    """What refuses the diagonal instead: both axes are regular taken alone, and only a
    real sheet has gaps that are small against its cells."""
    image = np.zeros((40, 40, 4), dtype=np.uint8)
    image[2:10, 2:10, 3] = 255
    image[25:33, 25:33, 3] = 255
    assert detect_grid(image) is None


def test_a_rectangle_off_the_edge_is_refused_rather_than_truncated() -> None:
    """A numpy slice past the edge truncates silently, which is how a piece became a 2x10
    file on disk while the command's JSON called it 10x10."""
    from ssc.core.recover import Rect, crop

    with pytest.raises(ValueError, match="not inside"):
        crop(np.zeros((10, 10, 4), dtype=np.uint8), Rect(x=5, y=0, width=10, height=10))
