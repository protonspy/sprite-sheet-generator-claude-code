"""Reading a clip into frames.

Separate from `core/clip.py` for the ordinary reason and one specific one: a decoder is
where the failures are — a container that is not one, a codec this build cannot read, a file
that is half written — and keeping it away from the arithmetic means the arithmetic has no
failures to have.

`cv2` decodes it. `opencv-python-headless` is already a direct dependency for connected
components and morphology, so this adds nothing to `docs/stack.md` and the `[cv]` extra is
not involved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ssc.cli.errors import SscError, UsageError
from ssc.cli.frames import MAX_PIXELS, MAX_SET_PIXELS

#: How many frames of a clip this will hold at once. Four seconds at 30fps is 120, and the
#: sources `docs/wiki/generating-animations.md` records generate 80 to 120 — so this is
#: several times the clip anybody samples, and still bounded: every frame is decoded into
#: memory as RGBA before any of them is sampled, and a long clip at a generous size is
#: gigabytes. Refused rather than truncated, because half a clip has half a cycle in it and
#: nothing says which half.
MAX_CLIP_FRAMES = 600


@dataclass(frozen=True)
class Clip:
    """A decoded clip: its frames, and the two facts about the container worth carrying."""

    frames: list[np.ndarray]
    fps: float

    @property
    def seconds(self) -> float:
        return len(self.frames) / self.fps if self.fps > 0 else 0.0


def _number(value: float) -> float:
    """A header field as a number this can compare, or `0`.

    `nan` is the reason this exists rather than `float(x or 0)`. It is truthy, so `or 0`
    keeps it; it survives every `<=` comparison because comparing against `nan` is always
    False; and `int(nan)` raises. That is the same trap `commands/gen.py`'s `check_wait` was
    written to close, arriving here from a container's metadata instead of from a flag.
    """
    return 0.0 if value is None or math.isnan(value) or math.isinf(value) else float(value)


def _too_long(path: Path, what: str) -> UsageError:
    return UsageError(
        "clip-too-long",
        f"{path.name} {what}, past {MAX_CLIP_FRAMES}",
        fix="sample a shorter clip; half a clip holds half a cycle and nothing says which half",
    )


def _too_large(path: Path, width: int, height: int) -> UsageError:
    return UsageError(
        "clip-too-large",
        f"{path.name} is {width}x{height}, past {MAX_PIXELS:,} pixels a frame",
        fix="sample a clip at a size a sprite comes from",
    )


def read_clip(path: Path) -> Clip:
    """Every frame of the clip at `path`, as RGBA (R1.2, R1.3, R1.4).

    `cv2` gives BGR and this project works in RGBA everywhere, so the conversion happens
    once, here, rather than being a thing each caller remembers.
    """
    if not path.is_file():
        raise UsageError(
            "no-input", f"{path} is not a file", fix="point --in at a clip a model returned"
        )

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        # Released on this path too. The destructor would eventually do it, but every other
        # exit from this function releases explicitly and the one that does not is the one
        # somebody copies.
        capture.release()
        raise UsageError(
            "unreadable-clip",
            f"{path.name} could not be opened as a clip",
            fix="check the file is a video this build can read — mp4, webm, mov, mkv",
        )

    frames: list[np.ndarray] = []
    try:
        # The header first, so a clip past a ceiling is refused before it is decoded rather
        # than after. Every one of these is a hint rather than a guarantee — a container can
        # report zero, or lie — so each is checked again against what actually arrives.
        declared = _number(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if declared > MAX_CLIP_FRAMES:
            raise _too_long(path, f"holds {int(declared)} frames")

        width = _number(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = _number(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width * height > MAX_PIXELS:
            raise _too_large(path, int(width), int(height))

        fps = _number(capture.get(cv2.CAP_PROP_FPS))
        pixels = 0.0
        while True:
            ok, bgr = capture.read()
            if not ok:
                break
            if len(frames) >= MAX_CLIP_FRAMES:
                raise _too_long(path, f"holds more than {MAX_CLIP_FRAMES} frames")
            # Against the frame in hand, because the header is the attacker's to write: a
            # container declaring 16x16 and decoding to 16000x16000 is the video shape of the
            # decompression bomb `frames.MAX_PIXELS` exists for.
            frame_height, frame_width = bgr.shape[:2]
            if frame_width * frame_height > MAX_PIXELS:
                raise _too_large(path, frame_width, frame_height)
            pixels += frame_width * frame_height
            if pixels > MAX_SET_PIXELS:
                raise UsageError(
                    "clip-too-large",
                    f"{path.name} comes to over {MAX_SET_PIXELS:,} pixels decoded",
                    fix="sample a shorter clip, or one at a smaller size",
                )
            frames.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA))
    finally:
        capture.release()

    if not frames:
        raise SscError(
            "empty-clip",
            f"{path.name} opened but holds no frames this build can decode",
            fix="check the codec; ssc reads what opencv reads",
        )
    return Clip(frames=frames, fps=fps)
