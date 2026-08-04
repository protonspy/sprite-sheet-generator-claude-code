"""Seeing an animation before an engine does.

Pure, like everything under `core/`: arrays and numbers in, arrays and numbers out. The GIF
encoding is `cli/preview.py`'s, because a GIF is bytes and this is not the layer that makes
those.

`specs/frame-preview/` in `plans/sprite-normalisation-gate.md` builds `ssc tool preview` on
top of this rather than growing a second renderer. That is why the composition is here and
not inside the command.
"""

from __future__ import annotations

MODES = ("loop", "ping-pong", "reverse")


def order(frames: int, mode: str, section: tuple[int, int] | None = None) -> list[int]:
    """Which frame plays when (R6.1, R6.4).

    `ping-pong` repeats neither end: four frames play `0 1 2 3 2 1`, and the six is the whole
    point of this function. Eight — `0 1 2 3 3 2 1 0` — holds the first and last frame for
    twice as long as every other, which reads as a stutter at each turn. The same argument
    is why the returned list is one cycle rather than a loop: whoever plays it repeats it,
    and a cycle that already repeats its own ends cannot be made not to.

    A section restricts the set first and the mode applies inside it, so `ping-pong` over
    `[2, 5]` turns at 5 rather than at the end of the animation.
    """
    if mode not in MODES:
        raise ValueError(f"{mode!r} is not a playback mode; it is one of {', '.join(MODES)}")
    if frames < 0:
        raise ValueError(f"a set cannot have {frames} frames")

    if section is None:
        first, last = 0, frames - 1
    else:
        first, last = section
        if first < 0 or last < first or last >= frames:
            raise ValueError(
                f"a section of frames {first} to {last} is not inside a set of {frames}"
            )

    forward = list(range(first, last + 1))
    if mode == "reverse":
        return forward[::-1]
    if mode == "ping-pong":
        return forward + forward[-2:0:-1]
    return forward
