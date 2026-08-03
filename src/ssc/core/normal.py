"""Deriving a normal map from finished art.

Pure. The whole module is an inference and says so: the art never carried a height field, so
brightness stands in for one. Where that inference is wrong — art with its own painted
shadows — the map describes the painting's lighting rather than the surface, which is
recorded in `specs/normal-maps/` rather than filtered out here.
"""

from __future__ import annotations

import warnings

import numpy as np

#: Below this the map is a solid colour and the command has silently done nothing useful;
#: above it the normals are so tilted that every surface faces sideways. Both ends are
#: refusals rather than clamps, because a caller who typed 0 meant something.
MIN_STRENGTH = 0.01
MAX_STRENGTH = 32.0

#: The encoded normal of a surface facing straight out: (0, 0, 1) through `v * 0.5 + 0.5`.
FLAT = (128, 128, 255)

#: Rec. 601. The same weights `doctor` uses, so "brighter" means one thing in this project.
LUMA = (0.299, 0.587, 0.114)


def luminance(image: np.ndarray) -> np.ndarray:
    """Perceived brightness, standing in for height (R1.2).

    `float32` here and everywhere below. The values are 0..255 and the arithmetic is a
    weighted sum and a Sobel, so single precision is far more than this needs — and the
    intermediates are several arrays the size of the image plus an eight- and a nine-deep
    stack, which at `frames.MAX_PIXELS` is the difference between a few gigabytes and twice
    that.
    """
    rgb = image[:, :, :3].astype(np.float32)
    weighted = rgb[:, :, 0] * LUMA[0] + rgb[:, :, 1] * LUMA[1] + rgb[:, :, 2] * LUMA[2]
    return np.asarray(weighted, dtype=np.float32)


def filled(height: np.ndarray, opaque: np.ndarray) -> np.ndarray:
    """The height field with transparent pixels taking their opaque neighbours' value (R1.4).

    A transparent pixel's RGB is usually black and always meaningless. Left in the window it
    puts a cliff around every sprite's silhouette, which is the most visible way to get this
    wrong — the outline lights like a wall. Filling instead of masking is what makes the
    slope at the edge of the art the slope *of* the art.

    **One dilation, and one is provably enough.** Only a transparent pixel *inside* an opaque
    pixel's 3x3 Sobel window can affect that pixel's slope, and every such pixel is a direct
    neighbour of an opaque one — so it is filled by this single pass. Anything still unfilled
    is two or more pixels from any art, cannot reach an opaque window, and is overwritten
    with the flat normal on the way out regardless; a constant is all it needs to be.

    The first version propagated in a loop until nothing was left, which was two defects at
    once. It used `np.roll`, whose wraparound let a value from the far edge of the canvas
    bleed into a real pixel's window — R1.4's own second clause, violated. And the loop ran
    once per pixel of transparent margin, so a tall thin image with one opaque pixel took
    millions of passes over the whole array: hours, from a file that is nothing on disk.
    """
    if not opaque.any():
        return np.zeros_like(height)

    known = np.where(opaque, height, np.nan)
    # Padded slices, never `np.roll`: the edge of the canvas is an edge, not a seam onto the
    # opposite side. All eight neighbours, because the window that consumes this has eight.
    padded = np.pad(known, 1, mode="constant", constant_values=np.nan)
    rows, columns = height.shape
    neighbours = np.stack(
        [
            padded[dy : dy + rows, dx : dx + columns]
            for dy in range(3)
            for dx in range(3)
            if (dy, dx) != (1, 1)
        ]
    )
    # A pixel with no opaque neighbour at all averages an empty slice. That is the expected
    # case for most of a sparse frame, not a problem, and the NaN it yields is exactly the
    # "still unknown" marker the fallback below reads.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        spread = np.nanmean(neighbours, axis=0)

    out = np.where(np.isnan(known), spread, known)
    return np.nan_to_num(out, nan=float(height[opaque].mean())).astype(np.float32)


def slopes(height: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The Sobel gradients, x then y.

    Sobel rather than a plain difference because a one-pixel difference on pixel art is all
    edge and no surface: the smoothing across the perpendicular axis is what makes a block
    read as a facet rather than as four cliffs.
    """
    padded = np.pad(height, 1, mode="edge")
    windows = np.stack(
        [
            padded[dy : dy + height.shape[0], dx : dx + height.shape[1]]
            for dy in range(3)
            for dx in range(3)
        ]
    )
    kernel_x = np.array([-1.0, 0.0, 1.0, -2.0, 0.0, 2.0, -1.0, 0.0, 1.0], dtype=np.float32)
    kernel_y = np.array([-1.0, -2.0, -1.0, 0.0, 0.0, 0.0, 1.0, 2.0, 1.0], dtype=np.float32)
    dx = np.tensordot(kernel_x, windows, axes=(0, 0))
    dy = np.tensordot(kernel_y, windows, axes=(0, 0))
    return dx / np.float32(8.0), dy / np.float32(8.0)


def derive(image: np.ndarray, *, strength: float = 1.0, flip_y: bool = False) -> np.ndarray:
    """The normal map for one image (R1.1, R1.2, R1.3, R1.6, R2.2).

    Same size as its input, carrying its alpha, so an engine sampling outside the sprite gets
    nothing rather than a flat blue rectangle.
    """
    if not MIN_STRENGTH <= strength <= MAX_STRENGTH:
        raise ValueError(
            f"a strength of {strength} is outside {MIN_STRENGTH}..{MAX_STRENGTH}: "
            "at zero every normal is flat and the map says nothing"
        )

    alpha = image[:, :, 3] if image.shape[2] > 3 else np.full(image.shape[:2], 255, np.uint8)
    opaque = alpha > 0
    dx, dy = slopes(filled(luminance(image), opaque))

    # Height *rises* with brightness, and a normal points away from the surface — so the
    # slope's sign is inverted going into the vector. Getting this backwards is the failure
    # this leaf's TDD task exists to catch: it lights every sprite from the wrong side and
    # looks entirely plausible.
    vectors = np.stack(
        [
            -dx * strength / 255.0,
            (dy if flip_y else -dy) * strength / 255.0,
            np.ones_like(dx),
        ],
        axis=-1,
    )
    vectors /= np.linalg.norm(vectors, axis=-1, keepdims=True)

    out = np.zeros((*image.shape[:2], 4), dtype=np.uint8)
    out[:, :, :3] = np.clip(np.rint((vectors * 0.5 + 0.5) * 255), 0, 255).astype(np.uint8)
    out[:, :, 3] = alpha
    # A transparent pixel has no surface, so it gets the flat normal rather than whatever the
    # filled height field implied there.
    out[~opaque, :3] = FLAT
    return out
