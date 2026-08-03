"""Nine-patch guides — the four numbers an engine stretches a panel by.

Pure, and it computes numbers rather than pixels: nothing here reads or writes an image
beyond its size and its pixel grid. The engine does the stretching; `ssc` says where.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ssc.core.doctor.checks import detect_pixel_size

#: left, right, top, bottom — each a distance inwards from that edge.
Guides = tuple[int, int, int, int]

#: The nine, named the way an engine names them. Order is fixed so a caller reading the JSON
#: does not have to sort it.
REGIONS = (
    "top_left",
    "top",
    "top_right",
    "left",
    "centre",
    "right",
    "bottom_left",
    "bottom",
    "bottom_right",
)

#: Which axis each region is stretched along: `x`, `y`, both, or neither. This table *is* the
#: nine-patch — a corner never stretches, an edge stretches one way, the centre both — and it
#: is what `nineslice` measures against rather than re-deriving.
STRETCHED: dict[str, tuple[str, ...]] = {
    "top_left": (),
    "top": ("x",),
    "top_right": (),
    "left": ("y",),
    "centre": ("x", "y"),
    "right": ("y",),
    "bottom_left": (),
    "bottom": ("x",),
    "bottom_right": (),
}


def snap(value: int, pixel_size: int) -> int:
    """`value` moved onto the pixel grid, never to zero.

    Rounding 1 down to 0 with a pixel size of 4 would silently delete the border a caller
    asked for, which is worse than the half-block they would have got.
    """
    if pixel_size <= 1:
        return value
    snapped = round(value / pixel_size) * pixel_size
    return max(snapped, pixel_size) if value > 0 else value


def guides_for(image: np.ndarray, given: Guides | None = None) -> Guides:
    """The four guides, snapped onto the art's own grid (R1.2, R1.3).

    Derived guides are one pixel-art pixel a side. That is not a reading of the drawing —
    finding a border by looking at it is out of scope, and confidently wrong when tried — but
    the smallest guide that can be right, and the one a caller adjusts from.
    """
    pixel_size = max(detect_pixel_size(image), 1)
    if given is None:
        return (pixel_size, pixel_size, pixel_size, pixel_size)
    left, right, top, bottom = given
    return (
        snap(left, pixel_size),
        snap(right, pixel_size),
        snap(top, pixel_size),
        snap(bottom, pixel_size),
    )


def bounds(image: np.ndarray, guides: Guides) -> dict[str, tuple[slice, slice]]:
    """Each region as the pair of slices that cuts it out (R1.4 refuses first)."""
    height, width = image.shape[:2]
    left, right, top, bottom = guides

    if min(guides) < 0:
        raise ValueError(f"a guide cannot be negative, got {guides}")
    if left + right >= width or top + bottom >= height:
        raise ValueError(
            f"guides {guides} leave no centre in a {width}x{height} image: "
            "the two on an axis have met or crossed"
        )

    columns = {"left": slice(0, left), "centre": slice(left, width - right)}
    columns["right"] = slice(width - right, width)
    rows = {"top": slice(0, top), "centre": slice(top, height - bottom)}
    rows["bottom"] = slice(height - bottom, height)

    named = {}
    for row_name, row in rows.items():
        for column_name, column in columns.items():
            if row_name == "centre" and column_name == "centre":
                key = "centre"
            elif row_name == "centre":
                key = column_name
            elif column_name == "centre":
                key = row_name
            else:
                key = f"{row_name}_{column_name}"
            named[key] = (row, column)
    return named


def describe(image: np.ndarray, guides: Guides) -> dict[str, Any]:
    """The guides and the size of every region they make (R1.1, R1.5).

    The region sizes are the point of reporting rather than just the guides: a caller who
    sees the corners came out 4x4 on a panel with a four-pixel bevel knows the derived guides
    were a starting point, not an answer.
    """
    cut = bounds(image, guides)
    left, right, top, bottom = guides
    return {
        "guides": {"left": left, "right": right, "top": top, "bottom": bottom},
        "regions": {
            name: {
                "width": cut[name][1].stop - cut[name][1].start,
                "height": cut[name][0].stop - cut[name][0].start,
            }
            for name in REGIONS
        },
    }
