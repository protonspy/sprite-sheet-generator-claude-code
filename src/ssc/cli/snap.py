"""Snapping a frame *set*, which is the only way this leaf snaps anything.

The single-frame case is the set of one. Everything interesting here is about R2.2 — that
every frame of a set comes back on one grid — and the reason it is not simply "pass the
same number to each call" is in `specs/pixel-art-conversion/design.md`: the module does not
report the grid it chose, and its override is not the inverse of its output.
"""

from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass
from functools import partial

import numpy as np
from PIL import Image

from ssc.cli.cache import Cache, cache_key
from ssc.cli.frames import Frame, encode
from ssc.cli.meta import digest
from ssc.cli.snapper import Snapper
from ssc.core.resize import ResizeParams, resize


@dataclass(frozen=True)
class SnapParams:
    """Everything that changes the result, and therefore everything in the cache key."""

    colors: int = 16
    pixel_size: float | None = None
    palette: str = ""
    grid: bool = False

    def as_key(self) -> dict[str, object]:
        """What the *cached* artefact depends on, which is not the same as what the command
        depends on. The cache holds the module's raw output; `grid` only decides what is
        done to it afterwards, so including it would turn toggling `--grid` into a miss on
        work that was already done.
        """
        return {
            "colors": self.colors,
            "pixel_size": self.pixel_size,
            "palette": self.palette,
        }


def decode(png: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(png)) as handle:
        return np.array(handle.convert("RGBA"))


def one_grid(sizes: list[tuple[int, int]]) -> tuple[int, int]:
    """The grid most of the set resolved to (R2.2).

    Ties break towards the larger grid, and then on the size itself, so that the answer is
    a function of the set and not of the order it was read in. Losing detail is a decision
    worth being deterministic about — half a set at one size and half at another, snapped
    twice, must not come back different each time.
    """
    counted = Counter(sizes)
    best = max(counted.items(), key=lambda item: (item[1], item[0][0] * item[0][1], item[0]))
    return best[0]


def snap_frames(
    frames: list[Frame],
    params: SnapParams,
    snapper: Snapper,
    cache: Cache | None = None,
) -> tuple[list[Frame], dict[str, object]]:
    """Snap every frame onto one grid. Returns the frames and what was measured.

    One `Snapper` for the whole set: the module is expensive to instantiate and cheap to
    call again, and `snap` is called once per frame of every animation in a project.
    """
    arrived = [(frame.image.shape[1], frame.image.shape[0]) for frame in frames]
    override = 0.0 if params.pixel_size is None else params.pixel_size

    snapped: list[np.ndarray] = []
    reused = 0
    for frame in frames:
        source = encode(frame.image)
        compute = partial(_call, snapper, source, params, override)
        if cache is None:
            snapped.append(decode(compute()))
            continue
        key = cache_key("tool snap", params=params.as_key(), inputs=[digest(source)])
        data, hit = cache.use(key, compute)
        reused += int(hit)
        snapped.append(decode(data))

    grid = one_grid([(image.shape[1], image.shape[0]) for image in snapped])
    on_grid = [
        image
        if (image.shape[1], image.shape[0]) == grid
        else resize(image, ResizeParams(width=grid[0], height=grid[1]))
        for image in snapped
    ]

    if params.grid:
        out = on_grid
    else:
        # Back up to the size each frame arrived at, with the only resampler there is.
        # This is the point of `snap`: the caller gets an image the same size as the one
        # they had, made of real pixels rather than of blurred ones.
        out = [
            resize(image, ResizeParams(width=width, height=height))
            for image, (width, height) in zip(on_grid, arrived, strict=True)
        ]

    measured: dict[str, object] = {
        "grid": {"width": grid[0], "height": grid[1]},
        "frames": len(frames),
        # Reported rather than silent: a set where several frames had to be brought onto
        # the consensus is a set the module read differently frame by frame, and that is
        # worth a caller seeing before it wonders why one frame looks softer.
        "off_consensus": sum(1 for image in snapped if (image.shape[1], image.shape[0]) != grid),
        "reused": reused,
    }
    return [Frame(frame.name, image) for frame, image in zip(frames, out, strict=True)], measured


def _call(snapper: Snapper, png: bytes, params: SnapParams, override: float) -> bytes:
    return snapper.snap(png, colors=params.colors, pixel_size=override, palette=params.palette)
