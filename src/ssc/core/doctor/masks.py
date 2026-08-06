"""The mask arithmetic several detectors share.

`drift` needs an anchor, `silhouette` needs holes and fragments, and both start from the
same question: which pixels are the body. Written once so the two cannot drift apart in
their answer to it.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ssc.core.resize import ResizeParams, resize

#: A pixel belongs to the body when it is not fully transparent. Not "mostly opaque":
#: `halo` exists to count the in-between pixels, and a mask that quietly rounded them away
#: would hide the defect the other check is there to find.
OPAQUE = 0


def has_alpha(image: np.ndarray) -> bool:
    return image.ndim == 3 and image.shape[2] == 4


def alpha_mask(image: np.ndarray) -> np.ndarray:
    """`True` where the image has any coverage at all."""
    if not has_alpha(image):
        return np.ones(image.shape[:2], dtype=bool)
    return image[:, :, 3] > OPAQUE


def anchor(mask: np.ndarray) -> tuple[float, float] | None:
    """Where the feet are: the lowest occupied row, and the centre of the body *in that
    row*.

    Not the centroid, and not the centre of the bounding box either — both move when an
    arm swings, so a walk cycle would read as drifting while the feet stayed put, which is
    measuring the animation instead of the defect. Only the pixels actually standing on
    the ground decide the anchor.
    """
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        return None
    bottom = int(rows[-1])
    columns = np.flatnonzero(mask[bottom])
    return (float(bottom), float((columns[0] + columns[-1]) / 2.0))


@dataclass(frozen=True)
class Bounds:
    """Where the sprite is in one frame: its alpha bounding box, plus the two lines the
    normaliser aligns across a frame set.

    `width` and `height` are the visible width and visible height — the alpha bounding
    box, never the canvas. `baseline` is the canvas row the sprite's feet land on, the
    lowest occupied row, which is the anchor's row once `align` has run and the thing that
    has to agree between two animations. `centre` is the column of the body's centre in
    that row — the same number `anchor` returns — so the normaliser, the `scale` check and
    the per-frame box read one implementation of "where is the sprite in this frame".
    """

    x: int
    y: int
    width: int
    height: int
    baseline: int
    centre: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "baseline": self.baseline,
            "centre": self.centre,
        }


def bounds_of(image: np.ndarray) -> Bounds | None:
    """The alpha bounding box of one frame and the two lines a set is normalised on.

    `None` for a frame with no coverage — the one `align` reports as `empty` and the
    normaliser refuses to guess a position for, rather than averaging a zero frame into a
    set's baseline.
    """
    mask = alpha_mask(image)
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        return None
    columns = np.flatnonzero(mask.any(axis=0))
    placed = anchor(mask)
    # `rows` is non-empty, so `anchor` found a bottom row and a centre in it.
    assert placed is not None
    bottom, centre = placed
    return Bounds(
        x=int(columns[0]),
        y=int(rows[0]),
        width=int(columns[-1] - columns[0] + 1),
        height=int(rows[-1] - rows[0] + 1),
        baseline=int(bottom),
        centre=float(centre),
    )


def set_visible_height(frames: list[np.ndarray]) -> int:
    """The one height that represents a frame set: the median of its frames' visible heights.

    A set whose every frame is blank has no height, and returns `0` so `scale_target`
    refuses it and the `scale` check reads it as "no measurement" — a blank set is a set
    `bounds` reported empty, and neither the normaliser nor the check guesses a height for it.
    The same number the normaliser scales onto one target and the `scale` check compares
    across sets, in one place, so the two cannot disagree about what a set's height is.
    """
    heights = [box.height for box in (bounds_of(frame) for frame in frames) if box is not None]
    if not heights:
        return 0
    return round(float(np.median(heights)))


#: The fields a set is summarised over, in the order the report prints them.
BOUND_FIELDS: tuple[str, ...] = ("x", "y", "width", "height", "baseline", "centre")


def summarise_bounds(boxes: list[Bounds | None]) -> dict[str, dict[str, float]]:
    """Per-measurement median and spread across one frame set.

    The median is the set's representative value — the baseline one animation has to agree
    with another on, the visible height the `scale` check compares across sets. The spread
    is the range across the frames that had coverage: how much the measurement moves
    within one animation, which is the within-set jitter the cross-set check has to be
    larger than to be a defect rather than noise.

    Frames without coverage are excluded: a blank frame is not a measurement of the
    sprite's position, and including a zero would move the median off the sprite. An empty
    set — every frame blank — returns nothing, so a caller reads a missing field as "no
    measurement" rather than as a zero it would mistake for a sprite at the origin.
    """
    present = [box for box in boxes if box is not None]
    if not present:
        return {}
    summary: dict[str, dict[str, float]] = {}
    for field in BOUND_FIELDS:
        values = np.array([getattr(box, field) for box in present], dtype=float)
        summary[field] = {
            "median": float(np.median(values)),
            "spread": float(values.max() - values.min()),
        }
    return summary


def reduce_mask(mask: np.ndarray, width: int, height: int) -> np.ndarray:
    """Reduce a mask to `width`x`height`, each target pixel taking the majority of the
    source block it covers.

    Point sampling would make a one-pixel hole's survival a lottery of where the samples
    happened to land, and a measurement may not depend on that. A majority over the block
    is deterministic and it answers the question the check is actually asking: does this
    feature still cover a pixel at the size the sprite is played at.

    This is not a resampler in the sense the project forbids — the output is boolean, so
    it cannot invent an intermediate value, which is the whole reason nearest neighbour is
    the rule for images.
    """
    source_height, source_width = mask.shape
    if height >= source_height or width >= source_width:
        # Nothing to average: at or above the source size, a pixel maps to a pixel.
        return resize(mask.astype(np.uint8), ResizeParams(width=width, height=height)).astype(bool)

    row_edges = (np.arange(height + 1) * source_height) // height
    column_edges = (np.arange(width + 1) * source_width) // width
    counted = np.add.reduceat(
        np.add.reduceat(mask.astype(np.int32), row_edges[:-1], axis=0), column_edges[:-1], axis=1
    )
    areas = np.diff(row_edges)[:, None] * np.diff(column_edges)[None, :]
    majority: np.ndarray = counted * 2 >= areas
    return majority


def label_regions(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Label 4-connected `True` regions. Returns the labels and how many there are.

    4-connected, not 8: two shapes touching only at a corner are two shapes in pixel art,
    where a diagonal is a deliberate step rather than a join.

    `cv2` rather than a hand-rolled flood fill — `docs/stack.md` adopted OpenCV for
    "connected components, morphology, flood fill, Sobel", and this is the first thing in
    the project that needed one.
    """
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
    # OpenCV counts the background as label 0, so its total is one more than the number of
    # regions that are actually `True`.
    return labels, max(count - 1, 0)


def region_areas(labels: np.ndarray, count: int) -> np.ndarray:
    """The pixel count of every label from 1 upward, in one pass."""
    if count == 0:
        return np.zeros(0, dtype=np.int64)
    return np.bincount(labels.ravel(), minlength=count + 1)[1:]


def enclosed_regions(mask: np.ndarray) -> int:
    """Background regions the body surrounds — holes.

    Found by labelling the background and discarding whatever touches the image border:
    what is left is background that cannot be reached from outside, which is exactly a
    hole punched in the silhouette.
    """
    labels, count = label_regions(~mask)
    if count == 0:
        return 0
    touching_the_border = np.unique(
        np.concatenate((labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]))
    )
    return int(count - np.count_nonzero(touching_the_border > 0))
