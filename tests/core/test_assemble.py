"""Putting the pieces back — specs/sheet-assembly R1, R2, R3, R4.

`plan_alignment` is the (TDD) part. Its failure mode is the one this whole leaf exists to
remove: an alignment that is subtly off looks fine frame by frame and reads as drift when
the animation plays, which is exactly what `doctor`'s `drift` check measures. So the
assertions are about where the anchors end up, not about what the implementation returns.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.assemble import (
    expand,
    flip,
    mirror,
    mirror_anchor,
    mirror_box,
    offset,
    offset_anchor,
    offset_box,
    pack,
    plan_alignment,
    rotate,
    rotate_anchor,
    rotate_box,
    rotate_cell,
    trim_anchor,
    trim_box,
    union_box,
)
from ssc.core.doctor.masks import alpha_mask, anchor


def figure(width: int, height: int, x: int, y: int, w: int = 2, h: int = 4) -> np.ndarray:
    """A frame with one opaque block standing at (x, y)."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[y : y + h, x : x + w] = (200, 30, 30, 255)
    return image


# R3.2, R3.3 — every anchor on one pixel, and nothing pushed off the canvas.


def test_every_frames_anchor_lands_on_the_same_pixel() -> None:
    frames = [figure(12, 12, 1, 2), figure(12, 12, 7, 5), figure(12, 12, 4, 0)]
    placed = plan_alignment(frames, "feet")

    anchors = {anchor(alpha_mask(frame)) for frame in placed.frames}
    assert len(anchors) == 1


def test_no_frames_content_leaves_the_canvas() -> None:
    """The easy way to get this wrong is to shift within the original canvas, which only
    fits if the anchors happened to be arranged conveniently."""
    frames = [figure(12, 12, 0, 8), figure(12, 12, 10, 0)]
    placed = plan_alignment(frames, "feet")

    for before, after in zip(frames, placed.frames, strict=True):
        assert int(alpha_mask(after).sum()) == int(alpha_mask(before).sum())


def test_alignment_is_a_move_and_not_a_resample() -> None:
    """The pixels are moved, never recomputed — nothing here may reintroduce the blur."""
    frames = [figure(12, 12, 1, 2), figure(12, 12, 7, 5)]
    placed = plan_alignment(frames, "feet")

    for frame in placed.frames:
        opaque = frame[frame[..., 3] > 0]
        assert {tuple(colour) for colour in np.unique(opaque, axis=0)} == {(200, 30, 30, 255)}


def test_the_common_anchor_is_reported() -> None:
    placed = plan_alignment([figure(12, 12, 1, 2)], "feet")
    assert placed.anchor[0] >= 0 and placed.anchor[1] >= 0


def test_centre_and_bottom_are_anchors_too() -> None:
    frames = [figure(12, 12, 1, 2), figure(12, 12, 7, 5)]
    for mode in ("bottom", "centre"):
        placed = plan_alignment(frames, mode)
        assert len(placed.frames) == 2
        assert placed.frames[0].shape == placed.frames[1].shape


def test_one_frame_aligns_to_itself() -> None:
    placed = plan_alignment([figure(12, 12, 3, 3)], "feet")
    assert int(alpha_mask(placed.frames[0]).sum()) == 8


# R3.4 — a frame with nothing in it.


def test_an_empty_frame_is_left_where_it_is_and_reported() -> None:
    """A blank frame is a legitimate frame of an animation, and it has no anchor to move."""
    frames = [figure(12, 12, 1, 2), np.zeros((12, 12, 4), dtype=np.uint8)]
    placed = plan_alignment(frames, "feet")

    assert placed.empty == [1]
    assert not alpha_mask(placed.frames[1]).any()
    assert placed.frames[1].shape == placed.frames[0].shape


def test_a_set_of_nothing_but_empty_frames_does_not_fail() -> None:
    frames = [np.zeros((8, 8, 4), dtype=np.uint8)] * 2
    placed = plan_alignment(frames, "feet")
    assert placed.empty == [0, 1]


# R1 — padding.


def test_expand_to_a_size_centres_the_content() -> None:
    grown = expand(figure(4, 4, 1, 0, 2, 4), to=(8, 8))
    assert grown.shape == (8, 8, 4)
    assert int(alpha_mask(grown).sum()) == 8
    assert not alpha_mask(grown)[:, 0].any()


def test_expand_by_a_margin_adds_it_on_every_side() -> None:
    grown = expand(figure(4, 4, 1, 0), by=2)
    assert grown.shape == (8, 8, 4)


