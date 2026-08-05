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

#: The anchors this module implements, as a value other modules import rather than retype.
#: `kinds.py` validates a profile against it and `recover.py` offers it as a `click.Choice`;
#: all three used to carry their own copy, which is the shape of defect this project has
#: been bitten by repeatedly.
ANCHOR_MODES = ("feet", "bottom", "centre")

#: The largest canvas any of these will build. Same number the board generator holds itself
#: to, for the same reason: every operation here allocates `width x height x 4` bytes, and
#: three of the four take a value that multiplies into that — `--cols` times the cell, `--by`
#: twice over, and the spread between a set's anchors. A ceiling on the *result* is the only
#: one that bounds them, because bounding the input value alone misses the multiplication.
MAX_CANVAS = 8192


class CanvasTooLarge(ValueError):
    """A result past `MAX_CANVAS`.

    Its own type, because `expand` and `pack` each raise two or three different refusals
    through one handler, and a caller acting on the `fix` of the wrong one is sent in the
    wrong direction — "expand never crops" says nothing useful about a canvas that was
    simply too big.
    """


def check_canvas(width: int, height: int, what: str) -> None:
    if width > MAX_CANVAS or height > MAX_CANVAS:
        raise CanvasTooLarge(f"{what} would be {width}x{height}, past {MAX_CANVAS} on a side")


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

    #: Whether every frame really shared that anchor. `False` says the set was not aligned
    #: first, so the anchor is one frame's rather than the set's — reported instead of
    #: quietly averaged, because an engine believing a wrong anchor is the failure.
    aligned: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
            "aligned": self.aligned,
        }


def flip(frame: np.ndarray) -> np.ndarray:
    """Mirror about the vertical axis (R2.1) — the free way to get East from West."""
    return np.ascontiguousarray(frame[:, ::-1])


def mirror(frame: np.ndarray, axis: str) -> np.ndarray:
    """Mirror a frame about an axis (R2.1), defaulting to the vertical one.

    `vertical` flips left↔right (East from West); `horizontal` flips top↔bottom.
    Both are placements, not resamples — no pixel is recomputed, so neither can
    reintroduce the blur `snap` exists to remove. The axis string is validated by
    the command surface (`click.Choice`), so a value that reaches here unrecognised
    is a programmer error and is treated as the default rather than silently doing
    the wrong flip.
    """
    if axis == "horizontal":
        return np.ascontiguousarray(frame[::-1, :])
    return np.ascontiguousarray(frame[:, ::-1])


def rotate(frame: np.ndarray, turns: int) -> np.ndarray:
    """Rotate by `turns` quarter turns counterclockwise.

    A placement, not a resample: `np.rot90` transposes and reverses axes, so no
    pixel is recomputed and the nearest-neighbour invariant (R4.4) holds — which is
    why `ssc tool rotate` accepts only quarter turns and refuses any other angle
    with the resampler as the stated reason. `turns` is 1, 2 or 3, normalised and
    validated by the command surface; a value outside that is a programmer error.
    """
    return np.ascontiguousarray(np.rot90(frame, k=turns))


def union_box(frames: list[np.ndarray]) -> tuple[int, int, int, int] | None:
    """The smallest box `(x, y, width, height)` covering every opaque pixel across
    every frame, or `None` where no frame holds anything opaque.

    One box for the set, not one per frame: a per-frame trim moves pixels to
    different places between frames and breaks the registration `align` just
    locked, so `trim` crops the set to a shared box. The frames are a set and share
    a shape; mixed sizes raise on the `|=` and the command surface reports that.
    """
    union = np.zeros(frames[0].shape[:2], dtype=bool)
    for frame in frames:
        union |= alpha_mask(frame)
    if not union.any():
        return None
    rows = np.where(union.any(axis=1))[0]
    cols = np.where(union.any(axis=0))[0]
    return int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


