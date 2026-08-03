"""Putting the pieces back on a grid.

Pure. Every operation here is a **placement**, never a resampling: padding, flipping,
shifting and laying out all move pixels without recomputing any, which is what makes it
impossible for this leaf to reintroduce the blur `snap` exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ssc.core.doctor.masks import alpha_mask, anchor

Place = str


@dataclass(frozen=True)
class Aligned:
    """A set moved onto one anchor, and what that took."""

    frames: list[np.ndarray]
    anchor: tuple[int, int]
    empty: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class Layout:
    """Where a packed sheet put everything."""

    columns: int
    rows: int
    cell: tuple[int, int]
    anchor: tuple[int, int]

    def as_dict(self) -> dict[str, object]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
        }


def flip(frame: np.ndarray) -> np.ndarray:
    """Mirror horizontally (R2.1) — the free way to get East from West."""
    return np.ascontiguousarray(frame[:, ::-1])


def expand(
    frame: np.ndarray,
    *,
    to: tuple[int, int] | None = None,
    by: int = 0,
    fill: tuple[int, int, int] | None = None,
    place: Place = "centre",
) -> np.ndarray:
    """Put `frame` on a bigger canvas (R1.1-R1.5).

    Never crops: a target smaller than the frame is refused rather than quietly trimmed
    (R1.5). Padding that silently removed content would be the same class of defect as a
    grid that silently miscrops.
    """
    height, width = frame.shape[:2]
    target = to if to is not None else (width + 2 * by, height + 2 * by)
    if target[0] < width or target[1] < height:
        raise ValueError(f"{target[0]}x{target[1]} is smaller than the frame's {width}x{height}")

    canvas = np.zeros((target[1], target[0], 4), dtype=np.uint8)
    if fill is not None:
        canvas[..., :3] = fill
        canvas[..., 3] = 255

    left = (target[0] - width) // 2
    top = (target[1] - height) if place in {"bottom", "feet"} else (target[1] - height) // 2
    canvas[top : top + height, left : left + width] = frame
    return canvas


def anchor_of(frame: np.ndarray, mode: Place) -> tuple[float, float] | None:
    """Where this frame is anchored, as `(row, column)`, or `None` if it holds nothing.

    `feet` is `doctor`'s, reused rather than redefined: the lowest occupied row and the
    centre of the body *in that row*. Two functions answering "where is this sprite
    anchored" that could disagree is the defect, not the saving.
    """
    mask = alpha_mask(frame)
    if not mask.any():
        return None
    if mode == "feet":
        return anchor(mask)

    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    middle = float((columns[0] + columns[-1]) / 2.0)
    if mode == "bottom":
        return float(rows[-1]), middle
    return float((rows[0] + rows[-1]) / 2.0), middle


def plan_alignment(frames: list[np.ndarray], mode: Place = "feet") -> Aligned:
    """Move every frame so that its anchor lands on one pixel (R3.2, R3.3).

    The canvas grows rather than the frames shifting inside the one they arrived on. A
    shift that fitted every frame would only exist if the anchors happened to be arranged
    conveniently, and when it does not exist the frames that do not fit lose content off an
    edge — silently, which is the failure worth spending pixels to avoid.

    So the common anchor sits at the furthest any frame reaches from its own anchor, in each
    of the four directions, and the canvas is exactly big enough for that.
    """
    anchors = [anchor_of(frame, mode) for frame in frames]
    empty = [index for index, found in enumerate(anchors) if found is None]
    real = [
        (frame, found) for frame, found in zip(frames, anchors, strict=True) if found is not None
    ]

    if not real:
        # Nothing to align. The frames come back untouched but padded to one size, so a set
        # of blanks is still a set the rest of the pipeline can pack.
        height = max((frame.shape[0] for frame in frames), default=1)
        width = max((frame.shape[1] for frame in frames), default=1)
        return Aligned(
            frames=[expand(frame, to=(width, height)) for frame in frames],
            anchor=(0, 0),
            empty=empty,
        )

    # Floor, not `round`. An anchor's column is fractional — `doctor` puts it at the centre
    # of the body in its bottom row, so a two-pixel-wide sprite anchors at x.5 — and Python's
    # `round` is banker's rounding, which sends 7.5 and 8.5 both to 8. Two frames whose
    # anchors share a fractional part then got shifts differing by one, and landed half a
    # pixel apart: the drift this command exists to remove, reintroduced by the command.
    #
    # Flooring keeps the fraction intact, and an integer shift preserves it, so frames whose
    # anchors agree fractionally land exactly together.
    above = max(int(found[0]) for _, found in real)
    below = max(frame.shape[0] - 1 - int(found[0]) for frame, found in real)
    left = max(int(found[1]) for _, found in real)
    right = max(frame.shape[1] - 1 - int(found[1]) for frame, found in real)

    height, width = above + below + 1, left + right + 1
    placed: list[np.ndarray] = []
    for frame, found in zip(frames, anchors, strict=True):
        canvas = np.zeros((height, width, 4), dtype=np.uint8)
        if found is None:
            placed.append(canvas)
            continue
        top = above - int(found[0])
        start = left - int(found[1])
        canvas[top : top + frame.shape[0], start : start + frame.shape[1]] = frame
        placed.append(canvas)

    return Aligned(frames=placed, anchor=(left, above), empty=empty)


def onion(frames: list[np.ndarray]) -> np.ndarray:
    """Every frame drawn over the others (R3.5), so a person can see the alignment.

    The cheapest way to check that a set really is aligned: the anchors coincide or they do
    not, and a picture says which without anyone reading a number.
    """
    if not frames:
        return np.zeros((1, 1, 4), dtype=np.uint8)
    stacked = np.zeros_like(frames[0])
    for frame in frames:
        visible = frame[..., 3] > 0
        stacked[visible] = frame[visible]
    return stacked


def pack(
    frames: list[np.ndarray],
    *,
    columns: int,
    cell: tuple[int, int] | None = None,
    anchor_at: tuple[int, int] | None = None,
) -> tuple[np.ndarray, Layout]:
    """Lay a set out in equal cells (R4.1-R4.4).

    Equal cells are what let an engine address a frame by number instead of by rect, and
    the anchor's position *within* the cell is reported because a sheet without it makes the
    engine re-centre the sprite — which brings back at runtime exactly the drift `align`
    just removed.
    """
    if not frames:
        raise ValueError("there are no frames to pack")
    if columns < 1:
        raise ValueError(f"a sheet needs at least one column, got {columns}")

    widest = max(frame.shape[1] for frame in frames)
    tallest = max(frame.shape[0] for frame in frames)
    size = cell or (widest, tallest)
    if size[0] < widest or size[1] < tallest:
        raise ValueError(f"a {size[0]}x{size[1]} cell does not fit a {widest}x{tallest} frame")

    rows = -(-len(frames) // columns)
    sheet = np.zeros((rows * size[1], columns * size[0], 4), dtype=np.uint8)
    for index, frame in enumerate(frames):
        row, column = divmod(index, columns)
        y, x = row * size[1], column * size[0]
        sheet[y : y + frame.shape[0], x : x + frame.shape[1]] = frame

    return sheet, Layout(
        columns=columns,
        rows=rows,
        cell=size,
        anchor=anchor_at or (size[0] // 2, size[1] - 1),
    )
