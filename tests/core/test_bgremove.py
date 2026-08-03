"""Chroma keying — specs/background-removal R1.3, R2.1, R2.2, R3.1, R3.2, R3.3, R3.4."""

from __future__ import annotations

import numpy as np

from ssc.core.bgremove import (
    PRESETS,
    BgRemoveParams,
    despeckle_opaque,
    despill,
    key_mask,
    reachable_from_border,
    remove,
    trim,
)

GREEN = PRESETS["green"]
SKIN = (220, 180, 150)


def scene() -> np.ndarray:
    """A green backdrop, a subject in the middle, and a green gem inside the subject.

    The gem is the whole point of the leaf: it is the key colour, it is not the background,
    and only its being enclosed by the subject can say so.
    """
    image = np.zeros((10, 10, 4), dtype=np.uint8)
    image[..., :3] = GREEN
    image[..., 3] = 255
    image[2:8, 2:8, :3] = SKIN
    image[4:6, 4:6, :3] = GREEN
    return image


# R1.3 — what counts as the key.


def test_the_key_matches_itself_and_not_the_subject() -> None:
    mask = key_mask(scene(), GREEN, tolerance=10)
    assert mask[0, 0]
    assert not mask[2, 2]


def test_tolerance_widens_what_matches() -> None:
    image = np.zeros((2, 2, 4), dtype=np.uint8)
    image[..., :3] = (0x00, 0xB1, 0x60)  # 32 away from the green preset
    assert not key_mask(image, GREEN, tolerance=10).any()
    assert key_mask(image, GREEN, tolerance=40).all()


def test_a_zero_tolerance_still_matches_the_key_exactly() -> None:
    assert key_mask(scene(), GREEN, tolerance=0)[0, 0]


# R2.1, R2.2 — the gem survives a flood and does not survive a global.


def test_a_flood_leaves_an_enclosed_key_coloured_region_alone() -> None:
    out, _ = remove(scene(), BgRemoveParams(key=GREEN, tolerance=10, mode="flood"))
    assert out[0, 0, 3] == 0, "the backdrop should be gone"
    assert out[4, 4, 3] == 255, "the gem is not the background"
    assert out[2, 2, 3] == 255


def test_a_global_takes_the_gem_with_it() -> None:
    """Not a bug — it is what `global` means, and why it is not the default."""
    out, _ = remove(scene(), BgRemoveParams(key=GREEN, tolerance=10, mode="global"))
    assert out[0, 0, 3] == 0
    assert out[4, 4, 3] == 0


def test_reachable_from_border_finds_nothing_when_nothing_touches_it() -> None:
    mask = np.zeros((6, 6), dtype=bool)
    mask[2:4, 2:4] = True
    assert not reachable_from_border(mask).any()


def test_reachable_from_border_on_an_empty_mask_is_empty() -> None:
    assert not reachable_from_border(np.zeros((4, 4), dtype=bool)).any()


def test_a_backdrop_that_is_entirely_key_coloured_all_goes() -> None:
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[..., :3] = GREEN
    image[..., 3] = 255
    out, measured = remove(image, BgRemoveParams(key=GREEN, tolerance=10))
    assert measured["opaque_px"] == 0
    assert (out[..., 3] == 0).all()


# R3.1 — alpha is 0 or 255 and nothing between.


