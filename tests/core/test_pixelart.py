"""One palette for a whole set — specs/pixel-art-conversion R3.1, R3.2, R3.3.

Written before the code (TDD), because this is the structural fix for `flicker` and its
failure mode is output that looks entirely plausible: quantize each frame on its own and a
region that never moved changes colour between adjacent frames. `doctor` measures that
defect; nothing removes it afterwards, because by then the information is gone.

The assertions come from the requirement, not from the implementation: what matters is that
an unchanged region is *byte-identical* across frames, not which colours the quantizer
happened to pick.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.pixelart import (
    PaletteParams,
    build_palette,
    clean_clusters,
    map_to_palette,
    outline,
)


def frame(colours: list[tuple[int, int, int]], *, alpha: int = 255) -> np.ndarray:
    """A 4x4 RGBA frame: the top half is `colours[0]`, the bottom half `colours[1]`."""
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[:2, :, :3] = colours[0]
    image[2:, :, :3] = colours[1]
    image[..., 3] = alpha
    return image


# R3.1 — one palette across the set, which is what stops flicker.


def test_a_region_that_did_not_move_is_identical_across_frames() -> None:
    """The whole point. The top half is the same in both frames and must come back the
    same; only the bottom half differs."""
    frames = [frame([(200, 30, 30), (10, 10, 200)]), frame([(200, 30, 30), (20, 200, 20)])]
    palette = build_palette(frames, PaletteParams(colors=4))
    mapped = [map_to_palette(image, palette) for image in frames]

    assert np.array_equal(mapped[0][:2], mapped[1][:2])


def test_the_palette_is_computed_from_every_frame_not_just_the_first() -> None:
    """A colour that appears only in the last frame still has to be representable, or that
    frame is mapped onto colours chosen without it."""
    frames = [frame([(255, 0, 0), (255, 0, 0)]), frame([(0, 0, 255), (0, 0, 255)])]
    palette = build_palette(frames, PaletteParams(colors=2))

    assert len(palette) == 2
    reds = np.abs(palette.astype(int) - [255, 0, 0]).sum(axis=1).min()
    blues = np.abs(palette.astype(int) - [0, 0, 255]).sum(axis=1).min()
    assert reds < 30 and blues < 30


def test_the_palette_never_exceeds_the_budget() -> None:
    frames = [frame([(i * 20, 255 - i * 20, i * 7), (i, i, i)]) for i in range(1, 12)]
    palette = build_palette(frames, PaletteParams(colors=5))
    assert len(palette) <= 5


def test_a_mapped_frame_uses_only_palette_colours() -> None:
    frames = [frame([(200, 30, 30), (10, 10, 200)])]
    palette = build_palette(frames, PaletteParams(colors=4))
    mapped = map_to_palette(frames[0], palette)

    used = {tuple(colour) for colour in mapped[..., :3].reshape(-1, 3)}
    assert used <= {tuple(colour) for colour in palette}


# R3.2 — a given palette is used exactly, and nothing is computed.


def test_a_given_palette_is_used_exactly() -> None:
    fixed = ((13, 43, 69), (255, 236, 214))
    frames = [frame([(200, 30, 30), (10, 10, 200)])]
    palette = build_palette(frames, PaletteParams(fixed=fixed))

    assert {tuple(colour) for colour in palette} == set(fixed)


def test_a_given_palette_ignores_the_colour_budget() -> None:
    """`--palette` and `--colors` together are not a negotiation: the caller named the
    colours, so the budget has nothing left to decide."""
    fixed = ((0, 0, 0), (255, 255, 255), (255, 0, 0))
    palette = build_palette([frame([(1, 2, 3), (4, 5, 6)])], PaletteParams(colors=2, fixed=fixed))
    assert len(palette) == 3


# R3.3 — alpha is not quantized and not touched.


def test_alpha_comes_back_unchanged() -> None:
    image = frame([(200, 30, 30), (10, 10, 200)])
    image[0, 0, 3] = 0
    image[1, 1, 3] = 128
    palette = build_palette([image], PaletteParams(colors=4))
    mapped = map_to_palette(image, palette)

    assert np.array_equal(mapped[..., 3], image[..., 3])


def test_a_transparent_pixel_does_not_reach_the_palette() -> None:
    """A fully transparent pixel's RGB is whatever was left behind it. Letting it into the
    palette spends a colour of the budget on something nobody can see."""
    image = frame([(255, 0, 255), (10, 10, 200)])
    image[:2, :, 3] = 0

    palette = build_palette([image], PaletteParams(colors=2))
    magenta = np.abs(palette.astype(int) - [255, 0, 255]).sum(axis=1).min()
    assert magenta > 60


def test_a_frame_with_nothing_opaque_still_maps() -> None:
    """An empty frame is a legitimate frame of an animation, and it must not take the
    whole set down with it."""
    image = frame([(0, 0, 0), (0, 0, 0)], alpha=0)
    palette = build_palette([image, frame([(200, 30, 30), (10, 10, 200)])], PaletteParams(colors=2))
    mapped = map_to_palette(image, palette)

    assert np.array_equal(mapped[..., 3], image[..., 3])


# R3.4, R3.5 — dithering when asked, and not otherwise.


def flat(colour: tuple[int, int, int], size: int = 8) -> np.ndarray:
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[..., :3] = colour
    image[..., 3] = 255
    return image


BLACK_AND_WHITE = np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)


def used_colours(image: np.ndarray) -> set[tuple[int, ...]]:
    return {tuple(colour) for colour in image[..., :3].reshape(-1, 3)}


def test_without_dithering_a_flat_midtone_becomes_one_colour() -> None:
    mapped = map_to_palette(flat((128, 128, 128)), BLACK_AND_WHITE)
    assert len(used_colours(mapped)) == 1


@pytest.mark.parametrize("mode", ["ordered", "floyd-steinberg"])
def test_dithering_a_flat_midtone_uses_both_ends_of_the_palette(mode: str) -> None:
    """The point of dithering: a colour the palette cannot hold is approximated by mixing
    the ones it can."""
    mapped = map_to_palette(flat((128, 128, 128)), BLACK_AND_WHITE, mode)  # type: ignore[arg-type]
    assert used_colours(mapped) == {(0, 0, 0), (255, 255, 255)}


@pytest.mark.parametrize("mode", ["none", "ordered", "floyd-steinberg"])
def test_no_mode_invents_a_colour_outside_the_palette(mode: str) -> None:
    mapped = map_to_palette(flat((90, 160, 40)), BLACK_AND_WHITE, mode)  # type: ignore[arg-type]
    assert used_colours(mapped) <= {(0, 0, 0), (255, 255, 255)}


@pytest.mark.parametrize("mode", ["none", "ordered", "floyd-steinberg"])
def test_no_mode_touches_alpha(mode: str) -> None:
    image = flat((128, 128, 128))
    image[0, 0, 3] = 0
    image[1, 1, 3] = 77
    mapped = map_to_palette(image, BLACK_AND_WHITE, mode)  # type: ignore[arg-type]
    assert np.array_equal(mapped[..., 3], image[..., 3])


def test_ordered_dithering_is_positional_so_a_still_region_cannot_shimmer() -> None:
    """Why `ordered` exists next to `floyd-steinberg`: the same pixel gets the same offset
    in every frame, so an unchanged region is unchanged after dithering too."""
    first, second = flat((128, 128, 128)), flat((128, 128, 128))
    second[4:] = 0
    a = map_to_palette(first, BLACK_AND_WHITE, "ordered")
    b = map_to_palette(second, BLACK_AND_WHITE, "ordered")
    assert np.array_equal(a[:4], b[:4])


# R3.6 — orphan clusters are absorbed by what surrounds them.


def test_a_speck_is_absorbed_by_the_colour_around_it() -> None:
    image = flat((0, 0, 0), size=8)
    image[4, 4, :3] = (255, 255, 255)
    cleaned = clean_clusters(image, min_cluster=2)
    assert tuple(cleaned[4, 4, :3]) == (0, 0, 0)


def test_a_group_at_the_threshold_survives() -> None:
    image = flat((0, 0, 0), size=8)
    image[4, 4, :3] = (255, 255, 255)
    image[4, 5, :3] = (255, 255, 255)
    cleaned = clean_clusters(image, min_cluster=2)
    assert tuple(cleaned[4, 4, :3]) == (255, 255, 255)


def test_min_cluster_of_one_changes_nothing() -> None:
    image = flat((0, 0, 0), size=8)
    image[4, 4, :3] = (255, 255, 255)
    assert np.array_equal(clean_clusters(image, min_cluster=1), image)


def test_a_speck_alone_on_transparency_is_left_alone() -> None:
    """Nothing surrounds it, so there is no colour to absorb it into, and inventing one
    would be guessing."""
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[4, 4] = (255, 0, 0, 255)
    cleaned = clean_clusters(image, min_cluster=4)
    assert tuple(cleaned[4, 4]) == (255, 0, 0, 255)


def test_cleaning_never_touches_alpha() -> None:
    image = flat((0, 0, 0), size=8)
    image[4, 4, :3] = (255, 255, 255)
    image[0, 0, 3] = 0
    cleaned = clean_clusters(image, min_cluster=3)
    assert np.array_equal(cleaned[..., 3], image[..., 3])


# R3.7 — the outline goes around the silhouette.


def test_an_outline_surrounds_the_body_without_replacing_it() -> None:
    image = np.zeros((6, 6, 4), dtype=np.uint8)
    image[2:4, 2:4] = (200, 30, 30, 255)
    outlined = outline(image, (0, 0, 0))

    assert tuple(outlined[2, 2]) == (200, 30, 30, 255)
    assert tuple(outlined[1, 2]) == (0, 0, 0, 255)
    assert tuple(outlined[0, 0]) == (0, 0, 0, 0)


def test_an_outline_is_one_pixel_thick() -> None:
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[3:5, 3:5] = (200, 30, 30, 255)
    outlined = outline(image, (0, 0, 0))
    assert tuple(outlined[1, 3]) == (0, 0, 0, 0)


def test_an_empty_frame_gets_no_outline() -> None:
    image = np.zeros((6, 6, 4), dtype=np.uint8)
    assert np.array_equal(outline(image, (0, 0, 0)), image)
