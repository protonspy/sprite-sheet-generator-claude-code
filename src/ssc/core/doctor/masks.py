"""The mask arithmetic several detectors share.

`drift` needs an anchor, `silhouette` needs holes and fragments, and both start from the
same question: which pixels are the body. Written once so the two cannot drift apart in
their answer to it.
"""

from __future__ import annotations

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


def bounding_box(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """`(top, left, bottom, right)`, inclusive, or `None` for an empty mask."""
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return None
    return int(rows[0]), int(columns[0]), int(rows[-1]), int(columns[-1])


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
    """
    height, width = mask.shape
    labels = np.zeros((height, width), dtype=np.int32)
    count = 0
    for start_y in range(height):
        for start_x in range(width):
            if not mask[start_y, start_x] or labels[start_y, start_x]:
                continue
            count += 1
            stack = [(start_y, start_x)]
            labels[start_y, start_x] = count
            while stack:
                y, x = stack.pop()
                for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if not (0 <= next_y < height and 0 <= next_x < width):
                        continue
                    if mask[next_y, next_x] and not labels[next_y, next_x]:
                        labels[next_y, next_x] = count
                        stack.append((next_y, next_x))
    return labels, count


def region_sizes(labels: np.ndarray, count: int) -> list[int]:
    return [int((labels == label).sum()) for label in range(1, count + 1)]


def enclosed_regions(mask: np.ndarray) -> int:
    """Background regions the body surrounds — holes.

    Found by labelling the background and discarding whatever touches the image border:
    what is left is background that cannot be reached from outside, which is exactly a
    hole punched in the silhouette.
    """
    labels, count = label_regions(~mask)
    if count == 0:
        return 0
    border = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    return sum(1 for label in range(1, count + 1) if label not in border)
