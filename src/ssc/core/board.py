"""The two reference images the generation step needs.

Generated, never vendored. Both sources treat a black-and-white checkerboard as the trick
that makes an image model produce block-shaped pixels, and both distribute it as a download
behind a mailing list — somebody else's file under a licence this project does not have,
and a fixed PNG freezes a parameter that should track the project.

The sources also disagree about what the board *is*: one describes a checkerboard
alternating every single pixel, the other a grid of black and white squares. Which one a
given model responds to is an empirical question, so this generates either — `--square 1`
is the first, anything larger is the second — and `tool sweep` is what answers it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


@dataclass(frozen=True)
class Layout:
    """What was actually drawn.

    Reported by the command (R4.3) because the layout is what determines the size the
    generation call has to ask a model for — and `specs/gen-fal/` reconciles that against
    what the model allows. A board whose layout the caller has to re-derive from the image
    is a board that will be asked for at the wrong aspect.
    """

    columns: int
    rows: int
    cell: int
    width: int
    height: int

    def as_dict(self) -> dict[str, int]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "cell": self.cell,
            "width": self.width,
            "height": self.height,
        }


def checkerboard(square: int, width: int, height: int) -> tuple[np.ndarray, Layout]:
    """A black-and-white checkerboard of `square`-pixel squares (R4.1).

    The board is drawn to fill `width` x `height` exactly, so a size that is not a whole
    number of squares ends on a partial one rather than being silently rounded — the caller
    asked for a canvas of that size, and a model asked for a different one is the failure
    this whole command exists to avoid.
    """
    columns = -(-width // square)
    rows = -(-height // square)
    ys, xs = np.mgrid[0:height, 0:width]
    dark = ((xs // square) + (ys // square)) % 2 == 0

    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., :3] = np.where(dark[..., None], np.array(BLACK), np.array(WHITE))
    image[..., 3] = 255
    return image, Layout(columns=columns, rows=rows, cell=square, width=width, height=height)


def pose_board(columns: int, rows: int, cell: int) -> tuple[np.ndarray, Layout]:
    """`columns` x `rows` cells of `cell` pixels, every boundary visible (R4.2).

    White cells with black one-pixel rules between them: the model has to be able to see
    where one pose ends and the next begins, and a border drawn *on* the boundary rather
    than inside each cell keeps every cell exactly `cell` pixels — which is what `tool cut`
    will later assume when it takes the board's output apart.
    """
    width, height = columns * cell, rows * cell
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., :3] = WHITE
    image[..., 3] = 255

    for column in range(columns + 1):
        image[:, min(column * cell, width - 1), :3] = BLACK
    for row in range(rows + 1):
        image[min(row * cell, height - 1), :, :3] = BLACK

    return image, Layout(columns=columns, rows=rows, cell=cell, width=width, height=height)