def test_expand_puts_the_content_on_the_floor_for_a_bottom_anchor() -> None:
    grown = expand(figure(4, 4, 1, 0, 2, 4), to=(8, 8), place="bottom")
    assert alpha_mask(grown)[-1].any()


def test_expand_fills_the_new_area_when_asked() -> None:
    grown = expand(figure(4, 4, 1, 0), to=(8, 8), fill=(0, 177, 64))
    assert tuple(grown[0, 0]) == (0, 177, 64, 255)


def test_expand_leaves_the_new_area_transparent_by_default() -> None:
    assert tuple(expand(figure(4, 4, 1, 0), to=(8, 8))[0, 0]) == (0, 0, 0, 0)


@pytest.mark.parametrize("target", [(2, 8), (8, 2)])
def test_expand_never_crops(target: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="smaller"):
        expand(figure(4, 4, 1, 0), to=target)


# R2.1 — flipping.


def test_flip_mirrors_horizontally_and_nothing_else() -> None:
    frame = figure(6, 4, 0, 0, 2, 4)
    mirrored = flip(frame)
    assert alpha_mask(mirrored)[:, -2:].all()
    assert not alpha_mask(mirrored)[:, :-2].any()


def test_flipping_twice_is_the_original() -> None:
    frame = figure(6, 4, 1, 0)
    assert np.array_equal(flip(flip(frame)), frame)


def test_mirror_vertical_matches_flip() -> None:
    frame = figure(6, 4, 0, 0, 2, 4)
    assert np.array_equal(mirror(frame, "vertical"), flip(frame))


def test_mirror_horizontal_flips_top_to_bottom() -> None:
    frame = figure(6, 4, 0, 0, w=2, h=2)
    mirrored = mirror(frame, "horizontal")
    # the block stood at the top (rows 0..1); a horizontal-axis flip moves it to the bottom.
    assert alpha_mask(mirrored)[2:, :2].all()
    assert not alpha_mask(mirrored)[:2, :2].any()


def test_mirroring_twice_about_either_axis_is_the_original() -> None:
    frame = figure(6, 4, 1, 1)
    assert np.array_equal(mirror(mirror(frame, "vertical"), "vertical"), frame)
    assert np.array_equal(mirror(mirror(frame, "horizontal"), "horizontal"), frame)


# rotation — quarter turns only, never a resample


def test_one_quarter_turn_moves_the_top_row_to_the_left_column() -> None:
    frame = figure(6, 4, 0, 0, w=2, h=2)  # opaque block at the top-left
    turned = rotate(frame, 1)
    # 90° CCW: the top-left block lands at the bottom-left.
    assert alpha_mask(turned)[-2:, :2].all()
    assert not alpha_mask(turned)[:-2, :2].any()


def test_two_quarter_turns_flips_top_to_bottom() -> None:
    frame = figure(6, 4, 0, 0, w=2, h=2)
    turned = rotate(frame, 2)
    # 180°: the top-left block lands at the bottom-right.
    assert alpha_mask(turned)[-2:, -2:].all()
    assert not alpha_mask(turned)[-2:, :-2].any()


def test_three_quarter_turns_is_the_inverse_of_one() -> None:
    frame = figure(6, 4, 0, 0, w=2, h=2)
    assert np.array_equal(rotate(rotate(frame, 1), 3), frame)


def test_four_quarter_turns_is_the_original() -> None:
    frame = figure(6, 4, 1, 1)
    assert np.array_equal(rotate(frame, 4), frame)


# trim — one box for the whole set, never one per frame


def test_union_box_covers_every_frame_and_no_more() -> None:
    # one frame opaque at the left, one at the right: the box spans both.
    left = figure(8, 8, 0, 0, w=2, h=2)
    right = figure(8, 8, 6, 6, w=2, h=2)
    box = union_box([left, right])
    assert box == (0, 0, 8, 8)


def test_union_box_is_the_smallest_covering_the_opaque_pixels() -> None:
    frame = figure(10, 10, 3, 2, w=4, h=5)  # opaque block at x=3..6, y=2..6
    box = union_box([frame])
    assert box == (3, 2, 4, 5)


def test_union_box_is_none_where_no_frame_has_opaque_pixels() -> None:
    empty = np.zeros((6, 6, 4), dtype=np.uint8)
    assert union_box([empty]) is None


# offset — whole-pixel shift, never a resample