def offset(frame: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Shift a frame by whole pixels `(dx, dy)`: positive `dx` moves right, positive
    `dy` moves down. Content shifted off the canvas is dropped; the gap left behind
    is transparent. A placement, not a resample, so the nearest-neighbour invariant
    (R4.4) holds — which is why `ssc tool offset` takes whole pixels only.
    """
    height, width = frame.shape[:2]
    out = np.zeros_like(frame)
    y0, y1 = max(0, dy), min(height, dy + height)
    x0, x1 = max(0, dx), min(width, dx + width)
    if y0 < y1 and x0 < x1:
        out[y0:y1, x0:x1] = frame[y0 - dy : y1 - dy, x0 - dx : x1 - dx]
    return np.ascontiguousarray(out)


#: An anchor is a recorded point `(x, y) = (column, row)` — the pixel an engine pins the
#: sprite to. Every transform that moves the frames moves the anchor by the same placement,
#: or the sprite jitters against its anchor when the animation turns. These four mirror the
#: frame ops above one-for-one; the frame op is the source of truth for *which* pixels move,
#: and these restate where the anchor among them lands.
Anchor = tuple[int, int]


def mirror_anchor(anchor: Anchor, *, width: int, height: int, axis: str) -> Anchor:
    """The anchor after a mirror. `vertical` (left↔right) maps `x` to `width - 1 - x`;
    `horizontal` (top↔bottom) maps `y` to `height - 1 - y`.

    The `- 1` is the whole point: pixels are 0-indexed, so a width-6 frame's rightmost
    column is 5, and mapping `x` to `width - x` sends column 0 to 6 — one past the edge.
    The sprite then sits a pixel off its anchor on the mirror, which reads as a one-pixel
    jitter when an animation turns to its mirrored frame. The axis string is validated
    on the command surface, so an unrecognised value here is a programmer error and is
    treated as the vertical mirror.
    """
    x, y = anchor
    if axis == "horizontal":
        return (x, height - 1 - y)
    return (width - 1 - x, y)


def rotate_anchor(anchor: Anchor, *, width: int, height: int, turns: int) -> Anchor:
    """The anchor after `turns` quarter turns counterclockwise.

    `width` and `height` are the frame's shape *before* the turn. An odd turn swaps them,
    which is why the cell and the anchor stop matching after one (7.6) until both are
    moved. Built one quarter turn at a time so the shape swap is hard to get wrong: each
    step maps `(x, y)` to `(y, width - 1 - x)` and swaps the running shape.
    """
    x, y = anchor
    w, h = width, height
    for _ in range(turns % 4):
        x, y = y, w - 1 - x
        w, h = h, w
    return (x, y)


def offset_anchor(anchor: Anchor, *, dx: int, dy: int) -> Anchor:
    """The anchor after an offset — the same `(dx, dy)` the frames shifted by."""
    return (anchor[0] + dx, anchor[1] + dy)


def trim_anchor(anchor: Anchor, *, box: tuple[int, int, int, int]) -> Anchor:
    """The anchor after a trim to `box = (x, y, width, height)`. Cropping to the box moves
    every pixel — and the anchor — by the box's origin, so the anchor's offset into the
    kept content is what survives."""
    return (anchor[0] - box[0], anchor[1] - box[1])


#: An authored box `(x, y, width, height)` in frame pixels — a hitbox or a hurtbox. These
#: four restate the frame ops for a box the way the anchor ops above do for a point: a
#: mirrored frame with an unmirrored hurt box takes damage on the wrong side, so a box moves
#: by exactly the transform its pixels took, or it is wrong.
BoxSpan = tuple[int, int, int, int]


def mirror_box(box: BoxSpan, *, width: int, height: int, axis: str) -> BoxSpan:
    """The box after a mirror. Its left edge lands where its *right* edge was: a span
    `[x, x + w)` maps to `[width - x - w, width - x)`, which is `width - 1 - (x + w - 1)`
    at the near end — the same `- 1` `mirror_anchor` keeps, applied to the far corner."""
    x, y, w, h = box
    if axis == "horizontal":
        return (x, height - y - h, w, h)
    return (width - x - w, y, w, h)


def rotate_box(box: BoxSpan, *, width: int, height: int, turns: int) -> BoxSpan:
    """The box after `turns` quarter turns counterclockwise, `width` and `height` the
    frame's shape before the turn. One step maps a pixel `(x, y)` to `(y, width - 1 - x)`,
    so the box's rows become its columns and its far column becomes its near row; width and
    height swap, on the box and on the running shape alike."""
    x, y, w, h = box
    canvas_w, canvas_h = width, height
    for _ in range(turns % 4):
        x, y, w, h = y, canvas_w - x - w, h, w
        canvas_w, canvas_h = canvas_h, canvas_w
    return (x, y, w, h)


def offset_box(box: BoxSpan, *, dx: int, dy: int, width: int, height: int) -> BoxSpan | None:
    """The box after an offset, clipped to the canvas the way the pixels were: content
    shifted off the edge is dropped, so the part of a box past the edge is too, and a box
    entirely off the canvas is `None` — gone with the pixels it covered."""
    x, y, w, h = box
    x0, y0 = max(0, x + dx), max(0, y + dy)
    x1, y1 = min(width, x + dx + w), min(height, y + dy + h)
    if x0 >= x1 or y0 >= y1:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def trim_box(box: BoxSpan, *, kept: tuple[int, int, int, int]) -> BoxSpan | None:
    """The box after a trim to `kept = (x, y, width, height)` — moved by the kept box's
    origin like `trim_anchor`, then clipped to the kept canvas. A box can outgrow the
    opaque content that decided the trim, so the part outside the crop is dropped, and a
    box wholly outside is `None`."""
    x, y, w, h = box
    kx, ky, kw, kh = kept
    x0, y0 = max(0, x - kx), max(0, y - ky)
    x1, y1 = min(kw, x - kx + w), min(kh, y - ky + h)
    if x0 >= x1 or y0 >= y1:
        return None
    return (x0, y0, x1 - x0, y1 - y0)


def rotate_cell(cell: tuple[int, int], *, turns: int) -> tuple[int, int]:
    """The cell a frame of this cell's size becomes after `turns` quarter turns — width and
    height swap on an odd turn, which is the mismatch `ssc tool rotate` reports when the
    frames came out of a pack to a fixed cell. A 16x8 frame turned a quarter is 8x16, and the
    sheet's 16x8 cell no longer fits it; the cell it now fits is `(8, 16)`.
    """
    width, height = cell
    if turns % 2:
        return (height, width)
    return (width, height)


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
    # `--by` is doubled by the time it gets here, so bounding the flag alone leaves the
    # canvas at twice the ceiling every sibling command is held to.
    check_canvas(target[0], target[1], "the canvas")

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


def anchor_pixel(frame: np.ndarray, mode: Place) -> tuple[int, int] | None:
    """The *pixel* a frame is anchored on, or `None` if it holds nothing.

    Rounded half-up, and this is the whole of the fix the first attempt got wrong. An
    anchor's column is fractional — the centre of the body in its bottom row — and its
    fraction is decided by the body's parity: two pixels wide anchors at x.5, three at x.0.
    Two such frames cannot share a sub-pixel centre no matter how they are moved, so the
    thing that has to coincide is the pixel, not the real number.

    The first attempt floored, which only decided the margins: each frame's content was then
    copied verbatim and kept its own fraction, so frames of differing parity stayed exactly
    as far apart as they had started. Half-up here, on each frame's own anchor, is what makes
    the targets equal before anything is placed.
    """
    found = anchor_of(frame, mode)
    if found is None:
        return None
    return int(np.floor(found[0] + 0.5)), int(np.floor(found[1] + 0.5))


def plan_alignment(frames: list[np.ndarray], mode: Place = "feet") -> Aligned:
    """Move every frame so that its anchor lands on one pixel (R3.2, R3.3).

    The canvas grows rather than the frames shifting inside the one they arrived on. A
    shift that fitted every frame would only exist if the anchors happened to be arranged
    conveniently, and when it does not exist the frames that do not fit lose content off an
    edge — silently, which is the failure worth spending pixels to avoid.

    So the common anchor sits at the furthest any frame reaches from its own anchor, in each
    of the four directions, and the canvas is exactly big enough for that.
    """
    anchors = [anchor_pixel(frame, mode) for frame in frames]
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
    above = max(found[0] for _, found in real)
    below = max(frame.shape[0] - 1 - found[0] for frame, found in real)
    left = max(found[1] for _, found in real)
    right = max(frame.shape[1] - 1 - found[1] for frame, found in real)

    height, width = above + below + 1, left + right + 1
    # Sized from the *content*, not from a flag: a set with two frames anchored near
    # opposite corners needs a canvas covering both, and every frame gets one. Two 8000px
    # frames inside the read ceilings already ask for a gigabyte each, all resident at once.
    check_canvas(width, height, "aligning these frames")

    placed: list[np.ndarray] = []
    for frame, found in zip(frames, anchors, strict=True):
        canvas = np.zeros((height, width, 4), dtype=np.uint8)
        if found is None:
            placed.append(canvas)
            continue
        top = above - found[0]
        start = left - found[1]
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


def common_anchor(frames: list[np.ndarray], mode: Place) -> tuple[tuple[int, int] | None, bool]:
    """The anchor pixel every frame shares, and whether they actually share one.

    `pack` measures this rather than assuming bottom-centre. The first version guessed
    `(cell_width // 2, cell_height - 1)`, which disagreed with where `align` had really put
    the anchor — by six pixels vertically on the tests' own fixture — because an aligned
    canvas keeps whatever transparent padding sat below the anchor row. A sheet whose
    recorded anchor is wrong makes the engine re-centre the sprite, which is the runtime
    drift `align` exists to remove, arriving by another door.
    """
    found = [anchor_pixel(frame, mode) for frame in frames]
    real = [item for item in found if item is not None]
    if not real:
        return None, False
    return (real[0][1], real[0][0]), len(set(real)) == 1


def pack(
    frames: list[np.ndarray],
    *,
    columns: int,
    cell: tuple[int, int] | None = None,
    mode: Place = "feet",
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
    # `columns` widens the sheet whether or not there are frames to fill it: one ordinary
    # 256px frame at the documented maximum of columns is a gigabyte of empty cells.
    check_canvas(columns * size[0], rows * size[1], "the sheet")
    sheet = np.zeros((rows * size[1], columns * size[0], 4), dtype=np.uint8)
    for index, frame in enumerate(frames):
        row, column = divmod(index, columns)
        y, x = row * size[1], column * size[0]
        sheet[y : y + frame.shape[0], x : x + frame.shape[1]] = frame

    measured, agreed = common_anchor(frames, mode)
    return sheet, Layout(
        columns=columns,
        rows=rows,
        cell=size,
        anchor=measured or (size[0] // 2, size[1] - 1),
        aligned=agreed,
    )
