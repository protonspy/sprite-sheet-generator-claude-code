"""Which frames of an animation are saying nothing new.

Pure. `curate` reports and, when asked, drops; **which frames an action actually needs is a
judgement and stays out** — that is `sprite-animation`'s, in M4. What is measurable is how
far one frame is from the one before it, and that is all this decides.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Difference:
    """How far one frame is from its predecessor."""

    index: int
    ratio: float
    redundant: bool

    def as_dict(self) -> dict[str, object]:
        return {"index": self.index, "ratio": round(self.ratio, 6), "redundant": self.redundant}


def distance(first: np.ndarray, second: np.ndarray) -> float:
    """The share of pixels that differ, counting alpha.

    A share rather than a count, so one threshold means the same thing on a 32x32 sprite and
    on a 512x512 one. Frames of different sizes are entirely different by definition — they
    cannot be compared pixelwise, and pretending otherwise by resampling one would be
    inventing the answer.
    """
    if first.shape != second.shape:
        return 1.0
    if first.size == 0:
        return 0.0
    return float(np.count_nonzero(np.any(first != second, axis=-1))) / (
        first.shape[0] * first.shape[1]
    )


def differences(frames: list[np.ndarray], threshold: float) -> list[Difference]:
    """Each frame against the one before it (R4.2).

    The first frame is never redundant (R4.4): there is nothing before it to repeat, and a
    set that dropped its own opening frame would start mid-motion.

    Compared against the previous *kept* frame rather than the previous frame outright. A
    slow pan moves a little per frame and a lot over five, and comparing neighbours would
    call every frame redundant and drop the whole pan.
    """
    found: list[Difference] = []
    reference: np.ndarray | None = None
    for index, frame in enumerate(frames):
        if reference is None:
            found.append(Difference(index=index, ratio=1.0, redundant=False))
            reference = frame
            continue
        ratio = distance(reference, frame)
        redundant = ratio < threshold
        found.append(Difference(index=index, ratio=ratio, redundant=redundant))
        if not redundant:
            reference = frame
    return found


def kept(frames: list[np.ndarray], threshold: float) -> list[int]:
    """The indices worth keeping (R4.3)."""
    return [item.index for item in differences(frames, threshold) if not item.redundant]
