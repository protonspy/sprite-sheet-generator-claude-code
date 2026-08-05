"""Applying a project-locked palette to a frame set.

Pure: `ndarray` in, `ndarray` out, the palette a fixed `(K, 3)` array, no file and no
`click`. The palette is *given* — locked in `palette.json` by `tool style --preset` — so
unlike `pixelart`, nothing is computed from the set: every frame is mapped onto the same
fixed colours. That is the point of locking it: two assets generated a week apart agree
because they were quantized against one palette nobody re-picks per call.

Dithering lives here too, but as a workspace decision (task 5.2 records it under
`style:` in `ssc.yaml`), never a per-call argument — see ``docs/wiki/pages/agent-workflow.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ssc.core.pixelart import Dither, map_to_palette


@dataclass(frozen=True)
class StyleOutcome:
    """What mapping a set onto a locked palette produced, plus what it measured."""

    frames: list[np.ndarray]
    measurement: dict[str, Any] = field(default_factory=dict)


def style_frames(
    images: list[np.ndarray], palette: np.ndarray, dither: Dither = "none"
) -> StyleOutcome:
    """Map every frame onto the one locked `palette`, leaving alpha untouched.

    The palette is fixed, so this is a straight per-frame `map_to_palette` rather than
    the set-level `build_palette` of `pixelart`: there is nothing to compute, and applying
    one chosen palette to a set is exactly what ``map_to_palette`` is for. Dither is the
    palette's own property (default none), not a knob on this call.
    """
    converted = [map_to_palette(image, palette, dither) for image in images]
    colours = [f"{r:02x}{g:02x}{b:02x}" for r, g, b in palette]
    return StyleOutcome(
        frames=converted,
        measurement={"frames": len(converted), "palette": colours, "dither": dither},
    )