def test_offset_moves_content_right_and_down() -> None:
    """Positive dx moves right, positive dy moves down — the direction the flags name."""
    frame = figure(8, 8, 0, 0, w=2, h=2)  # opaque block at the top-left
    moved = offset(frame, 2, 3)
    # the block lands at x=2..3, y=3..4
    assert alpha_mask(moved)[3:5, 2:4].all()
    assert not alpha_mask(moved)[:3, :].any()
    assert int(alpha_mask(moved).sum()) == 4


def test_offset_negative_moves_left_and_up() -> None:
    frame = figure(8, 8, 6, 6, w=2, h=2)  # opaque block at the bottom-right
    moved = offset(frame, -2, -3)
    # the block lands at x=4..5, y=3..4
    assert alpha_mask(moved)[3:5, 4:6].all()
    assert int(alpha_mask(moved).sum()) == 4


def test_offset_drops_content_shifted_off_the_canvas() -> None:
    """The canvas keeps its size; pixels that leave it are gone, not wrapped or cropped smaller."""
    frame = figure(4, 4, 0, 0, w=4, h=4)  # fully opaque
    moved = offset(frame, 2, 0)  # shift right by 2 — the right two columns leave
    assert moved.shape == (4, 4, 4)
    assert int(alpha_mask(moved).sum()) == 8  # half the block remains


def test_offset_keeps_the_canvas_size() -> None:
    frame = figure(6, 5, 1, 1, w=2, h=2)
    moved = offset(frame, -1, 2)
    assert moved.shape == frame.shape


def test_offset_by_zero_is_the_original() -> None:
    frame = figure(6, 6, 1, 1, w=2, h=2)
    assert np.array_equal(offset(frame, 0, 0), frame)


def test_offset_is_a_move_not_a_resample() -> None:
    """No pixel is recomputed — the colours arrive intact, which is what keeps the blur out."""
    frame = figure(8, 8, 0, 0, w=2, h=2)
    moved = offset(frame, 3, 3)
    opaque = moved[moved[..., 3] > 0]
    assert {tuple(colour) for colour in np.unique(opaque, axis=0)} == {(200, 30, 30, 255)}


# the recorded anchor moves with the transform — the point an engine pins the sprite to
# has to land where the sprite's pixels did, or the sprite jitters when it turns.


def test_mirror_anchor_maps_x_to_width_minus_one_minus_x() -> None:
    """The detail that breaks: `width - 1 - x`, not `width - x`. Pixels are 0-indexed, so
    a width-6 frame's rightmost column is 5; mapping x to `width - x` sends column 0 to 6,
    one past the edge, and the sprite jitters by a pixel when it turns to its mirror."""
    assert mirror_anchor((1, 2), width=6, height=4, axis="vertical") == (4, 2)


def test_mirror_anchor_about_the_horizontal_axis_maps_y() -> None:
    assert mirror_anchor((1, 1), width=6, height=4, axis="horizontal") == (1, 2)


def test_mirror_anchor_vertical_then_horizontal_is_the_corner() -> None:
    x, y = mirror_anchor((1, 1), width=6, height=4, axis="vertical")
    x, y = mirror_anchor((x, y), width=6, height=4, axis="horizontal")
    assert (x, y) == (4, 2)


def test_rotate_anchor_one_quarter_turn_swaps_the_axes() -> None:
    """90° CCW: (x, y) → (y, width - 1 - x). The width is the pre-turn width, and the new
    anchor sits on the frame's new width (the old height), which is why the cell and the
    anchor stop matching after an odd turn until both are moved."""
    assert rotate_anchor((1, 2), width=6, height=4, turns=1) == (2, 4)


def test_rotate_anchor_two_quarter_turns_is_a_point_mirror() -> None:
    assert rotate_anchor((1, 2), width=6, height=4, turns=2) == (4, 1)


def test_rotate_anchor_three_quarter_turns_is_the_inverse_of_one() -> None:
    assert rotate_anchor((1, 2), width=6, height=4, turns=3) == (1, 1)


def test_rotate_anchor_four_turns_is_the_original() -> None:
    assert rotate_anchor((1, 2), width=6, height=4, turns=4) == (1, 2)


def test_offset_anchor_adds_the_shift() -> None:
    assert offset_anchor((3, 5), dx=2, dy=-1) == (5, 4)


def test_trim_anchor_moves_by_the_box_origin() -> None:
    """Trim crops to a box at (x, y), so every pixel — and the anchor — loses that origin."""
    assert trim_anchor((5, 6), box=(1, 2, 8, 7)) == (4, 4)


# plans/ssc-completion 7.8 — a box moves by the same transform as the pixels it covers, or
# a mirrored frame with an unmirrored hurt box takes damage on the wrong side. Each test
# asserts against where the pixels actually landed, not against the formula.


