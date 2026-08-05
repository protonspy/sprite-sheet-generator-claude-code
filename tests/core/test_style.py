"""`style_frames` — quantize a set against a fixed, locked palette.

The assertion comes from the requirement (task 5.1), not the implementation: the palette
is *given*, so every output pixel must be one of the palette's colours — never a computed
fifth colour — and alpha is untouched. This is the difference from `pixelart`, which
*computes* a palette; here the colours are decided already.
"""

from __future__ import annotations

import numpy as np

from ssc.core.style import style_frames


def frame(colours: list[tuple[int, int, int]], *, alpha: int = 255) -> np.ndarray:
    """A 4x4 RGBA frame split into horizontal bands of `colours`."""
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    rows = len(colours)
    for index, colour in enumerate(colours):
        start = index * 4 // rows
        end = (index + 1) * 4 // rows
        image[start:end, :, :3] = colour
    image[..., 3] = alpha
    return image


PALETTE = np.array([(0, 0, 0), (255, 255, 255), (200, 30, 30), (30, 30, 200)], dtype=np.uint8)


def test_every_output_pixel_is_one_of_the_locked_palette_colours() -> None:
    """A frame with colours between palette entries must snap onto an entry, not invent one."""
    # (100, 100, 100) is between black and white; it has to become one or the other.
    images = [frame([(100, 100, 100), (200, 30, 30)])]
    outcome = style_frames(images, PALETTE)

    rgb = outcome.frames[0][..., :3].reshape(-1, 3)
    palette_set = {tuple(int(v) for v in c) for c in PALETTE}
    for pixel in rgb:
        assert tuple(int(v) for v in pixel) in palette_set


def test_alpha_is_left_untouched() -> None:
    """Style maps colour, not transparency — a half-transparent edge is `doctor`'s, not here."""
    images = [frame([(200, 30, 30), (30, 30, 200)], alpha=128)]
    outcome = style_frames(images, PALETTE)

    assert set(int(v) for v in outcome.frames[0][..., 3].flatten()) == {128}


def test_a_region_that_did_not_move_is_identical_across_frames() -> None:
    """The same benefit as `pixelart`'s set-level quantization, for a different reason: the
    palette is fixed, so an unchanged region maps to the same entry in every frame."""
    a = frame([(200, 30, 30), (10, 10, 200)])
    b = frame([(200, 30, 30), (20, 200, 20)])
    outcome = style_frames([a, b], PALETTE)

    assert np.array_equal(outcome.frames[0][:2], outcome.frames[1][:2])


def test_the_measurement_reports_the_locked_palette_and_dither() -> None:
    outcome = style_frames([frame([(200, 30, 30), (30, 30, 200)])], PALETTE)
    assert outcome.measurement["frames"] == 1
    assert outcome.measurement["palette"] == ["000000", "ffffff", "c81e1e", "1e1ec8"]
    assert outcome.measurement["dither"] == "none"
