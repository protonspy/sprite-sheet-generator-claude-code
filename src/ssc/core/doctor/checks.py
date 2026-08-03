"""The seven detectors.

Each one is pure — arrays plus a params dataclass in, a `Finding` out — so that
`specs/asset-listing/` can call the same measurement with no CLI, and so every number
here can be checked against an 8x8 array whose defect is known by construction.

Thresholds live in the params dataclasses with documented defaults. The defaults came from
the fixtures in `tests/fixtures/doctor/`, and those fixtures are what a change to a default
has to be argued against.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from ssc.core.doctor.finding import Check, Finding, defect, ok, skipped, warning
from ssc.core.doctor.masks import (
    alpha_mask,
    anchor,
    enclosed_regions,
    has_alpha,
    label_regions,
    reduce_mask,
)


def _rgb(image: np.ndarray) -> np.ndarray:
    return image[:, :, :3] if image.ndim == 3 and image.shape[2] >= 3 else image


# ── pixel_grid ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PixelGridParams:
    #: Above this share of pixels disagreeing with their own cell, the image is not
    #: sitting on the grid it appears to have.
    max_off_grid: float = 0.02


def detect_pixel_size(image: np.ndarray) -> int:
    """The spacing the image's own edges fall on.

    Real pixel art changes colour only at cell boundaries, so the gaps between change
    positions are multiples of the cell. Fake pixel art has a ramp at every block edge,
    which produces gaps of 1 and drags the answer down — which is the point: a small
    detected size next to a high off-grid share is the signature of the defect.
    """
    spacings: list[int] = []
    for axis_image in (image, np.swapaxes(image, 0, 1)):
        flat = axis_image.reshape(axis_image.shape[0], -1)
        changed = np.flatnonzero(np.any(flat[1:] != flat[:-1], axis=1)) + 1
        if changed.size:
            spacings.extend(int(gap) for gap in np.diff(np.concatenate(([0], changed))) if gap > 0)
    if not spacings:
        return int(min(image.shape[:2]))
    return int(Counter(spacings).most_common(1)[0][0])


def off_grid_ratio(image: np.ndarray, pixel_size: int) -> float:
    """The share of pixels differing from the dominant colour of their own cell."""
    if pixel_size <= 1:
        # Every pixel is its own cell, so nothing can disagree with itself. Saying 0.0
        # here would report a blurry image as perfect; the honest answer is that a
        # one-pixel grid means no grid was found.
        return 1.0
    height, width = image.shape[:2]
    rows, columns = height // pixel_size, width // pixel_size
    if rows == 0 or columns == 0:
        return 0.0

    cropped = image[: rows * pixel_size, : columns * pixel_size]
    flat = cropped.reshape(rows, pixel_size, columns, pixel_size, -1)
    cells = flat.transpose(0, 2, 1, 3, 4).reshape(rows * columns, pixel_size * pixel_size, -1)

    mismatched = 0
    for cell in cells:
        colours, counts = np.unique(cell, axis=0, return_counts=True)
        mismatched += int(cell.shape[0] - counts.max())
        del colours
    return mismatched / float(cells.shape[0] * cells.shape[1])


def check_pixel_grid(image: np.ndarray, params: PixelGridParams | None = None) -> Finding:
    params = params or PixelGridParams()
    pixel_size = detect_pixel_size(image)
    ratio = off_grid_ratio(image, pixel_size)
    measurement = {"pixel_size": pixel_size, "off_grid_ratio": round(ratio, 6)}
    if ratio > params.max_off_grid:
        return defect(Check.PIXEL_GRID, fix="ssc tool snap", **measurement)
    return ok(Check.PIXEL_GRID, **measurement)


# ── halo ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HaloParams:
    #: Any semi-transparent pixel is a defect; the tolerance exists only so that a single
    #: stray pixel in a large sheet reads as a warning rather than a failure.
    warn_at: int = 1


def check_halo(image: np.ndarray, params: HaloParams | None = None) -> Finding:
    params = params or HaloParams()
    if not has_alpha(image):
        return skipped(Check.HALO, "the image has no alpha channel")
    alpha = image[:, :, 3]
    count = int(np.count_nonzero((alpha > 0) & (alpha < 255)))
    total = int(alpha.size)
    measurement = {"semi_transparent_px": count, "ratio": round(count / total, 6)}
    if count == 0:
        return ok(Check.HALO, **measurement)
    if count < params.warn_at:
        return warning(Check.HALO, fix="ssc tool bgremove --edge-pass", **measurement)
    return defect(Check.HALO, fix="ssc tool bgremove --edge-pass", **measurement)


# ── palette ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaletteParams:
    #: `None` means "count the colours, judge nothing" — the limit is a project decision
    #: and `specs/style-and-palette/` is where it is made.
    limit: int | None = None
    allowed: tuple[tuple[int, int, int], ...] = ()


def check_palette(image: np.ndarray, params: PaletteParams | None = None) -> Finding:
    params = params or PaletteParams()
    mask = alpha_mask(image)
    opaque = _rgb(image)[mask]
    if opaque.size == 0:
        return skipped(Check.PALETTE, "the image is fully transparent")

    colours = np.unique(opaque.reshape(-1, opaque.shape[-1]), axis=0)
    measurement: dict[str, object] = {"colours": int(colours.shape[0])}

    off_palette = 0
    if params.allowed:
        allowed = np.array(params.allowed, dtype=opaque.dtype)
        matches = (opaque.reshape(-1, 1, opaque.shape[-1]) == allowed.reshape(1, -1, 3)).all(axis=2)
        off_palette = int((~matches.any(axis=1)).sum())
        measurement["off_palette_px"] = off_palette

    over_limit = params.limit is not None and colours.shape[0] > params.limit
    if params.limit is not None:
        measurement["limit"] = params.limit
    if off_palette or over_limit:
        return defect(Check.PALETTE, fix="ssc tool pixelart --colors", **measurement)
    return ok(Check.PALETTE, **measurement)


# ── silhouette ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SilhouetteParams:
    """`cell` is required rather than defaulted: a default here would silently decide the
    project's visual era, which is a project-level decision, not a per-check one."""

    cell: tuple[int, int]
    #: Regions this small at target size are noise rather than a fragment of the body.
    min_fragment_px: int = 2


