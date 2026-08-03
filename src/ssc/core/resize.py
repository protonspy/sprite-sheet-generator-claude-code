"""The only resampler in this codebase.

Nearest neighbour is an invariant, not an option (R4.4). Every resize anywhere in the
pipeline — snapping back up to the working size, scaling a recovered frame down to its
cell, rendering a preview — goes through here. Any other resampler reintroduces exactly
the sub-pixel blur `snap` exists to remove, and the damage is invisible at a glance and
obvious at 4x zoom.

`tests/test_no_other_resampler.py` fails the suite if a second one appears.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ResizeParams:
    """The target size, in pixels. There is deliberately no `filter` field."""

    width: int
    height: int


def resize(image: np.ndarray, params: ResizeParams) -> np.ndarray:
    """Resample `image` to `params`, choosing each output pixel from one input pixel.

    Because every output pixel *is* an input pixel, the output can never contain a colour
    the input did not — which is the property the rest of the pipeline depends on.
    """
    if params.width < 1 or params.height < 1:
        raise ValueError(f"size must be positive, got {params.width}x{params.height}")
    if image.ndim < 2:
        raise ValueError(f"expected an image, got an array of {image.ndim} dimension(s)")

    source_height, source_width = image.shape[:2]
    if source_height < 1 or source_width < 1:
        raise ValueError("cannot resize an empty image")

    rows = (np.arange(params.height) * source_height) // params.height
    columns = (np.arange(params.width) * source_width) // params.width
    sampled: np.ndarray = image[rows[:, None], columns]
    return sampled