def test_every_written_pixel_is_fully_opaque_or_fully_transparent() -> None:
    image = scene()
    # A pixel half way between the subject and the key, which a soft key would feather.
    image[2, 1, :3] = tuple((a + b) // 2 for a, b in zip(GREEN, SKIN, strict=True))
    out, _ = remove(image, BgRemoveParams(key=GREEN, tolerance=80, edge_pass=True))
    assert set(np.unique(out[..., 3]).tolist()) <= {0, 255}


def test_an_input_that_already_had_soft_alpha_comes_out_binary() -> None:
    image = scene()
    image[3, 3, 3] = 128
    out, _ = remove(image, BgRemoveParams(key=GREEN, tolerance=10))
    assert out[3, 3, 3] == 255


# R3.3, R3.4 — despeckle, then trim.


def test_despeckle_drops_a_group_below_the_threshold() -> None:
    opaque = np.zeros((8, 8), dtype=bool)
    opaque[1, 1] = True
    opaque[4:7, 4:7] = True
    kept = despeckle_opaque(opaque, smallest=3)
    assert not kept[1, 1]
    assert kept[5, 5]


def test_despeckle_of_one_keeps_everything() -> None:
    opaque = np.zeros((4, 4), dtype=bool)
    opaque[1, 1] = True
    assert despeckle_opaque(opaque, smallest=1)[1, 1]


def test_trim_shrinks_the_opaque_region_by_a_pixel() -> None:
    opaque = np.zeros((8, 8), dtype=bool)
    opaque[2:6, 2:6] = True
    trimmed = trim(opaque, 1)
    assert not trimmed[2, 2]
    assert trimmed[3, 3]


def test_trim_of_zero_changes_nothing() -> None:
    opaque = np.zeros((4, 4), dtype=bool)
    opaque[1:3, 1:3] = True
    assert np.array_equal(trim(opaque, 0), opaque)


def test_despeckle_judges_the_size_before_the_trim_shrinks_it() -> None:
    """The order is load-bearing, and this is the scene that proves it rather than one that
    passes either way.

    A 1px speck erodes away whichever order runs, so a test built on one says nothing. With
    a 3x3 speck beside a 4x4 subject at `--despeckle 5 --edge-trim 1`: despeckle first keeps
    the subject, because it judged 16 pixels; trim first shrinks the subject to 4 and the
    despeckle then eats **the subject as well**. That is the failure the order prevents —
    not a speck surviving, but `--despeckle 5` silently deleting something much bigger
    than five pixels.
    """
    image = np.zeros((12, 12, 4), dtype=np.uint8)
    image[..., :3] = GREEN
    image[..., 3] = 255
    image[7:11, 7:11, :3] = SKIN  # the subject, 16 px
    image[2:5, 2:5, :3] = SKIN  # the speck, 9 px

    out, _ = remove(image, BgRemoveParams(key=GREEN, tolerance=10, despeckle=5, edge_trim=1))
    assert out[8, 8, 3] == 255, "the subject must survive"

    # The same two steps in the other order keep nothing at all, which is what makes this
    # an order and not a coincidence.
    opaque = ~reachable_from_border(key_mask(image, GREEN, 10))
    assert not despeckle_opaque(trim(opaque, 1), 5).any()


# R3.2 — the cast, not the alpha.


def test_the_edge_pass_takes_the_key_out_of_a_bordering_pixel() -> None:
    image = np.zeros((6, 6, 4), dtype=np.uint8)
    image[..., :3] = GREEN
    image[..., 3] = 255
    image[2:4, 2:4, :3] = SKIN
    # A subject pixel carrying spill: green well above its red and blue.
    image[2, 2, :3] = (90, 200, 80)

    out, _ = remove(image, BgRemoveParams(key=GREEN, tolerance=40, edge_pass=True))
    assert out[2, 2, 3] == 255
    assert out[2, 2, 1] <= max(int(out[2, 2, 0]), int(out[2, 2, 2]))


def test_without_the_edge_pass_the_cast_stays() -> None:
    """It changes colours the caller may have chosen, which is why it is a flag."""
    image = np.zeros((6, 6, 4), dtype=np.uint8)
    image[..., :3] = GREEN
    image[..., 3] = 255
    image[2:4, 2:4, :3] = SKIN
    image[2, 2, :3] = (90, 200, 80)

    out, _ = remove(image, BgRemoveParams(key=GREEN, tolerance=40, edge_pass=False))
    assert tuple(out[2, 2, :3]) == (90, 200, 80)


def test_the_edge_pass_leaves_the_interior_alone() -> None:
    image = scene()
    out, _ = remove(image, BgRemoveParams(key=GREEN, tolerance=10, edge_pass=True))
    assert tuple(out[5, 2, :3]) == SKIN


def test_despill_on_a_frame_with_no_border_is_a_no_op() -> None:
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[..., :3] = SKIN
    image[..., 3] = 255
    opaque = np.ones((4, 4), dtype=bool)
    assert np.array_equal(despill(image, opaque, GREEN), image)


# R4.1 — what the caller is told.


def test_the_counts_add_up_to_the_frame() -> None:
    out, measured = remove(scene(), BgRemoveParams(key=GREEN, tolerance=10))
    assert measured["transparent_px"] + measured["opaque_px"] == out[..., 3].size
    assert measured["opaque_px"] == int((out[..., 3] == 255).sum())


def test_a_trim_past_the_mask_is_clamped_rather_than_run() -> None:
    """`cv2.erode` costs a pass per iteration regardless of image size, so an unclamped call
    is a 1x1 image and a large number away from running for hours. Past the longest side the
    answer stops changing, so the clamp reaches the same result without spending the time."""
    opaque = np.zeros((8, 8), dtype=bool)
    opaque[2:6, 2:6] = True

    assert not trim(opaque, 10_000_000).any()
    assert np.array_equal(trim(opaque, 10_000_000), trim(opaque, 8))


def test_a_subject_touching_the_image_edge_is_not_trimmed_there() -> None:
    """OpenCV treats what is outside the frame as opaque for an erosion, so a silhouette
    running off the edge keeps that edge. That is the right answer — there is no background
    on that side to pull away from — and it is worth pinning, because it is the reason a
    fully opaque frame does not erode at all."""
    opaque = np.ones((6, 6), dtype=bool)
    assert trim(opaque, 3).all()
