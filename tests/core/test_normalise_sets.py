"""The scale decision — plan `sprite-normalisation-gate` 4.1 (TDD).

One visible-height factor per frame set, bringing every set of one asset onto one target
visible height through the project's single nearest-neighbour resampler. The sprite that
grows two pixels when it starts walking is the defect; this is the arithmetic that fixes
it, and arithmetic nobody watches go wrong.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.doctor.masks import bounds_of
from ssc.core.normalise import normalise_sets, scale_factor, scale_plan, scale_target, scaled_size
from ssc.core.resize import ResizeParams, resize


def sprite_frame(canvas: tuple[int, int], y: int, x: int, height: int, width: int) -> np.ndarray:
    image = np.zeros((canvas[0], canvas[1], 4), dtype=np.uint8)
    image[y : y + height, x : x + width] = (0, 0, 0, 255)
    return image


# ── the target ────────────────────────────────────────────────────────────────────────


def test_the_target_is_the_median_visible_height() -> None:
    """The one height every set is resampled onto. The median, not the max, so a single
    outsized set does not pull every other up to it; not the mean, so the target is a whole
    pixel a nearest-neighbour resampler can actually hit."""
    assert scale_target([30, 32]) == 31
    assert scale_target([30, 31, 34]) == 31


def test_a_blank_set_cannot_anchor_a_target() -> None:
    """A set with no visible height is a set `bounds` reported blank; it has no height to
    scale from or to, and a target of zero would divide every factor by nothing."""
    with pytest.raises(ValueError):
        scale_target([30, 0])


# ── the factor ─────────────────────────────────────────────────────────────────────────


def test_the_factor_is_target_over_source() -> None:
    assert scale_factor(30, 31) == pytest.approx(31 / 30)
    assert scale_factor(32, 31) == pytest.approx(31 / 32)


def test_a_set_already_on_target_is_unchanged() -> None:
    """The set at the target gets factor 1.0 and is left alone — resampling it would risk
    the very drift the gate exists to remove, for no gain."""
    assert scale_factor(31, 31) == 1.0


def test_a_blank_set_has_no_factor() -> None:
    with pytest.raises(ValueError):
        scale_factor(0, 31)


# ── the resampled size ─────────────────────────────────────────────────────────────────


def test_the_output_canvas_is_the_source_scaled_uniformly() -> None:
    """One factor for width and height both, so the sprite's proportions survive. Rounded
    to whole pixels, because the resampler takes integers and a fractional cell is not a
    cell an engine can address."""
    out = scaled_size((40, 20), 31 / 30)
    assert out == (round(40 * 31 / 30), round(20 * 31 / 30))


def test_a_factor_of_one_leaves_the_canvas_untouched() -> None:
    assert scaled_size((40, 20), 1.0) == (40, 20)


def test_the_output_canvas_cannot_shrink_below_one_pixel() -> None:
    """A near-zero factor from a giant set onto a tiny target would otherwise round the
    canvas away entirely."""
    assert scaled_size((8, 8), 0.01) == (1, 1)


# ── the plan ───────────────────────────────────────────────────────────────────────────


def test_the_plan_gives_one_factor_and_one_canvas_per_set() -> None:
    """idle at 30px on a 40x40 canvas, walk at 32px on a 40x40 canvas, target 31."""
    plan = scale_plan(
        visible_heights=[30, 32],
        canvases=[(40, 40), (40, 40)],
        target=31,
    )
    assert len(plan) == 2
    assert plan[0].factor == pytest.approx(31 / 30)
    assert plan[0].canvas == (round(40 * 31 / 30), round(40 * 31 / 30))
    assert plan[1].factor == pytest.approx(31 / 32)


def test_a_set_on_target_is_unchanged_in_the_plan() -> None:
    plan = scale_plan(visible_heights=[31, 31], canvases=[(40, 40), (32, 48)], target=31)
    assert plan[0].factor == 1.0
    assert plan[0].canvas == (40, 40)
    assert plan[1].factor == 1.0
    assert plan[1].canvas == (32, 48)


# ── the resampler honours the decision ─────────────────────────────────────────────────


def test_resampling_puts_the_visible_height_on_target() -> None:
    """The decision's proof: a frame resampled by the plan's factor, through the one
    resampler the project allows, lands its visible height on the target. idle 5px onto
    target 10 doubles cleanly."""
    frame = sprite_frame((10, 10), y=2, x=2, height=5, width=4)
    factor = scale_factor(5, 10)
    out_w, out_h = scaled_size((10, 10), factor)
    resampled = resize(frame, ResizeParams(width=out_w, height=out_h))
    box = bounds_of(resampled)
    assert box is not None
    assert box.height == 10


def test_resampling_a_set_on_target_is_the_identity() -> None:
    """Factor 1.0 means the resampler is not run at all in the normaliser; here we only
    confirm that the size it would produce leaves the visible height alone."""
    frame = sprite_frame((10, 10), y=2, x=2, height=5, width=4)
    out_w, out_h = scaled_size((10, 10), scale_factor(5, 5))
    assert (out_w, out_h) == (10, 10)
    box = bounds_of(frame)
    assert box is not None
    assert box.height == 5


# ── the gate ──────────────────────────────────────────────────────────────────────────


from ssc.core.assemble import anchor_pixel  # noqa: E402


def _cells(sheet: np.ndarray, cell: tuple[int, int], count: int) -> list[np.ndarray]:
    cell_w, cell_h = cell
    return [sheet[0:cell_h, i * cell_w : (i + 1) * cell_w] for i in range(count)]


def _median_visible_height(sheet: np.ndarray, cell: tuple[int, int], count: int) -> float:
    boxes = (bounds_of(c) for c in _cells(sheet, cell, count))
    heights = [box.height for box in boxes if box is not None]
    return float(np.median(heights))


def test_normalise_puts_every_set_on_one_canvas_and_one_anchor() -> None:
    """idle visible height 4, walk visible height 6 — the two-pixel defect. After the gate
    every set is a sheet of one cell size, and the anchor pixel is the same across sets, so
    an engine pins idle and walk to the same floor and the same centreline."""
    idle = [sprite_frame((8, 8), y=2, x=2, height=4, width=3) for _ in range(2)]
    walk = [sprite_frame((8, 8), y=1, x=1, height=6, width=3) for _ in range(2)]

    result = normalise_sets([idle, walk])

    assert len(result.sheets) == 2
    assert result.target == 5  # median(4, 6)
    assert result.factors == pytest.approx([5 / 4, 5 / 6])
    # One canvas: both sheets are laid out on the same cell, so with the same frame count
    # their shapes match.
    assert result.sheets[0].shape == result.sheets[1].shape
    # One baseline and one centre column: the anchor pixel inside a cell of idle equals the
    # one inside a cell of walk.
    cell = result.layout.cell
    idle_anchor = anchor_pixel(_cells(result.sheets[0], cell, 2)[0], "feet")
    walk_anchor = anchor_pixel(_cells(result.sheets[1], cell, 2)[0], "feet")
    assert idle_anchor is not None
    assert walk_anchor is not None
    # `anchor_pixel` returns (row, column); `Layout.anchor` is (column, row) — same pixel.
    assert idle_anchor == walk_anchor == (result.layout.anchor[1], result.layout.anchor[0])


def test_normalise_closes_the_visible_height_gap_to_within_a_rounding_pixel() -> None:
    """The defect was a two-pixel difference between idle and walk. The gate resamples both
    onto one target; what is left is at most the one pixel nearest-neighbour rounds to, not
    the two the sprite grew by."""
    idle = [sprite_frame((8, 8), y=2, x=2, height=4, width=3) for _ in range(2)]
    walk = [sprite_frame((8, 8), y=1, x=1, height=6, width=3) for _ in range(2)]

    result = normalise_sets([idle, walk])
    cell = result.layout.cell
    idle_h = _median_visible_height(result.sheets[0], cell, 2)
    walk_h = _median_visible_height(result.sheets[1], cell, 2)

    assert abs(idle_h - walk_h) <= 1  # was 2 before the gate


def test_a_set_already_on_target_passes_through_unchanged() -> None:
    """Both sets at the same height: the target is that height, every factor is 1.0, and no
    frame is resampled — the resampler is not run on a set that needs no resampling."""
    idle = [sprite_frame((8, 8), y=2, x=2, height=5, width=3) for _ in range(2)]
    walk = [sprite_frame((8, 8), y=2, x=2, height=5, width=3) for _ in range(2)]

    result = normalise_sets([idle, walk])
    assert result.target == 5
    assert result.factors == [1.0, 1.0]


def test_a_blank_set_is_refused() -> None:
    """A set with no visible height has nothing to scale from; the gate refuses to guess
    rather than average a zero into the target."""
    idle = [sprite_frame((8, 8), y=2, x=2, height=4, width=3) for _ in range(2)]
    blank = [np.zeros((8, 8, 4), dtype=np.uint8) for _ in range(2)]
    with pytest.raises(ValueError):
        normalise_sets([idle, blank])


def test_no_sets_is_refused() -> None:
    with pytest.raises(ValueError):
        normalise_sets([])
