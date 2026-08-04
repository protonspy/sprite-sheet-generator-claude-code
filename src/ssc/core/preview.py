"""Seeing an animation before an engine does.

Pure, like everything under `core/`: arrays and numbers in, arrays and numbers out. The GIF
encoding is `cli/preview.py`'s, because a GIF is bytes and this is not the layer that makes
those.

`specs/frame-preview/` in `plans/sprite-normalisation-gate.md` builds `ssc tool preview` on
top of this rather than growing a second renderer. That is why the composition is here and
not inside the command.
"""

from __future__ import annotations

import numpy as np

from ssc.core.assemble import check_canvas
from ssc.core.contact import Cell, ContactParams, sheet

MODES = ("loop", "ping-pong", "reverse")

#: How many times a tile is repeated on each axis to show its seams. Two is the smallest
#: number that puts every edge of the tile against a copy of the opposite edge, which is the
#: whole question a tile preview answers.
TILED = 2


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


def tiled(image: np.ndarray, times: int = TILED) -> np.ndarray:
    """The image repeated `times` on each axis, to show what its seams do (R6.3).

    A copy, never a resample: `np.tile` repeats whole pixels, so a preview of a 32x32 tile is
    exactly four copies of it and any seam a reader sees is a seam that is really there.
    """
    if times < 1:
        raise ValueError(f"a tiled preview repeats at least once, got {times}")
    height, width = image.shape[:2]
    check_canvas(width * times, height * times, "the tiled preview")
    return np.tile(image, (times, times, 1))


def contact(frames: list[np.ndarray], columns: int = 0) -> np.ndarray:
    """Every frame on one canvas, each labelled with its index (R6.2).

    The labels are the point: a contact sheet of eight identical-looking idle frames is not
    worth printing unless a reader can say *which* one has the defect. `core.contact` already
    lays out and labels a grid for `sweep`, so this is that, with the frame number as the
    label rather than a parameter value.
    """
    if not frames:
        raise ValueError("there are no frames to lay out")
    return sheet(
        [Cell(image=frame, label=str(number)) for number, frame in enumerate(frames)],
        ContactParams(columns=columns),
    )
