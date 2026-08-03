"""Deriving a normal map — specs/normal-maps R1, R2.

The TDD half is the encoding, because a wrong normal map is not visibly wrong: it is a
plausible lavender image either way, and the defect shows up as light falling from the wrong
side in an engine nobody runs during this work. So the assertions are properties — unit
length, flat encodes to the flat normal, a slope and its reverse land on opposite sides of
centre — rather than pixel values read off a run.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core import normal

FLAT = (128, 128, 255)


def flat_image(width: int = 8, height: int = 8, value: int = 120) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = value
    image[:, :, 3] = 255
    return image


def ramp(width: int = 8, height: int = 8) -> np.ndarray:
    """Brightness rising to the right: a surface tilted about the vertical axis."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    for column in range(width):
        image[:, column, :3] = int(column * 255 / max(width - 1, 1))
    image[:, :, 3] = 255
    return image


def decoded(encoded: np.ndarray) -> np.ndarray:
    return encoded[:, :, :3].astype(np.float64) / 255.0 * 2.0 - 1.0


# R1.1, R1.6 — what the encoding has to be true of.


def test_every_encoded_normal_is_a_unit_vector() -> None:
    vectors = decoded(normal.derive(ramp()))

    lengths = np.linalg.norm(vectors, axis=-1)
    assert np.allclose(lengths, 1.0, atol=0.02)


def test_a_flat_surface_encodes_to_the_flat_normal() -> None:
    encoded = normal.derive(flat_image())

    assert np.array_equal(np.unique(encoded[:, :, 0]), np.array([FLAT[0]]))
    assert np.array_equal(np.unique(encoded[:, :, 1]), np.array([FLAT[1]]))
    assert np.array_equal(np.unique(encoded[:, :, 2]), np.array([FLAT[2]]))


def test_a_slope_and_its_reverse_land_on_opposite_sides_of_centre() -> None:
    """The property that catches a sign error, which is the whole failure mode here."""
    rising = normal.derive(ramp())
    falling = normal.derive(ramp()[:, ::-1].copy())

    middle = slice(1, -1)
    assert rising[middle, middle, 0].mean() < FLAT[0]
    assert falling[middle, middle, 0].mean() > FLAT[0]


def test_the_map_is_the_size_of_its_input() -> None:
    assert normal.derive(ramp(11, 7)).shape[:2] == (7, 11)


def test_the_map_keeps_the_input_s_alpha() -> None:
    image = ramp()
    image[0, :, 3] = 0

    encoded = normal.derive(image)

    assert np.array_equal(encoded[:, :, 3], image[:, :, 3])


# R1.3 — strength, and its range.


def test_more_strength_tilts_the_normal_further_from_flat() -> None:
    gentle = decoded(normal.derive(ramp(), strength=0.5))
    steep = decoded(normal.derive(ramp(), strength=4.0))

    middle = slice(1, -1)
    assert abs(steep[middle, middle, 0].mean()) > abs(gentle[middle, middle, 0].mean())


@pytest.mark.parametrize("strength", [0.0, -1.0, normal.MAX_STRENGTH + 1])
def test_a_strength_outside_the_range_is_refused(strength: float) -> None:
    with pytest.raises(ValueError, match="strength"):
        normal.derive(ramp(), strength=strength)


# R1.4 — transparency is a hole, not a colour.


def test_a_transparent_pixel_encodes_flat() -> None:
    image = ramp()
    image[2:5, 2:5, 3] = 0

    encoded = normal.derive(image)

    assert np.array_equal(np.unique(encoded[2:5, 2:5, :3].reshape(-1, 3), axis=0), np.array([FLAT]))


def test_transparent_pixels_do_not_put_a_cliff_around_the_silhouette() -> None:
    """The single most visible way to get this wrong: transparent RGB is usually black, so
    letting it into the window makes every sprite's outline a wall."""
    image = flat_image(12, 12)
    image[:, :, :3] = 200
    image[:, :3, 3] = 0  # a transparent margin down the left

    encoded = normal.derive(image)

    lit = encoded[:, 3:, :3]
    assert np.array_equal(np.unique(lit.reshape(-1, 3), axis=0), np.array([FLAT]))


def test_an_image_that_is_entirely_transparent_is_all_flat() -> None:
    image = np.zeros((6, 6, 4), dtype=np.uint8)

    encoded = normal.derive(image)

    assert np.array_equal(np.unique(encoded[:, :, :3].reshape(-1, 3), axis=0), np.array([FLAT]))


# R2.2 — the other convention.


