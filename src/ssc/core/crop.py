"""Framing a canvas: the rectangle a crop cuts, computed from numbers a caller gave.

Rectangles rather than images, the same split `core/recover.py` makes and for the same
reason: an aspect fit is arithmetic about a canvas size, and testing it against a pair of
integers is what keeps the placement honest. The cutting itself is `recover.crop`, which
already refuses a rectangle that is not wholly inside the image — nothing here touches a
pixel.
"""

from __future__ import annotations

from ssc.core.recover import Rect

#: Where a computed rectangle sits inside the canvas it was fitted to. Nine values, and
#: an axis the name does not mention is centred: `top` says nothing about x, so a caller
#: who wanted the top-left corner has to say `top-left`.
GRAVITIES = (
    "centre",
    "top",
    "bottom",
    "left",
    "right",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
)


def place(span: int, inside: int, *, near: bool, far: bool) -> int:
    """Where a span of `span` starts inside `inside`, pinned near, far, or centred.

    The leftover is halved with a floor, so an odd leftover leaves the extra pixel on the
    far side. That the two margins can differ by one is not avoidable — a pixel does not
    split — and choosing it here once is what stops the x and y axes disagreeing about it.
    """
    if near:
        return 0
    if far:
        return inside - span
    return (inside - span) // 2


def positioned(size: tuple[int, int], canvas: tuple[int, int], gravity: str) -> Rect:
    """The rectangle of `size` placed inside `canvas` by `gravity`."""
    if gravity not in GRAVITIES:
        raise ValueError(f"{gravity!r} is not a gravity; use one of {', '.join(GRAVITIES)}")
    width, height = size
    return Rect(
        x=place(width, canvas[0], near="left" in gravity, far="right" in gravity),
        y=place(height, canvas[1], near="top" in gravity, far="bottom" in gravity),
        width=width,
        height=height,
    )


def inset_rect(canvas: tuple[int, int], insets: tuple[int, int, int, int]) -> Rect:
    """`canvas` with `insets` — top, right, bottom, left — taken off its four sides.

    Clockwise from the top, which is CSS's order and the one a caller is most likely to
    already hold. A negative inset would be padding, and padding is `tool expand`: a
    command that both cuts and grows makes a sign error the difference between losing
    content and gaining margin, so it is refused here rather than quietly accepted.
    """
    top, right, bottom, left = insets
    if min(insets) < 0:
        raise ValueError(f"{insets} insets a negative number of pixels; padding is tool expand")

    width, height = canvas[0] - left - right, canvas[1] - top - bottom
    if width < 1 or height < 1:
        raise ValueError(f"{insets} inside {canvas[0]}x{canvas[1]} has no pixels in it")
    return Rect(x=left, y=top, width=width, height=height)


def aspect_rect(canvas: tuple[int, int], ratio: tuple[int, int], gravity: str = "centre") -> Rect:
    """The largest rectangle of `ratio` that fits `canvas`, positioned by `gravity`.

    One side always ends up equal to the canvas — that is what "largest" means here — and
    the other is derived from it rather than from a scale factor. A float scale would put
    a 3:2 crop of a 40x24 canvas at 35.999 and floor it to 35, losing a column for nothing;
    the integer comparison `width * ratio_height <= height * ratio_width` decides which
    side is the limit without ever leaving integers.
    """
    width, height = canvas
    ratio_width, ratio_height = ratio
    if ratio_width < 1 or ratio_height < 1:
        raise ValueError(f"{ratio_width}:{ratio_height} is not a ratio; both sides must be ≥ 1")

    if width * ratio_height <= height * ratio_width:
        fitted = (width, width * ratio_height // ratio_width)
    else:
        fitted = (height * ratio_width // ratio_height, height)

    if fitted[0] < 1 or fitted[1] < 1:
        raise ValueError(
            f"{ratio_width}:{ratio_height} inside {width}x{height} has no pixels in it"
        )
    return positioned(fitted, canvas, gravity)
