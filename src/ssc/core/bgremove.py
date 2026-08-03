"""Taking a background out by chroma key.

Pure: `ndarray` in, `ndarray` out, parameters in a frozen dataclass.

Two things here are decisions rather than mechanics, and both are in
`specs/background-removal/design.md`. **Flood is the default**, because a green gem inside a
character is not the background and matching every key-coloured pixel eats it. And **alpha
comes out binary**, because a half-transparent fringe is the `halo` defect `doctor` measures
— a tool whose output failed this project's own detector would be the wrong kind of clever.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from ssc.core.doctor.masks import label_regions, region_areas

Mode = Literal["flood", "global"]

#: The two backdrops a model is actually asked for. Named rather than remembered: nobody
#: should have to recall that "green screen" is `00b140` to take a background out.
PRESETS: dict[str, tuple[int, int, int]] = {
    "green": (0x00, 0xB1, 0x40),
    "magenta": (0xFF, 0x00, 0xFF),
}

CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)


@dataclass(frozen=True)
class BgRemoveParams:
    key: tuple[int, int, int] = PRESETS["green"]
    tolerance: int = 60
    mode: Mode = "flood"
    edge_pass: bool = False
    edge_trim: int = 0
    despeckle: int = 0


def key_mask(image: np.ndarray, key: tuple[int, int, int], tolerance: int) -> np.ndarray:
    """`True` where the pixel is within `tolerance` of the key colour (R1.3).

    Plain Euclidean distance in RGB. Real chroma keying separates luma from chroma so that a
    shadowed green and a lit green read as one colour, and this deliberately does not: the
    input is a model's flat backdrop or a generated board rather than filmed footage, and
    the tolerance is a caller's dial rather than an inference. Changing that later is a
    change inside this function and nowhere else, which is why it is on its own.
    """
    difference = image[..., :3].astype(np.int32) - np.array(key, dtype=np.int32)
    distance = np.sqrt((difference**2).sum(axis=2))
    return distance <= tolerance


def reachable_from_border(mask: np.ndarray) -> np.ndarray:
    """The parts of `mask` connected to the image border (R2.1).

    This is the whole argument for `flood` being the default: a key-coloured region the
    subject encloses — a green gem, a magenta window — is not background, and only its
    connection to the border can tell the difference.
    """
    labels, count = label_regions(mask)
    if count == 0:
        return np.zeros_like(mask)
    touching = np.unique(np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1])))
    keep = touching[touching > 0]
    if keep.size == 0:
        return np.zeros_like(mask)
    return np.isin(labels, keep)


def despeckle_opaque(opaque: np.ndarray, smallest: int) -> np.ndarray:
    """Drop opaque groups below `smallest` pixels (R3.4).

    Before the trim rather than after: trimming first turns a speck into a smaller speck
    instead of removing it, so the two are not commutative and the order is the design.
    """
    if smallest <= 1:
        return opaque
    labels, count = label_regions(opaque)
    if count == 0:
        return opaque
    keep = np.flatnonzero(region_areas(labels, count) >= smallest) + 1
    return np.isin(labels, keep)


def trim(opaque: np.ndarray, pixels: int) -> np.ndarray:
    """Shrink the opaque region by `pixels` (R3.3)."""
    if pixels <= 0:
        return opaque
    eroded: np.ndarray = cv2.erode(opaque.astype(np.uint8), CROSS, iterations=pixels).astype(bool)
    return eroded


def despill(image: np.ndarray, opaque: np.ndarray, key: tuple[int, int, int]) -> np.ndarray:
    """Take the key's cast out of the pixels bordering the transparent region (R3.2).

    Not an alpha operation — R3.1 already made alpha binary, so what is left to fix is
    *colour*: a pixel that was partly key-coloured keeps a green or magenta tint that reads
    as a halo to a person even when `doctor` sees clean alpha.

    The key's dominant channel is clamped down to the strongest of the other two, which is
    the standard despill. It is a flag and not the default because it changes colours the
    caller may have chosen.
    """
    out = image.copy()
    border = cv2.dilate((~opaque).astype(np.uint8), CROSS).astype(bool) & opaque
    if not border.any():
        return out

    channel = int(np.argmax(key))
    others = [index for index in range(3) if index != channel]
    edge = out[border][:, :3].astype(np.int32)
    ceiling = edge[:, others].max(axis=1)
    edge[:, channel] = np.minimum(edge[:, channel], ceiling)
    out[border, :3] = edge.astype(np.uint8)
    return out


def remove(image: np.ndarray, params: BgRemoveParams) -> tuple[np.ndarray, dict[str, int]]:
    """Key the background out of one frame. Returns the frame and what was measured.

    The order — key, flood or global, despeckle, trim, despill — is in the design, and each
    step but the first two is skipped unless asked for.
    """
    keyed = key_mask(image, params.key, params.tolerance)
    background = reachable_from_border(keyed) if params.mode == "flood" else keyed

    opaque = ~background
    opaque = despeckle_opaque(opaque, params.despeckle)
    opaque = trim(opaque, params.edge_trim)

    out = image.copy()
    if params.edge_pass:
        out = despill(out, opaque, params.key)

    # Binary, always (R3.1). Nothing downstream has to wonder what a 200 means.
    out[..., 3] = np.where(opaque, 255, 0).astype(np.uint8)
    return out, {
        "transparent_px": int((~opaque).sum()),
        "opaque_px": int(opaque.sum()),
    }
