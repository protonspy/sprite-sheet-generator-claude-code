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
from dataclasses import dataclass

import numpy as np

from ssc.core.doctor.finding import Check, Finding, defect, ok, skipped, warning
from ssc.core.doctor.masks import (
    alpha_mask,
    anchor,
    enclosed_regions,
    has_alpha,
    label_regions,
    reduce_mask,
    region_areas,
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
        # Every pixel is its own cell, so nothing can disagree with itself, and the
        # literal share would be 0.0 — a blurry image reported as perfect. A finished
        # asset in this pipeline is always nearest-neighbour-upscaled to a real pixel size
        # (docs/wiki/pixel-snapping.md: 16, 32, 48-64, 96+), so a detected size of one
        # cannot occur on a legitimate one. Reporting it as maximally off-grid is the
        # honest reading of that invariant rather than a judgement.
        return 1.0
    height, width = image.shape[:2]
    rows, columns = height // pixel_size, width // pixel_size
    if rows == 0 or columns == 0:
        return 0.0

    cropped = image[: rows * pixel_size, : columns * pixel_size]
    flat = cropped.reshape(rows, pixel_size, columns, pixel_size, -1)
    cells = flat.transpose(0, 2, 1, 3, 4).reshape(rows * columns, pixel_size * pixel_size, -1)

    # One pass over every cell at once. A Python loop here is a denial-of-service path:
    # the cell count is (h/p)*(w/p) with `p` read off the image itself, so a crafted fine
    # checkerboard produces tens of millions of iterations from a file that is small on
    # disk.
    packed = np.zeros(cells.shape[:2], dtype=np.uint64)
    for channel in range(cells.shape[2]):
        packed = (packed << np.uint64(8)) | cells[:, :, channel].astype(np.uint64)
    packed.sort(axis=1)
    per_cell = packed.shape[1]
    starts = np.ones_like(packed, dtype=bool)
    starts[:, 1:] = packed[:, 1:] != packed[:, :-1]

    # Run lengths without a loop: each run ends where the next one starts, except the last
    # run of a cell, which ends at the cell boundary.
    cell_index, position = np.nonzero(starts)
    next_position = np.append(position[1:], per_cell)
    last_in_cell = np.append(cell_index[1:] != cell_index[:-1], True)
    lengths = np.where(last_in_cell, per_cell - position, next_position - position)

    dominant = np.zeros(cells.shape[0], dtype=np.int64)
    np.maximum.at(dominant, cell_index, lengths)
    mismatched = int((per_cell - dominant).sum())
    return mismatched / float(cells.shape[0] * per_cell)


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
    fragments = int((region_areas(labels, count) >= params.min_fragment_px).sum())
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


# ── seam ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SeamParams:
    #: How many times the image's own neighbouring-line difference the wrap may differ by
    #: before it reads as a seam. Relative, not absolute, because the number that matters is
    #: "is this boundary unusual for this image" — a noisy tile differs by 40 everywhere and
    #: a flat one differs by 2 at a seam nobody can miss on a floor.
    max_ratio: float = 1.5

    #: Below this, an image is flat enough that the denominator is noise. A constant tile has
    #: zero interior difference, so any wrap difference at all divides to infinity; this is
    #: what keeps a one-level rounding artefact from reporting as an unbounded seam.
    floor: float = 0.5


def _wrap_ratio(image: np.ndarray, axis: int, floor: float) -> float:
    """How far the wrap boundary differs, over how far neighbours ordinarily differ.

    Both halves are mean absolute differences over the same axis and the same channels, so
    the units cancel and the answer is dimensionless: about 1 when the boundary is as
    ordinary as any other adjacency, far above it when it is not.

    `floor` is passed in rather than read off `SeamParams`. Reading the class attribute is
    the same expression to look at and silently ignores whatever the caller tuned, which is
    worse than not offering the field at all.
    """
    values = _rgb(image).astype(np.int16)
    lines = values if axis == 0 else np.swapaxes(values, 0, 1)
    interior = float(np.abs(np.diff(lines, axis=0)).mean()) if lines.shape[0] > 1 else 0.0
    across = float(np.abs(lines[-1] - lines[0]).mean())
    return across / max(interior, floor)


def check_seam(image: np.ndarray, params: SeamParams | None = None) -> Finding:
    """Whether this tile meets itself (R2.1, R2.2, R2.3).

    Measured per axis, because a tile may wrap one way and not the other, and one combined
    number would hide it.
    """
    params = params or SeamParams()
    height, width = image.shape[:2]
    if height < 2 or width < 2:
        return skipped(
            Check.SEAM,
            f"a {width}x{height} image has no wrap: an edge and its opposite are one pixel",
        )

    vertical = _wrap_ratio(image, axis=0, floor=params.floor)
    horizontal = _wrap_ratio(image, axis=1, floor=params.floor)
    measurement = {
        "horizontal": round(horizontal, 3),
        "vertical": round(vertical, 3),
        "max_ratio": params.max_ratio,
    }
    if max(horizontal, vertical) > params.max_ratio:
        return defect(Check.SEAM, fix="ssc tool tile", **measurement)
    return ok(Check.SEAM, **measurement)


# ── nineslice ─────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NineSliceParams:
    #: The four guides, without which there are no regions to measure. `None` is a skip
    #: rather than a guess: inventing guides to produce a number measures something nobody
    #: asked about.
    guides: tuple[int, int, int, int] | None = None

    #: How far a stretched region may vary along the axis it stretches on. In levels, and
    #: absolute rather than relative: unlike a seam, there is no "ordinary" variation to
    #: measure against — the correct answer for a stretched region is *none*.
    max_variation: int = 4


def check_nineslice(image: np.ndarray, params: NineSliceParams | None = None) -> Finding:
    """Whether this panel survives being stretched at its guides (R2.1, R2.2, R2.4).

    An edge region is repeated along one axis, so what matters is whether it is constant
    *along that axis*. A left edge may be as detailed as it likes horizontally — that
    direction is never stretched — but any change down its height is smeared across every
    size the panel is drawn at. A corner is measured on neither axis, because a corner never
    stretches.
    """
    from ssc.core.ninepatch import STRETCHED, bounds

    params = params or NineSliceParams()
    if params.guides is None:
        return skipped(
            Check.NINESLICE,
            "nineslice needs the four guides; pass them to ssc tool ninepatch",
        )

    try:
        cut = bounds(image, params.guides)
    except ValueError as refused:
        return skipped(Check.NINESLICE, str(refused))

    values = _rgb(image).astype(np.int16)
    worst = 0
    worst_region = None
    for name, (rows, columns) in cut.items():
        region = values[rows, columns]
        if region.size == 0:
            continue
        for axis in STRETCHED[name]:
            # The spread of each line along the stretch axis, taken against that region's own
            # first line: a region that repeats cleanly has none.
            lines = region if axis == "y" else np.swapaxes(region, 0, 1)
            spread = int(np.abs(lines - lines[0]).max())
            if spread > worst:
                worst, worst_region = spread, name

    measurement = {
        "worst": worst,
        "worst_region": worst_region,
        "max_variation": params.max_variation,
    }
    if worst > params.max_variation:
        return defect(Check.NINESLICE, fix="ssc tool ninepatch", **measurement)
    return ok(Check.NINESLICE, **measurement)


# ── consistency ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConsistencyParams:
    """The set-level number `doctor` carries — a shape embedding per frame, averaged.

    `min_consistency` is `None` until a project sets it, which mirrors `PaletteParams.limit`:
    the number is reported on every set, and judging it is a project decision rather than a
    per-check one. A walk cycle's frames are *meant* to differ, so a default threshold would
    flag every animation as broken — the number is for a caller to read, not for the check
    to grade unsolicited.
    """

    #: The side each frame's mask is reduced to before it becomes a vector. 16 is enough
    #: resolution to tell a standing frame from a crouching one, and small enough that two
    #: frames of the same character at the same pose land within a point of each other.
    grid: int = 16
    #: Below this mean pairwise similarity the set is inconsistent. `None` reports the
    #: number and judges nothing.
    min_consistency: float | None = None


def _shape_vector(frame: np.ndarray, grid: int) -> np.ndarray:
    """One frame as a flattened low-resolution shape — the consistency embedding.

    The alpha mask is the subject where there is one; where there is not, a luminance mask
    stands in, because a sheet with a chroma background still has a subject whose shape
    varies frame to frame. Reduced to `grid`x`grid` so two frames of the same character at
    the same pose agree and two from different characters do not, without carrying the
    pixel detail that would make every frame unique.
    """
    if has_alpha(frame):
        mask = alpha_mask(frame)
    else:
        luminance = _rgb(frame).mean(axis=2)
        mask = luminance > luminance.mean()
    reduced = reduce_mask(mask, width=grid, height=grid)
    return reduced.astype(np.float32).ravel()


def check_consistency(frames: list[np.ndarray], params: ConsistencyParams | None = None) -> Finding:
    """How much one frame's shape agrees with the rest, as one number (plan task 10.2).

    Each frame is embedded to a reduced shape vector and the set's consistency is the mean
    cosine similarity over every pair. The number is 1.0 when every frame shares a
    silhouette and falls as they diverge; it is reported as a number, and is a defect only
    where a project gave `min_consistency` and the set fell below it.

    Model-free and pure, deliberately: `doctor` works on any install, so the set-level
    number does not depend on the pose model's competence the way `ssc tool pose` does. The
    two leaves are siblings — pose tracks per frame, consistency embeds across the set —
    but this one answers without the `[cv]` extra.
    """
    params = params or ConsistencyParams()
    if len(frames) < 2:
        return skipped(Check.CONSISTENCY, "consistency needs at least two frames")

    vectors = np.vstack([_shape_vector(frame, params.grid) for frame in frames])
    norms = np.linalg.norm(vectors, axis=1)
    # A zero vector is an empty frame. Normalising it to zero makes its cosine 0 with every
    # other frame, which is the honest reading: an empty frame agrees with nothing that has
    # content, and a set of all-empty frames agreeing is a degenerate case this guard turns
    # into 0.0 rather than `NaN`.
    safe = np.where(norms[:, None] > 0, norms[:, None], 1.0)
    unit = vectors / safe
    similarity = unit @ unit.T
    count = len(frames)
    # Mean over the upper triangle only: the diagonal is self-similarity (1.0) and the
    # lower triangle mirrors the upper, so either half double-counts.
    upper = similarity[np.triu_indices(count, k=1)]
    value = float(upper.mean()) if upper.size else 1.0

    measurement: dict[str, object] = {
        "consistency": round(value, 3),
        "frames": count,
        "grid": params.grid,
    }
    if params.min_consistency is not None:
        measurement["min_consistency"] = params.min_consistency
        if value < params.min_consistency:
            return defect(Check.CONSISTENCY, fix="ssc tool align --anchor feet", **measurement)
    return ok(Check.CONSISTENCY, **measurement)
