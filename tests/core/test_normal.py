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