def check_silhouette(image: np.ndarray, params: SilhouetteParams | None = None) -> Finding:
    if params is None:
        return skipped(Check.SILHOUETTE, "no target cell was given (--cell)")
    if not has_alpha(image):
        return skipped(Check.SILHOUETTE, "the image has no alpha channel")

    width, height = params.cell
    # Reduced first, so a hole that vanishes at the size the sprite is played at was never
    # a defect, and one that survives the reduction is.
    reduced = reduce_mask(alpha_mask(image), width=width, height=height)

    labels, count = label_regions(reduced)
    fragments = sum(
        1 for label in range(1, count + 1) if int((labels == label).sum()) >= params.min_fragment_px
    )
    holes = enclosed_regions(reduced)
    measurement = {"holes": holes, "fragments": fragments, "cell": [width, height]}

    if fragments == 0 or holes or fragments > 1:
        return defect(Check.SILHOUETTE, fix="ssc tool bgremove --tol", **measurement)
    return ok(Check.SILHOUETTE, **measurement)


# ── drift ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DriftParams:
    #: One pixel of movement at working size is invisible; two is a judder.
    max_px: float = 1.0


def check_drift(frames: list[np.ndarray], params: DriftParams | None = None) -> Finding:
    params = params or DriftParams()
    if len(frames) < 2:
        return skipped(Check.DRIFT, "drift needs at least two frames")

    anchors = [anchor(alpha_mask(frame)) for frame in frames]
    present = [point for point in anchors if point is not None]
    if len(present) < 2:
        return skipped(Check.DRIFT, "fewer than two frames have any content")

    array = np.array(present, dtype=float)
    median = np.median(array, axis=0)
    distances = np.hypot(array[:, 0] - median[0], array[:, 1] - median[1])
    worst = float(distances.max())
    measurement = {
        "max_drift_px": round(worst, 3),
        "worst_frame": int(distances.argmax()),
        "frames": len(frames),
    }
    if worst > params.max_px:
        return defect(Check.DRIFT, fix="ssc tool align --anchor feet", **measurement)
    return ok(Check.DRIFT, **measurement)


