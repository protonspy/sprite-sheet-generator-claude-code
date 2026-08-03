"""Finding the pieces in one image.

Pure, and it returns **rectangles rather than images**. That is the load-bearing choice: the
grid detector can then be tested against an 8x8 array, and `cut` and `slice` cannot each crop
their own way — they take the same rectangles and differ only in what they write.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from ssc.core.bgremove import key_mask
from ssc.core.doctor.masks import label_regions

Mode = Literal["grid", "chroma", "islands"]


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class GridSpec:
    """A layout, as observed (R2.1).

    Observed, not intended: a sprite does not fill its cell, so where no content touches a
    cell boundary that boundary is not in the image at all. `cell` is therefore tight to the
    content and `spacing` is the gap actually measured — the split between the two is
    unknowable, and `cell + spacing` (the pitch) is the part that is not.
    """

    columns: int
    rows: int
    cell: tuple[int, int]
    margin: tuple[int, int]
    spacing: tuple[int, int]

    #: The bands themselves, as `(start, length)` per column and per row. `cell`, `margin`
    #: and `spacing` above are a *summary* — three scalars for a caller to read — and the
    #: cutting uses these instead. Reconstructing a position as `margin + n * (cell +
    #: spacing)` assumes the layout is perfectly periodic, and `regular()` deliberately
    #: allows 25% of variation, so the reconstruction drifted a little further out of step
    #: with every column until one rectangle held two sprites and the last ran off the
    #: image. The bands cannot drift: they are where the content actually is.
    columns_at: tuple[tuple[int, int], ...] = ()
    rows_at: tuple[tuple[int, int], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "margin": {"x": self.margin[0], "y": self.margin[1]},
            "spacing": {"x": self.spacing[0], "y": self.spacing[1]},
        }


#: How far the runs along one axis may vary and still be called a grid, as a share of the
#: longest. Not zero: antialiasing and a sprite that leans a pixel further left than its
#: neighbour are both normal, and a detector that demanded exactness would refuse every real
#: sheet. Not generous either — the point is to refuse an illustration, not to accommodate
#: one.
REGULARITY = 0.25


def crop(image: np.ndarray, rect: Rect) -> np.ndarray:
    """The pixels inside `rect`, refusing one that is not wholly inside the image.

    A numpy slice past the edge truncates silently, which is how a rectangle that ran off
    the sheet became a 2x10 file on disk while the command's own JSON reported it as 10x10.
    A caller's metadata disagreeing with its own output is worth a branch to prevent.
    """
    if rect.x < 0 or rect.y < 0 or rect.bottom > image.shape[0] or rect.right > image.shape[1]:
        raise ValueError(
            f"{rect.as_dict()} is not inside a {image.shape[1]}x{image.shape[0]} image"
        )
    return image[rect.y : rect.bottom, rect.x : rect.right]


def runs_of(occupied: np.ndarray) -> list[tuple[int, int]]:
    """Every run of `True` in a 1-D profile, as `(start, length)`."""
    padded = np.concatenate(([False], occupied, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [
        (int(start), int(stop - start)) for start, stop in zip(edges[::2], edges[1::2], strict=True)
    ]


def regular(values: list[int]) -> bool:
    """Whether these lengths are close enough to being one length."""
    if not values:
        return False
    longest = max(values)
    return longest > 0 and (longest - min(values)) <= REGULARITY * longest


def axis_layout(occupied: np.ndarray) -> list[tuple[int, int]] | None:
    """The content bands along one axis, or `None` if this axis is not a grid."""
    found = runs_of(occupied)
    if not found:
        return None
    if len(found) == 1 and found[0] == (0, len(occupied)):
        # Content edge to edge with nothing separating anything: one solid block is not a
        # layout, and calling it 1x1 is the plausible wrong answer this refuses to give.
        return None

    lengths = [length for _, length in found]
    if not regular(lengths):
        return None

    gaps = [
        found[index + 1][0] - (found[index][0] + found[index][1]) for index in range(len(found) - 1)
    ]
    if gaps and not regular(gaps):
        return None

    # A gutter wider than a cell is not a gutter. This is what tells a sheet apart from two
    # shapes that happen to sit on a diagonal: both are regular along each axis taken alone,
    # and only the sheet has gaps that are small against its cells. An occupancy check
    # cannot make that call — it would also refuse a real animation with one blank frame in
    # it, which is a legitimate sheet.
    if gaps and max(gaps) > max(lengths):
        return None

    return found


def detect_grid(image: np.ndarray, mask: np.ndarray | None = None) -> GridSpec | None:
    """Find the layout of a sheet nobody described (R1.2), or report none (R1.3, R2.4).

    Projection profiles: a column holding nothing is a gutter, a run of columns holding
    something is a cell, and the same along the rows. Both axes have to read as a grid — a
    sheet regular across and ragged down is not one, and cutting it as though it were is the
    failure this returns `None` to avoid.
    """
    occupied = image[..., 3] > 0 if mask is None else mask
    if occupied.ndim != 2 or not occupied.any():
        return None

    across = axis_layout(occupied.any(axis=0))
    down = axis_layout(occupied.any(axis=1))
    if across is None or down is None:
        return None

    def gap_after(bands: list[tuple[int, int]]) -> int:
        return max(
            (bands[i + 1][0] - (bands[i][0] + bands[i][1]) for i in range(len(bands) - 1)),
            default=0,
        )

    return GridSpec(
        columns=len(across),
        rows=len(down),
        cell=(max(length for _, length in across), max(length for _, length in down)),
        margin=(across[0][0], down[0][0]),
        spacing=(gap_after(across), gap_after(down)),
        columns_at=tuple(across),
        rows_at=tuple(down),
    )


def rects_from(spec: GridSpec) -> list[Rect]:
    """The rectangles a measured layout describes, using the cell it measured.

    Separate from `grid_rects` because the two answer different questions. `grid_rects`
    divides an image into N equal parts, which is right when a caller *states* a layout.
    A detected layout already knows its cell, its margin and its spacing, and re-deriving
    the cell by dividing the width silently assumes the far margin equals the near one —
    which is the miscrop this leaf exists to avoid: a sheet padded 5px on the left and 15px
    on the right came back with 9px cells where 6px were measured, dropping content off one
    edge of every piece and pulling in the neighbour's.
    """
    return [
        Rect(x=x, y=y, width=width, height=height)
        for y, height in spec.rows_at
        for x, width in spec.columns_at
    ]


def grid_rects(
    width: int,
    height: int,
    columns: int,
    rows: int,
    *,
    margin: tuple[int, int] = (0, 0),
    spacing: tuple[int, int] = (0, 0),
) -> list[Rect]:
    """Cut a stated grid into rectangles (R1.1).

    The cell size is derived from what is left after the margins and the gutters, and the
    remainder is left at the far edge rather than distributed: a sheet whose width does not
    divide evenly has one cell short by a pixel, and spreading that error across every cell
    would put every frame off by a sub-pixel amount instead of one frame off visibly.
    """
    if columns < 1 or rows < 1:
        raise ValueError(f"a grid needs at least one cell, got {columns}x{rows}")

    usable_width = width - 2 * margin[0] - spacing[0] * (columns - 1)
    usable_height = height - 2 * margin[1] - spacing[1] * (rows - 1)
    if usable_width < columns or usable_height < rows:
        raise ValueError(f"{columns}x{rows} does not fit in {width}x{height}")

    cell_width, cell_height = usable_width // columns, usable_height // rows
    return [
        Rect(
            x=margin[0] + column * (cell_width + spacing[0]),
            y=margin[1] + row * (cell_height + spacing[1]),
            width=cell_width,
            height=cell_height,
        )
        for row in range(rows)
        for column in range(columns)
    ]


#: A ceiling on how many regions will be turned into rectangles. A mask with one component
#: per pixel is not a rare hostile construction — it is what any dithered or antialiased
#: alpha channel produces under 4-connectivity, including `bgremove`'s own edge — and a
#: sheet is not a million pieces. Refusing names a flag; grinding does not.
MAX_PIECES = 4096


def bounds_of(mask: np.ndarray) -> list[Rect]:
    """One rectangle per connected `True` region, in one pass over the image.

    The obvious implementation asks `np.nonzero(labels == label)` once per label, which is
    `O(pixels x components)`. That is not a theoretical concern: an alpha channel with any
    dithering gives one component per pixel, and a 400x400 image of those took nine seconds
    against a per-image ceiling of 64 million pixels. `region_areas` one file over already
    solved the same shape with a single `bincount`, and this is the same trick — scatter the
    minima and maxima per label in one vectorised pass.
    """
    labels, count = label_regions(mask)
    if count == 0:
        return []
    if count > MAX_PIECES:
        raise ValueError(
            f"{count} separate regions is past {MAX_PIECES}; this does not look like a sheet"
        )

    rows, columns = np.nonzero(labels)
    identifiers = labels[rows, columns]

    left = np.full(count + 1, mask.shape[1], dtype=np.int64)
    right = np.full(count + 1, -1, dtype=np.int64)
    top = np.full(count + 1, mask.shape[0], dtype=np.int64)
    bottom = np.full(count + 1, -1, dtype=np.int64)
    np.minimum.at(left, identifiers, columns)
    np.maximum.at(right, identifiers, columns)
    np.minimum.at(top, identifiers, rows)
    np.maximum.at(bottom, identifiers, rows)

    return [
        Rect(
            x=int(left[label]),
            y=int(top[label]),
            width=int(right[label] - left[label]) + 1,
            height=int(bottom[label] - top[label]) + 1,
        )
        for label in range(1, count + 1)
        if right[label] >= 0
    ]


def chroma_rects(image: np.ndarray, key: tuple[int, int, int], tolerance: int) -> list[Rect]:
    """A rectangle around each region that is *not* the key colour (R1.4).

    The key is given rather than detected, exactly as in `background-removal` and for the
    same reason: guessing which colour the backdrop is gets it wrong eventually, and a wrong
    guess here cuts the sheet into nonsense.
    """
    return bounds_of(~key_mask(image, key, tolerance))


def island_rects(image: np.ndarray) -> list[Rect]:
    """A rectangle around each connected opaque region (R1.5).

    For a sheet whose background is already transparent — which, after `bgremove`, is the
    normal case in this pipeline.
    """
    return bounds_of(image[..., 3] > 0)


def keep(rects: list[Rect], *, min_size: int = 0, max_aspect: float = 0.0) -> list[Rect]:
    """Drop the pieces that are not pieces (R1.6, R1.7).

    Both filters exist because every detector that finds regions also finds specks and
    smears: a stray antialiased pixel is an island, and a one-pixel rule between rows is a
    very wide one.
    """
    kept = []
    for rect in rects:
        if min_size and min(rect.width, rect.height) < min_size:
            continue
        if max_aspect:
            longer, shorter = max(rect.width, rect.height), min(rect.width, rect.height)
            if shorter == 0 or longer / shorter > max_aspect:
                continue
        kept.append(rect)
    return kept


def in_reading_order(rects: list[Rect]) -> list[Rect]:
    """Top to bottom, then left to right (R1.8).

    Rows are banded rather than sorted on `y` alone: pieces on one row of a sheet rarely
    share an exact top edge — a crouching pose starts lower than a standing one — and
    sorting on `y` would interleave two rows into an order no reader would call reading
    order. Two pieces are on the same row when they overlap vertically at all.
    """
    if not rects:
        return []

    bands: list[list[Rect]] = []
    for rect in sorted(rects, key=lambda item: (item.y, item.x)):
        for band in bands:
            # Against the band's *first* piece — the topmost, since the input is sorted —
            # and not against the running maximum of its bottoms. Chaining on the maximum
            # is transitive: one tall piece in the middle bridges two rows that never
            # overlap each other, and all three come out in one band.
            if rect.y < band[0].bottom:
                band.append(rect)
                break
        else:
            bands.append([rect])
    return [rect for band in bands for rect in sorted(band, key=lambda item: item.x)]
