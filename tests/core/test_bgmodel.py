"""Applying a model's matte — plan task 9.1, `specs/background-removal/` R5."""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core.bgmodel import MatteParams, cut_out


def frame(width: int = 8, height: int = 8) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., :3] = 200
    image[..., 3] = 255
    return image


def test_a_soft_matte_comes_out_binary() -> None:
    """R3.1 holds whichever path produced the alpha: a fringe is the `halo` defect."""
    matte = np.full((8, 8), 200, dtype=np.uint8)
    matte[0, 0] = 40
    matte[0, 1] = 129

    made, measured = cut_out(frame(), matte, MatteParams())

    assert set(np.unique(made[..., 3]).tolist()) <= {0, 255}
    assert made[0, 0, 3] == 0
    assert made[0, 1, 3] == 255
    assert measured["transparent_px"] == 1
    assert measured["opaque_px"] == 63


def test_a_matte_in_zero_to_one_is_read_the_same_way() -> None:
    """Models differ on whether a mask is bytes or floats; the threshold does not."""
    matte = np.full((8, 8), 0.9, dtype=np.float32)
    matte[3, 3] = 0.1

    made, _ = cut_out(frame(), matte, MatteParams())

    assert made[3, 3, 3] == 0
    assert made[0, 0, 3] == 255


def test_despeckle_and_trim_are_the_same_two_operations_as_the_chroma_path() -> None:
    matte = np.zeros((8, 8), dtype=np.uint8)
    matte[1, 1] = 255  # one lone opaque pixel
    matte[4:8, 4:8] = 255

    made, _ = cut_out(frame(), matte, MatteParams(despeckle=2))

    assert made[1, 1, 3] == 0
    assert made[5, 5, 3] == 255


def test_a_matte_of_another_size_is_refused() -> None:
    with pytest.raises(ValueError):
        cut_out(frame(), np.zeros((4, 4), dtype=np.uint8), MatteParams())
