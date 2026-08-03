"""R4.4 — the one resampler, asserted against what nearest neighbour means."""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core import ResizeParams, resize


def sprite() -> np.ndarray:
    """A 2x2 of four distinct colours: enough to see where every output pixel came from."""
    return np.array(
        [[[10, 0, 0, 255], [0, 20, 0, 255]], [[0, 0, 30, 255], [40, 40, 40, 0]]], dtype=np.uint8
    )


def test_an_integer_upscale_replicates_blocks_exactly() -> None:
    """The property `snap` depends on: scaling back up must produce hard edges, not ramps."""
    out = resize(sprite(), ResizeParams(width=4, height=4))
    assert out.shape == (4, 4, 4)
    assert np.array_equal(out[0, 0], out[0, 1])
    assert np.array_equal(out[0, 0], out[1, 1])
    assert np.array_equal(out[0, 0], sprite()[0, 0])
    assert np.array_equal(out[3, 3], sprite()[1, 1])


def test_no_colour_is_invented() -> None:
    """The whole point. An interpolating filter answers this test with new colours."""
    source = np.random.default_rng(3).integers(0, 255, size=(9, 7, 4), dtype=np.uint8)
    out = resize(source, ResizeParams(width=23, height=17))
    source_colours = {tuple(c) for c in source.reshape(-1, 4)}
    assert {tuple(c) for c in out.reshape(-1, 4)} <= source_colours


def test_downscaling_keeps_the_alpha_channel_binary() -> None:
    """A blended edge is the halo defect; nearest neighbour cannot produce one."""
    source = sprite()
    out = resize(source, ResizeParams(width=1, height=1))
    assert out[0, 0, 3] in {0, 255}


def test_the_same_size_is_the_same_image() -> None:
    source = sprite()
    assert np.array_equal(resize(source, ResizeParams(width=2, height=2)), source)


def test_a_greyscale_image_survives() -> None:
    source = np.array([[1, 2], [3, 4]], dtype=np.uint8)
    out = resize(source, ResizeParams(width=4, height=2))
    assert out.shape == (2, 4)
    assert out[0].tolist() == [1, 1, 2, 2]


@pytest.mark.parametrize("size", [(0, 4), (4, 0), (-1, 4)])
def test_a_size_below_one_pixel_is_refused(size: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="positive"):
        resize(sprite(), ResizeParams(width=size[0], height=size[1]))


def test_resizing_something_that_is_not_an_image_is_refused() -> None:
    with pytest.raises(ValueError, match="dimension"):
        resize(np.array([1, 2, 3], dtype=np.uint8), ResizeParams(width=2, height=2))


def test_there_is_no_filter_to_choose() -> None:
    """A params dataclass with a `filter` field is how the invariant would be lost."""
    assert set(ResizeParams.__dataclass_fields__) == {"width", "height"}
