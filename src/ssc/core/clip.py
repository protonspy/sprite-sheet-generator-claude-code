"""Where a cycle closes, and which frames to take across it.

Arithmetic over frames and nothing else: no file is opened here, which is the split
`core/recover.py` makes and the reason the cycle finder can be tested against a handful of
8x8 arrays. Reading the container is `cli/clip.py`, where the failures are.
"""

from __future__ import annotations

import numpy as np

#: The shortest cycle worth finding, in frames. Frame 1 is always near frame 0 and frame 2
#: is nearly always, so without a floor every clip has a one-frame cycle — the plausible
#: wrong answer, and the one that cuts a walk into a still.
MIN_CYCLE = 3

#: And a floor that grows with the clip, because a cycle is a *share* of a clip somebody
#: generated to hold one. A hundred-frame clip whose motion apparently closes after four
#: frames has been misread; the model was asked for one cycle in four seconds.
MIN_CYCLE_SHARE = 0.25

#: How near the closing frame has to be to the first, as a mean channel difference over
#: 0..1. A clip that loops returns to very nearly the same pixels — the video template asks
#: for a fixed camera and a flat background precisely so that it can. Past this, the honest
#: answer is that nothing returned, rather than the least-far frame dressed up as a cycle.
MAX_RETURN = 0.05


def difference(first: np.ndarray, second: np.ndarray) -> float:
    """How far apart two frames are, as a mean channel difference over 0..1.

    Magnitude rather than the share of pixels that differ, which is what `core/curate.py`
    measures for a different question. Curate asks *has anything changed at all*, and every
    pixel of a frame one shade darker has; this asks *how far from the same picture is it*,
    and one shade darker is very near. Using curate's measure here reads every clip as
    never returning.
    """
    return float(np.mean(np.abs(first.astype(np.int16) - second.astype(np.int16))) / 255.0)


def closes_at(frames: list[np.ndarray]) -> int | None:
    """The index the motion returns to its first frame at, or `None` where it does not.

    The cycle is `frames[:closes_at]` — the closing frame is the opening frame again, so it
    belongs to the next repetition rather than to this one, which is what `positions` then
    leaves out.

    The *first* return rather than the nearest of all of them: a four-second clip holds the
    cycle three times over, and the sheet wants one of them. `argmin` returns the earliest
    of equal minima, which is that.
    """
    if len({frame.shape for frame in frames}) > 1:
        raise ValueError("a clip's frames are all one size; these are not")

    floor = max(MIN_CYCLE, int(-(-len(frames) * MIN_CYCLE_SHARE // 1)))
    if floor >= len(frames):
        return None

    distances = [difference(frames[0], frame) for frame in frames[floor:]]
    nearest = int(np.argmin(distances))
    if distances[nearest] > MAX_RETURN:
        return None
    return floor + nearest


def positions(count: int, over: int) -> list[int]:
    """`count` indices evenly spaced across `over` frames, **excluding the end**.

    The exclusion is the domain fact rather than an off-by-one: a cycle's closing frame is
    its opening frame, and a sheet holding both plays the first pose twice — a stutter at
    the loop point, which is exactly where an animation is looked at.

    Floor division rather than rounding, so the positions never reach `over` and the first
    is always frame 0. A set that started at frame 1 would begin mid-motion.
    """
    if count < 1:
        raise ValueError("a frame set holds at least one frame")
    if count > over:
        raise ValueError(f"{count} frames cannot be taken from {over} frames")
    return [index * over // count for index in range(count)]
