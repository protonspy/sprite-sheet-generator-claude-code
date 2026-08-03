"""Turning art of any origin into true pixel art.

Pure: `ndarray` in, `ndarray` out, parameters in a frozen dataclass, no file and no `click`.

The load-bearing idea is that a **set is converted as a set**. One palette is computed from
every opaque pixel of every frame at once, and each frame is then mapped onto it. Quantizing
frame by frame is what makes a region that never moved change colour between adjacent
frames — the `flicker` defect `doctor` measures — and it cannot be repaired afterwards,
because by then each frame has already been rounded to a different set of colours.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from ssc.core.doctor.masks import label_regions, region_areas

Dither = Literal["none", "ordered", "floyd-steinberg"]

#: The classic 4x4 Bayer matrix, centred on zero. Ordered dithering is a fixed pattern
#: rather than diffused error, which is why it survives being animated: the same input
#: pixel gets the same offset in every frame, so a still region cannot shimmer.
BAYER = (
    np.array(
        [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
        dtype=np.float64,
    )
    + 0.5
) / 16.0 - 0.5

#: A cross, so that "touching" means the same thing here as it does in `label_regions`:
#: 4-connected, because in pixel art a diagonal is a deliberate step and not a join.
CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)

#: How many pixels the palette is computed from. A 200-frame set at 1024x1024 is 200M
#: pixels, and median cut over all of them buys nothing a strided sample does not: the
#: palette follows the colour *distribution*, which a regular sample preserves. Strided
#: rather than random so that two runs over one set agree.
MAX_SAMPLE = 1 << 20

#: Nearest-colour matching is a (pixels x palette) distance matrix, so it is done in
#: chunks: 4M pixels against 256 colours in one array is 12GB, and in chunks it is nothing.
CHUNK = 1 << 16


@dataclass(frozen=True)
class PaletteParams:
    """`fixed` wins over `colors` outright — see `build_palette`."""

    colors: int = 16
    fixed: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)


def opaque_pixels(frames: list[np.ndarray]) -> np.ndarray:
    """Every visible RGB pixel of every frame, as one `(N, 3)` array.

    Transparent pixels are excluded rather than counted (R3.3): a fully transparent pixel's
    RGB is whatever happened to be left behind it, and letting it into the palette spends a
    colour of the budget on something nobody can see.
    """
    collected = [frame[frame[..., 3] > 0][:, :3] for frame in frames if frame.size]
    if not collected:
        return np.zeros((0, 3), dtype=np.uint8)
    return np.concatenate(collected).astype(np.uint8)


def build_palette(frames: list[np.ndarray], params: PaletteParams) -> np.ndarray:
    """One palette for the whole set, as a `(K, 3)` array (R3.1).

    A palette given by the caller is used exactly and nothing is computed (R3.2). The two
    are not a negotiation: naming the colours leaves the budget nothing to decide.
    """
    if params.fixed:
        return np.array(params.fixed, dtype=np.uint8)

    pixels = opaque_pixels(frames)
    if len(pixels) == 0:
        # A set with nothing visible in it. One colour, so that mapping still has something
        # to map onto and an empty animation does not become an error.
        return np.zeros((1, 3), dtype=np.uint8)

    stride = max(1, len(pixels) // MAX_SAMPLE)
    sample = pixels[::stride]

    # Median cut is PIL's; applying one palette to many frames is ours, because `quantize`
    # has no notion of a set. The image is Nx1 because median cut reads the colour
    # distribution and not the geometry.
    strip = Image.fromarray(sample.reshape(-1, 1, 3), mode="RGB")
    quantized = strip.quantize(colors=params.colors, method=Image.Quantize.MEDIANCUT)

    # The indices actually present, not the whole 256-entry table: median cut can return
    # fewer colours than it was asked for, and padding the palette out with the unused
    # tail would hand the caller entries that are all zero and mean nothing.
    flat = quantized.getpalette() or []
    used = [int(index) for index in np.unique(np.array(quantized))]
    return np.array([flat[index * 3 : index * 3 + 3] for index in used], dtype=np.uint8)


def nearest(colours: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """The index of the closest palette entry for each of `colours`, in chunks."""
    reference = palette.astype(np.int32)
    found = np.empty(len(colours), dtype=np.intp)
    for start in range(0, len(colours), CHUNK):
        chunk = colours[start : start + CHUNK].astype(np.int32)
        distances = ((chunk[:, None, :] - reference[None, :, :]) ** 2).sum(axis=2)
        found[start : start + CHUNK] = distances.argmin(axis=1)
    return found


def ordered(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Bayer-dithered mapping: offset each pixel by its cell of the matrix, then round.

    The offset is scaled by the average gap between palette entries, because that is the
    error dithering exists to spread. A fixed offset per position — rather than error
    carried from the previous pixel — is what makes this the mode to reach for on an
    animation: the same pixel is offset the same way in every frame.
    """
    height, width = rgb.shape[:2]
    tile = np.tile(BAYER, (height // 4 + 1, width // 4 + 1))[:height, :width]
    spread = 255.0 / max(len(palette), 1)
    shifted = np.clip(rgb.astype(np.float64) + tile[..., None] * spread, 0, 255)
    mapped: np.ndarray = palette[nearest(shifted.reshape(-1, 3), palette)]
    return mapped.reshape(height, width, 3)


def floyd_steinberg(rgb: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Error-diffused mapping onto exactly `palette`.

    PIL's, not ours: error diffusion is inherently sequential, so a numpy version would be
    a Python loop over every pixel. `quantize(palette=...)` is the one call that dithers
    against a palette somebody else chose, which is precisely this leaf's situation — the
    palette came from the whole set, not from this frame.
    """
    reference = Image.new("P", (1, 1))
    flat = [int(value) for colour in palette for value in colour]
    # `putpalette` wants 256 entries; the unused tail is never indexed because `quantize`
    # only picks from the colours that were given.
    reference.putpalette(flat + [0] * (768 - len(flat)))
    quantized = Image.fromarray(rgb, mode="RGB").quantize(
        palette=reference, dither=Image.Dither.FLOYDSTEINBERG
    )
    return np.array(quantized.convert("RGB"))


def map_to_palette(image: np.ndarray, palette: np.ndarray, dither: Dither = "none") -> np.ndarray:
    """Map a frame's opaque pixels onto `palette`, leaving its alpha alone (R3.3, R3.4).

    Alpha is not quantized and not touched. Pixel art alpha is binary; a semi-transparent
    edge is `halo`, which is `doctor`'s to report and `bgremove`'s to fix, and folding it
    into the colour mapping would hide one defect inside another.

    `none` by default (R3.5): dithering is a deliberate aesthetic, and applying it to art
    that did not ask for it is a change nobody requested.
    """
    out = image.copy()
    visible = image[..., 3] > 0
    if not visible.any():
        return out

    if dither == "none":
        out[visible, :3] = palette[nearest(image[visible][:, :3], palette)]
        return out

    rgb = np.ascontiguousarray(image[..., :3])
    whole = ordered(rgb, palette) if dither == "ordered" else floyd_steinberg(rgb, palette)
    # Only the visible pixels are written back: a dither run over the whole frame is the
    # cheapest way to get one, but what is behind a transparent pixel stays its own
    # business.
    out[visible, :3] = whole[visible]
    return out


def clean_clusters(image: np.ndarray, min_cluster: int) -> np.ndarray:
    """Absorb every group of touching same-coloured pixels smaller than `min_cluster` into
    the colour that most surrounds it (R3.6).

    One pass, deliberately: repeating until nothing is left below the threshold would let
    a gradient dissolve one band at a time into whatever won the first round. A caller who
    wants that runs the command again and can see it happen.

    A group with nothing visible around it — a speck alone on transparency — is left
    alone. There is no surrounding colour to absorb it into, and inventing one would be
    guessing.
    """
    if min_cluster <= 1:
        return image

    out = image.copy()
    visible = image[..., 3] > 0
    rgb = image[..., :3]
    for colour in np.unique(rgb[visible], axis=0):
        same = (rgb == colour).all(axis=2) & visible
        labels, count = label_regions(same)
        if count == 0:
            continue
        for label in np.flatnonzero(region_areas(labels, count) < min_cluster) + 1:
            region = labels == label
            border = cv2.dilate(region.astype(np.uint8), CROSS).astype(bool) & ~region & visible
            neighbours = out[..., :3][border]
            if len(neighbours) == 0:
                continue
            found, counts = np.unique(neighbours, axis=0, return_counts=True)
            out[region, :3] = found[counts.argmax()]
    return out


def outline(image: np.ndarray, colour: tuple[int, int, int]) -> np.ndarray:
    """Draw a one-pixel outline in `colour` around the opaque silhouette (R3.7).

    Outside the silhouette rather than inside it, which is what "around" means and what
    makes the shape read at a distance — but it grows the frame's content by a pixel, so a
    silhouette already touching the edge has its outline clipped there. `tool expand` is
    the command that buys the margin first.
    """
    out = image.copy()
    body = image[..., 3] > 0
    if not body.any():
        return out
    ring = cv2.dilate(body.astype(np.uint8), CROSS).astype(bool) & ~body
    out[ring, :3] = colour
    out[ring, 3] = 255
    return out