def opaque_box(frame: np.ndarray) -> tuple[int, int, int, int]:
    box = union_box([frame])
    assert box is not None
    return box


def stamped(width: int, height: int, box: tuple[int, int, int, int]) -> np.ndarray:
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    x, y, w, h = box
    frame[y : y + h, x : x + w] = 255
    return frame


@pytest.mark.parametrize("axis", ["vertical", "horizontal"])
def test_mirror_box_lands_where_the_mirrored_pixels_did(axis: str) -> None:
    frame = stamped(6, 4, (1, 2, 2, 1))
    moved = mirror_box((1, 2, 2, 1), width=6, height=4, axis=axis)
    assert moved == opaque_box(mirror(frame, axis))


@pytest.mark.parametrize("turns", [1, 2, 3])
def test_rotate_box_lands_where_the_turned_pixels_did(turns: int) -> None:
    frame = stamped(6, 4, (1, 2, 3, 1))
    moved = rotate_box((1, 2, 3, 1), width=6, height=4, turns=turns)
    assert moved == opaque_box(rotate(frame, turns))


def test_offset_box_moves_and_clips_like_the_pixels() -> None:
    frame = stamped(6, 4, (1, 1, 2, 2))
    moved = offset_box((1, 1, 2, 2), dx=4, dy=0, width=6, height=4)
    assert moved == opaque_box(offset(frame, 4, 0))


def test_offset_box_entirely_off_the_canvas_is_gone() -> None:
    assert offset_box((1, 1, 2, 2), dx=6, dy=0, width=6, height=4) is None


def test_trim_box_moves_by_the_kept_origin_and_clips_to_it() -> None:
    assert trim_box((2, 3, 2, 2), kept=(1, 2, 8, 7)) == (1, 1, 2, 2)
    # a box may outgrow the opaque content that decided the trim; the part outside the
    # crop is dropped with the pixels that were there
    assert trim_box((0, 0, 4, 4), kept=(1, 2, 3, 2)) == (0, 0, 3, 2)


def test_trim_box_outside_the_kept_content_is_gone() -> None:
    assert trim_box((0, 0, 1, 1), kept=(2, 2, 4, 4)) is None


# an odd quarter turn swaps the cell's sides — the cell a pack laid out no longer fits


def test_rotate_cell_swaps_sides_on_an_odd_turn() -> None:
    assert rotate_cell((16, 8), turns=1) == (8, 16)
    assert rotate_cell((16, 8), turns=3) == (8, 16)


def test_rotate_cell_keeps_sides_on_an_even_turn() -> None:
    assert rotate_cell((16, 8), turns=2) == (16, 8)
    assert rotate_cell((16, 8), turns=4) == (16, 8)


# R4 — the sheet.


def test_pack_lays_every_frame_into_a_cell() -> None:
    frames = [figure(4, 4, 0, 0), figure(4, 4, 2, 0), figure(4, 4, 1, 0)]
    sheet, layout = pack(frames, columns=2)

    assert layout.columns == 2
    assert layout.rows == 2
    assert layout.cell == (4, 4)
    assert sheet.shape == (8, 8, 4)


def test_pack_sizes_the_cell_to_the_largest_frame() -> None:
    frames = [figure(4, 4, 0, 0), figure(6, 5, 0, 0)]
    _, layout = pack(frames, columns=2)
    assert layout.cell == (6, 5)


def test_a_given_cell_that_is_too_small_is_refused() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        pack([figure(8, 8, 0, 0)], columns=1, cell=(4, 4))


def test_pack_keeps_each_frames_pixels_in_its_own_cell() -> None:
    frames = [figure(4, 4, 0, 0, 2, 4), figure(4, 4, 2, 0, 2, 4)]
    sheet, _ = pack(frames, columns=2)

    assert alpha_mask(sheet[:, :4]).sum() == 8
    assert alpha_mask(sheet[:, 4:]).sum() == 8


# The two blockers the review found, each with the case that exposes it.


def test_frames_of_differing_body_parity_land_on_one_anchor_pixel() -> None:
    """The first fix decided the margins and then copied each frame verbatim, so a body two
    pixels wide (anchored at x.5) and one three wide (anchored at x.0) stayed exactly as far
    apart as they began. A 2px body and a 3px body cannot share a sub-pixel centre however
    they are moved — so what has to coincide is the *pixel*, and every frame's anchor is
    rounded to one before anything is placed.
    """
    from ssc.core.assemble import anchor_pixel

    frames = [figure(20, 20, 5, 10, 2, 4), figure(20, 20, 5, 10, 3, 4)]
    placed = plan_alignment(frames, "feet")

    pixels = {anchor_pixel(frame, "feet") for frame in placed.frames}
    assert len(pixels) == 1, f"anchors landed on different pixels: {pixels}"


