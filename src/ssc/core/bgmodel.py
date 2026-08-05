"""Taking a background out with a model, under the `[cv]` extra.

The sibling of `ssc.core.bgremove`, which does the same job by chroma key. A key needs a
flat backdrop and answers in microseconds; a model needs neither and answers in seconds
against weights it downloads. Both are free — that is what makes this `tool` rather than
`gen` — and both end the same way, at binary alpha, because a half-transparent fringe is
the `halo` defect `doctor` measures whichever path produced it.

Pure, in the same sense as the rest of `core`: the model is injected as a callable
returning a soft mask, so this module holds the thresholding and the cleanup and never the
import. Where the extra actually lives is `ssc.cli.cvruntime`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ssc.core.bgremove import despeckle_opaque, trim

#: What a model gives back: a soft mask, one float or byte per pixel, high where the
#: subject is. Every model under this leaf is asked for exactly this and nothing else, so a
#: second model is a new name in `MODELS` rather than a new code path.
Matte = Callable[[np.ndarray], np.ndarray]

#: The models this leaf knows, and the `rembg` name each one loads. `birefnet` is the
#: better matte on hair and thin geometry; `rembg`'s default u2net is faster and older.
MODELS = {
    "birefnet": "birefnet-general",
    "rembg": "u2net",
}

#: Where a soft mask becomes opaque. Halfway, deliberately: a threshold tuned per model
#: would be a number nobody could reproduce from the spec.
THRESHOLD = 128


@dataclass(frozen=True)
class MatteParams:
    """What the caller asks of the cleanup, after the model has spoken."""

    edge_trim: int = 0
    despeckle: int = 0


def cut_out(
    image: np.ndarray, matte: np.ndarray, params: MatteParams
) -> tuple[np.ndarray, dict[str, int]]:
    """Apply a model's matte to one frame. Returns the frame and what was measured.

    The matte arrives soft and leaves binary (R3.1). `despeckle` and `edge_trim` are the
    same two operations the chroma path runs, on the same mask, so a caller moving between
    the two paths keeps the flags and their meaning.
    """
    if matte.shape[:2] != image.shape[:2]:
        raise ValueError(
            f"the matte is {matte.shape[1]}x{matte.shape[0]} and the frame is "
            f"{image.shape[1]}x{image.shape[0]}"
        )
    soft = matte.astype(np.float32)
    if soft.max() <= 1.0:
        soft = soft * 255.0

    opaque = soft >= THRESHOLD
    opaque = despeckle_opaque(opaque, params.despeckle)
    opaque = trim(opaque, params.edge_trim)

    out = image.copy()
    out[..., 3] = np.where(opaque, 255, 0).astype(np.uint8)
    return out, {
        "transparent_px": int((~opaque).sum()),
        "opaque_px": int(opaque.sum()),
    }
