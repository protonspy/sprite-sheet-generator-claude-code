"""Closing a tile's wrap.

Pure, and every operation is a copy. That is not an implementation detail: the usual way to
close a seam is to blend across it, which invents colours the palette does not have and
softens exactly the hard edges `snap` exists to produce. Both modes here move pixels that
already exist in the image, so a closed tile's colour set is a subset of the one it arrived
with.
"""

from __future__ import annotations

from typing import Any

import numpy as np

Mode = str

#: What `close` knows how to do. `blend` is deliberately absent — see the module docstring
#: and `specs/tile-assets/` "Out of scope".
MODES = ("edge", "mirror")


def close(image: np.ndarray, *, mode: Mode = "edge") -> tuple[np.ndarray, dict[str, Any]]:
    """The tile with its wrap closed, and what that took (R1.1, R1.2, R1.3).

    `edge` copies the first column onto the last and the first row onto the last, so the
    pixels either side of the wrap are identical by construction — which is exactly what
    `doctor`'s `seam` check measures. It costs one column and one row of the art, and it is
    the smallest edit that closes the boundary.

    `mirror` makes the tile symmetric about both axes instead. Both wraps close because the
    first and last columns are then the same column; the cost is the symmetry, which reads
    as a pattern on a large floor.
    """
    height, width = image.shape[:2]
    if height < 2 or width < 2:
        raise ValueError(
            f"a {width}x{height} image has no wrap to close: "
            "an edge and its opposite need two pixels on a side"
        )
    if mode not in MODES:
        raise ValueError(f"{mode!r} is not a way to close a wrap; use one of {', '.join(MODES)}")

    if mode == "mirror":
        out = mirrored(image)
    else:
        out = image.copy()
        out[:, -1] = out[:, 0]
        # After the column, so the corner is the first row's first pixel either way round —
        # the two writes agree on it rather than racing for it.
        out[-1, :] = out[0, :]

    # What moved, not what was written to. The two differ on a tile that already wrapped,
    # and it is the difference an operator asking "did that do anything" wants: the answer
    # for a re-run is 0, which is what makes the idempotence visible rather than claimed.
    return out, {
        "mode": mode,
        "edges": ["right", "bottom"],
        "pixels_changed": pixels_changed(image, out),
    }


def mirrored(image: np.ndarray) -> np.ndarray:
    """The tile made symmetric about both axes (R1.2).

    The kept half is the first one, rounded up, so an odd side keeps its middle column and
    row rather than losing one: at 9 wide, columns 0-4 are the source and 5-8 mirror columns
    3-0. The first and last column then hold the same pixels, which is what closes the wrap.
    """
    height, width = image.shape[:2]
    keep_x, keep_y = (width + 1) // 2, (height + 1) // 2

    out = image.copy()
    # Reflect the kept half outwards, dropping the axis pixel itself so the middle is not
    # written twice — `[..., ::-1]` of everything before the axis is exactly the tail.
    out[:, keep_x:] = out[:, : width - keep_x][:, ::-1]
    out[keep_y:, :] = out[: height - keep_y, :][::-1, :]
    return out


def pixels_changed(before: np.ndarray, after: np.ndarray) -> int:
    """How many pixels differ between the two."""
    return int(np.count_nonzero(np.any(before != after, axis=-1)))
