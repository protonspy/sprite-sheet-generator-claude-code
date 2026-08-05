"""Recolouring — map one palette onto another, position by position.

Pure: `ndarray` in, `ndarray` out, two equal-length palettes, no file and no `click`.

The point (task 5.3) is that a red slime and a blue slime are one asset and a colour map
rather than two generations. A frame already quantized against the *source* palette has
each pixel at one of its colours; recolouring finds that colour's position and writes the
*target* palette's colour at the same position. The two palettes are aligned by the
caller — position 0 of `from` maps to position 0 of `to` — which is what makes a colour
map a deliberate thing rather than a nearest-colour guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ssc.core.pixelart import nearest


@dataclass(frozen=True)
class RecolourOutcome:
    """What recolouring a set produced, plus what it measured."""

    frames: list[np.ndarray]
    measurement: dict[str, Any] = field(default_factory=dict)


def recolour_frames(
    images: list[np.ndarray], source: np.ndarray, target: np.ndarray
) -> RecolourOutcome:
    """Map every frame's pixels from `source` to `target`, position by position.

    Each visible pixel is matched to its nearest `source` entry (the frames are assumed
    already quantized against `source`, so this is an exact lookup in practice, but
    nearest keeps a frame that drifted honest). The index found picks the same position
    out of `target`. Alpha is untouched: recolour changes colour, not shape.
    """
    converted = [recolour_frame(image, source, target) for image in images]
    return RecolourOutcome(
        frames=converted,
        measurement={
            "frames": len(converted),
            "from": [f"{r:02x}{g:02x}{b:02x}" for r, g, b in source],
            "to": [f"{r:02x}{g:02x}{b:02x}" for r, g, b in target],
        },
    )


def recolour_frame(image: np.ndarray, source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Recolour one frame, leaving alpha alone."""
    out = image.copy()
    visible = image[..., 3] > 0
    if not visible.any():
        return out
    indices = nearest(image[visible][:, :3], source)
    out[visible, :3] = target[indices]
    return out
