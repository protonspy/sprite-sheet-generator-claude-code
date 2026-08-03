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
    pack,
    plan_alignment,
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