# ── flicker ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FlickerParams:
    """Re-quantization moves a colour a little; motion moves it a lot. `max_distance` is
    where that line sits, and the fixtures carry both a flickering set and a moving one so
    it has to tell them apart rather than being argued in the abstract."""

    max_distance: int = 48
    #: A handful of wobbling pixels is noise; a region of them is the defect.
    max_pixels: int = 0


def check_flicker(frames: list[np.ndarray], params: FlickerParams | None = None) -> Finding:
    params = params or FlickerParams()
    if len(frames) < 2:
        return skipped(Check.FLICKER, "flicker needs at least two frames")
    if len({frame.shape for frame in frames}) != 1:
        return skipped(Check.FLICKER, "the frames are not all the same size")

    worst, worst_pair = 0, 0
    for index in range(len(frames) - 1):
        first, second = frames[index], frames[index + 1]
        rgb_first, rgb_second = _rgb(first).astype(np.int16), _rgb(second).astype(np.int16)
        distance = np.abs(rgb_first - rgb_second).max(axis=2)

        still = np.ones(distance.shape, dtype=bool)
        if has_alpha(first) and has_alpha(second):
            still = first[:, :, 3] == second[:, :, 3]

        wobbling = int(np.count_nonzero(still & (distance > 0) & (distance <= params.max_distance)))
        if wobbling > worst:
            worst, worst_pair = wobbling, index

    measurement = {"flicker_px": worst, "worst_pair": worst_pair, "frames": len(frames)}
    if worst > params.max_pixels:
        return defect(
            Check.FLICKER, fix="ssc tool pixelart (one palette for the set)", **measurement
        )
    return ok(Check.FLICKER, **measurement)


# ── bleed ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BleedParams:
    """The grid is given, never detected here. Grid auto-detection belongs to
    `specs/frame-recovery/`, and two detectors that could disagree would surface as a
    `bleed` number nobody could reproduce."""

    cols: int
    rows: int
    chroma: tuple[int, int, int] | None = None
    tolerance: int = 16
    _unused: tuple[()] = field(default=(), repr=False)


def _content_mask(sheet: np.ndarray, params: BleedParams) -> np.ndarray:
    if params.chroma is not None:
        distance = np.abs(_rgb(sheet).astype(np.int16) - np.array(params.chroma, dtype=np.int16))
        return distance.max(axis=2) > params.tolerance
    return alpha_mask(sheet)


def check_bleed(sheet: np.ndarray, params: BleedParams | None = None) -> Finding:
    if params is None:
        return skipped(Check.BLEED, "no grid was given (--cols/--rows)")
    if params.cols < 1 or params.rows < 1:
        return skipped(Check.BLEED, "a grid needs at least one column and one row")

    height, width = sheet.shape[:2]
    if height % params.rows or width % params.cols:
        return skipped(
            Check.BLEED,
            f"{width}x{height} does not divide into {params.cols}x{params.rows} whole cells",
        )

    cell_h, cell_w = height // params.rows, width // params.cols
    content = _content_mask(sheet, params)

    touching = 0
    for row in range(params.rows):
        for column in range(params.cols):
            cell = content[
                row * cell_h : (row + 1) * cell_h, column * cell_w : (column + 1) * cell_w
            ]
            # Only boundaries shared with a neighbour count. Content at the sheet's outer
            # edge has nowhere to bleed into.
            edges = (
                (column > 0 and cell[:, 0].any()),
                (column < params.cols - 1 and cell[:, -1].any()),
                (row > 0 and cell[0, :].any()),
                (row < params.rows - 1 and cell[-1, :].any()),
            )
            if any(edges):
                touching += 1

    measurement = {"cells_touching_a_boundary": touching, "cells": params.cols * params.rows}
    if touching:
        return defect(Check.BLEED, fix="ssc tool cut --mode bbox", **measurement)
    return ok(Check.BLEED, **measurement)
