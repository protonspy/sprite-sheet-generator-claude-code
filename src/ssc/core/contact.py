"""One canvas holding every variant of a sweep, side by side.

**Nothing here resamples** (`specs/sweep-and-review` R3.3). A contact sheet that scaled its
cells to a common size would hide exactly the differences it exists to reveal — a two-pixel
halo, a dithering pattern, a palette that went flat — and it would have to go through
`core.resize`, which is the invariant this project guards hardest. So the cell is as large
as the largest variant, every variant sits at its own size inside one, and the space a
smaller variant does not fill stays background.

Placement is at the cell's top-left rather than centred. With variants of one input the
sizes are almost always equal and the two agree; where they differ, a common origin makes
the difference read as *one edge moved*, which is the thing being compared, rather than as
two edges moving by half of it each.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

#: Where every variant failed there is no art to size a cell from, and a canvas of zero
#: width is not an image. The sheet still has to exist: "all twelve failed" is a result
#: somebody needs to see, and the labels are what carry it.
MIN_CELL = 16


@dataclass(frozen=True)
class Cell:
    """One variant's place on the sheet. `image` is `None` where that variant failed."""

    image: np.ndarray | None
    label: str


@dataclass(frozen=True)
class ContactParams:
    """`columns` of zero means near-square, worked out from the count."""

    columns: int = 0
    padding: int = 4
    label_height: int = 12
    background: tuple[int, int, int, int] = (24, 24, 24, 255)
    ink: tuple[int, int, int, int] = (235, 235, 235, 255)


def cell_for(frames: list[np.ndarray], label: str) -> Cell:
    """One variant's cell — its first frame, or nothing where it produced none (R3.4).

    The first frame rather than a strip of all of them: a sweep compares *parameters*, and
    twelve variants each showing eight frames is a sheet nobody can read. The frames are all
    on disk in the variant's own directory for anyone who needs the rest.
    """
    return Cell(image=frames[0] if frames else None, label=label)


def grid_for(count: int, columns: int) -> tuple[int, int]:
    """Columns and rows for `count` cells.

    Near-square by default, because a sweep of one parameter reads as a strip and a sweep of
    two reads as a table, and neither is knowable from the count alone. `expand` already
    orders the points so the first parameter varies slowest, which is what makes a
    caller-supplied `columns` — one row per value of it — worth having.
    """
    if count <= 0:
        return 1, 1
    wide = columns if columns > 0 else math.ceil(math.sqrt(count))
    return wide, math.ceil(count / wide)


def sheet(cells: list[Cell], params: ContactParams) -> np.ndarray:
    """Every cell on one canvas (R3.1, R3.3, R3.5).

    The labels are reserved for here and drawn by `label.py`: the geometry is arithmetic
    that is worth testing on its own, and glyph rendering is not.
    """
    columns, rows = grid_for(len(cells), params.columns)

    sized = [cell.image for cell in cells if cell.image is not None]
    cell_width = max((image.shape[1] for image in sized), default=MIN_CELL)
    cell_height = max((image.shape[0] for image in sized), default=MIN_CELL)

    tile_width = cell_width + 2 * params.padding
    tile_height = cell_height + 2 * params.padding + params.label_height

    canvas = np.empty((rows * tile_height, columns * tile_width, 4), dtype=np.uint8)
    canvas[:] = np.array(params.background, dtype=np.uint8)

    for index, cell in enumerate(cells):
        if cell.image is None:
            # R3.5 — left as background, and the label is what says it failed. Drawing a
            # cross or a placeholder here would be inventing a picture of an absence.
            continue
        row, column = divmod(index, columns)
        top = row * tile_height + params.padding
        left = column * tile_width + params.padding
        height, width = cell.image.shape[:2]
        canvas[top : top + height, left : left + width] = cell.image

    return canvas


def label_box(
    index: int, params: ContactParams, columns: int, cell: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Where cell `index`'s label strip is, as `(top, left, height, width)`.

    Separate from the drawing so the two cannot disagree about where a strip is: the
    geometry has one owner, and drawing reads it.
    """
    cell_width, cell_height = cell
    tile_width = cell_width + 2 * params.padding
    tile_height = cell_height + 2 * params.padding + params.label_height
    row, column = divmod(index, columns)
    top = row * tile_height + params.padding + cell_height
    left = column * tile_width + params.padding
    return top, left, params.label_height, cell_width


def _font(height: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """The default font at a size that fits the strip.

    `load_default` grew a `size` argument in Pillow 10.1 and returns a fixed-size bitmap
    font without it. Both are accepted rather than pinning a version: this is a label on a
    contact sheet, and a glyph one pixel taller than intended is not worth a constraint on
    what the project may install.
    """
    try:
        return ImageFont.load_default(size=max(8, height - 2))
    except TypeError:
        return ImageFont.load_default()


def _fitted(text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont, width: int) -> str:
    """As much of the label as the strip holds, with an ellipsis where it was cut.

    Truncating beats overflowing: a label that runs into the next cell makes two variants
    unreadable rather than one.
    """
    if width <= 0:
        return ""
    for length in range(len(text), 0, -1):
        candidate = text if length == len(text) else text[: max(0, length - 1)] + "…"
        if font.getlength(candidate) <= width:
            return candidate
    return ""


def draw_labels(canvas: np.ndarray, cells: list[Cell], params: ContactParams) -> np.ndarray:
    """Write each cell's label into its reserved strip (R3.2).

    Returns a new array. `core` functions do not mutate what they are handed, and a caller
    that built the canvas from a variant's own frames would otherwise find those frames
    written on.
    """
    if params.label_height <= 0 or not cells:
        return canvas

    columns, _ = grid_for(len(cells), params.columns)
    sized = [cell.image for cell in cells if cell.image is not None]
    cell_width = max((image.shape[1] for image in sized), default=MIN_CELL)
    cell_height = max((image.shape[0] for image in sized), default=MIN_CELL)

    handle = Image.fromarray(canvas.copy(), mode="RGBA")
    pen = ImageDraw.Draw(handle)
    font = _font(params.label_height)

    for index, cell in enumerate(cells):
        top, left, _, width = label_box(index, params, columns, (cell_width, cell_height))
        pen.text((left, top), _fitted(cell.label, font, width), font=font, fill=params.ink)

    return np.asarray(handle, dtype=np.uint8)