def test_a_set_of_mixed_parities_and_sizes_still_agrees() -> None:
    from ssc.core.assemble import anchor_pixel

    frames = [
        figure(20, 20, 3, 8, 2, 6),
        figure(24, 18, 9, 4, 5, 9),
        figure(16, 22, 1, 12, 3, 5),
        figure(20, 20, 7, 2, 4, 11),
    ]
    placed = plan_alignment(frames, "feet")
    assert len({anchor_pixel(frame, "feet") for frame in placed.frames}) == 1


def test_pack_reports_where_align_actually_put_the_anchor() -> None:
    """The second blocker: `pack` guessed bottom-centre, which disagreed with `align` by six
    pixels vertically on this very fixture — an aligned canvas keeps whatever transparent
    padding sat below the anchor row. These two commands are used in sequence and nothing
    composed them until now.
    """
    frames = [figure(12, 12, 1, 2), figure(12, 12, 7, 5)]
    placed = plan_alignment(frames, "feet")
    _, layout = pack(placed.frames, columns=2)

    assert layout.anchor == placed.anchor
    assert layout.aligned is True


def test_packing_a_set_that_was_never_aligned_says_so() -> None:
    """Reported rather than quietly averaged: an engine believing a wrong anchor is the
    failure this field exists to prevent."""
    frames = [figure(12, 12, 1, 2), figure(12, 12, 7, 5)]
    _, layout = pack(frames, columns=2)
    assert layout.aligned is False


def test_onion_layers_the_opaque_pixels_over_each_other() -> None:
    from ssc.core.assemble import onion

    first = figure(8, 8, 0, 0, 2, 2)
    second = figure(8, 8, 4, 4, 2, 2)
    stacked = onion([first, second])

    assert alpha_mask(stacked)[0, 0]
    assert alpha_mask(stacked)[4, 4]
    assert int(alpha_mask(stacked).sum()) == 8


# R1.6, R3.6, R4.5 — every canvas bounded on the result, not on the flag.


def test_expand_refuses_a_canvas_past_the_ceiling() -> None:
    """`--by` is doubled by the time it becomes a canvas, so bounding the flag alone left
    the result at twice the ceiling every sibling command is held to."""
    from ssc.core.assemble import MAX_CANVAS, CanvasTooLarge

    with pytest.raises(CanvasTooLarge, match="past"):
        expand(figure(4, 4, 0, 0), by=MAX_CANVAS)


def test_pack_refuses_a_sheet_past_the_ceiling() -> None:
    """`--cols` widens the sheet whether or not there are frames to fill it."""
    from ssc.core.assemble import CanvasTooLarge

    with pytest.raises(CanvasTooLarge, match="the sheet"):
        pack([figure(256, 256, 0, 0)], columns=4096)


def test_align_refuses_a_canvas_the_anchors_would_demand() -> None:
    """Sized from the content, which no read-side ceiling bounds."""
    from ssc.core.assemble import CanvasTooLarge

    frames = [figure(9000, 8, 0, 0, 2, 4), figure(9000, 8, 8990, 0, 2, 4)]
    with pytest.raises(CanvasTooLarge, match="aligning"):
        plan_alignment(frames, "feet")


def test_a_canvas_at_the_ceiling_is_allowed() -> None:
    """The other half: the cap must not refuse what it was sized to permit."""
    from ssc.core.assemble import MAX_CANVAS

    assert expand(figure(4, 4, 0, 0), to=(MAX_CANVAS, 4)).shape[1] == MAX_CANVAS


@pytest.mark.parametrize("mode", ["feet", "bottom", "centre"])
def test_pack_measures_the_same_anchor_align_used(mode: str) -> None:
    """The fourth instance of the class, found by the re-review: measuring `feet` on a set
    aligned by `centre` gives the wrong pixel *and* falsely calls the set unaligned. The
    mode cannot be derived from the frames, so it travels between the two commands."""
    frames = [figure(20, 20, 3, 8, 2, 6), figure(24, 18, 9, 4, 5, 9)]
    placed = plan_alignment(frames, mode)
    _, layout = pack(placed.frames, columns=2, mode=mode)

    assert layout.anchor == placed.anchor
    assert layout.aligned is True