def test_flip_y_inverts_the_green_channel_and_nothing_else() -> None:
    image = ramp(8, 8).swapaxes(0, 1).copy()  # a slope about the horizontal axis

    up = normal.derive(image)
    down = normal.derive(image, flip_y=True)

    assert np.array_equal(up[:, :, 0], down[:, :, 0])
    assert np.array_equal(up[:, :, 2], down[:, :, 2])
    middle = slice(1, -1)
    assert not np.array_equal(up[middle, middle, 1], down[middle, middle, 1])
    assert np.allclose(
        up[middle, middle, 1].astype(int) + down[middle, middle, 1].astype(int), 255, atol=1
    )


# The two functions `derive` is built from, tested directly rather than only through it.


def test_luminance_weights_green_most_and_blue_least() -> None:
    image = np.zeros((1, 3, 4), dtype=np.uint8)
    image[0, 0, :3] = (255, 0, 0)
    image[0, 1, :3] = (0, 255, 0)
    image[0, 2, :3] = (0, 0, 255)

    values = normal.luminance(image)[0]

    assert values[1] > values[0] > values[2]
    assert np.isclose(values.sum(), 255.0, atol=1.0)


def test_filled_takes_a_transparent_pixel_s_opaque_neighbours() -> None:
    height = np.array([[10.0, 0.0, 30.0]])
    opaque = np.array([[True, False, True]])

    assert normal.filled(height, opaque)[0, 1] == pytest.approx(20.0)


def test_filled_never_reaches_across_the_canvas_edge() -> None:
    """The defect the first version shipped: `np.roll` made the canvas a torus, so a
    transparent pixel at the right edge averaged the *left* edge's art into itself — and
    that value then fed a real pixel's window. R1.4's second clause, violated silently."""
    height = np.array([[200.0, 0.0, 50.0, 0.0]])
    opaque = np.array([[True, False, True, False]])

    out = normal.filled(height, opaque)

    # The last cell's only opaque neighbour is the 50, not the 200 wrapped round from column 0.
    assert out[0, 3] == pytest.approx(50.0)


def test_a_pixel_with_no_opaque_neighbour_gets_a_flat_constant() -> None:
    height = np.zeros((5, 5))
    height[0, 0] = 90.0
    opaque = np.zeros((5, 5), dtype=bool)
    opaque[0, 0] = True

    out = normal.filled(height, opaque)

    assert out[4, 4] == pytest.approx(90.0)  # the opaque mean, not a rolled-in neighbour
    assert np.isfinite(out).all()


def test_art_touching_two_edges_is_not_corrupted_by_the_far_side() -> None:
    """The end-to-end shape of the same defect: a sprite that has been cropped or keyed
    routinely touches more than one edge of its frame."""
    image = np.zeros((3, 4, 4), dtype=np.uint8)
    image[:, 0, :3] = 200
    image[:, 0, 3] = 255
    image[:, 2, :3] = 50
    image[:, 2, 3] = 255

    encoded = normal.derive(image)

    assert not np.array_equal(encoded[1, 2, :3], np.array(FLAT, dtype=np.uint8))


def test_the_fill_is_one_pass_however_wide_the_transparent_margin(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A single opaque pixel in a 400-wide frame used to cost one full pass over the array
    per pixel of margin. The window that consumes this reaches one pixel, so one pass is all
    it can ever need — and that is what keeps a small file from being an hour of CPU."""
    calls = 0
    real_nanmean = np.nanmean

    def counted(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return real_nanmean(*args, **kwargs)

    monkeypatch.setattr(np, "nanmean", counted)
    height = np.zeros((3, 400))
    height[0, 0] = 100.0
    opaque = np.zeros((3, 400), dtype=bool)
    opaque[0, 0] = True

    normal.filled(height, opaque)

    assert calls == 1


def test_a_strength_that_is_not_a_number_is_refused() -> None:
    """click parses `nan` and `inf` as floats quite happily, and every comparison against
    `nan` is False — so the range check has to be the one that rejects it, not a clamp."""
    for strength in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="strength"):
            normal.derive(ramp(), strength=strength)


def test_the_normals_stay_unit_length_at_full_strength() -> None:
    """The tolerance that matters: at strength 1 an unnormalised vector is within 0.02 of
    unit anyway, so this property needs a slope steep enough to tell the two apart."""
    vectors = decoded(normal.derive(ramp(), strength=normal.MAX_STRENGTH))

    assert np.allclose(np.linalg.norm(vectors, axis=-1), 1.0, atol=0.02)
