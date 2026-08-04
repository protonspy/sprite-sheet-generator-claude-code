"""Turning frames into a file somebody can look at.

The composition is `core/preview.py`; this is the encoder, and it is here for the reason
`frames.encode` is here — `core/` takes and returns arrays, and a GIF is bytes.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from ssc.cli.errors import SscError

#: GIF has 256 palette entries and one of them has to be the transparent one. 255 colours of
#: art is far more than pixel art uses and exactly one fewer than the format allows.
COLOURS = 255
TRANSPARENT = 255

#: Below this an alpha value is background. GIF has no partial transparency — a pixel is in
#: or out — so a threshold is unavoidable and stating it beats letting Pillow pick one.
OPAQUE_AT = 128

#: The shortest frame a GIF can really hold: the format stores hundredths of a second, and
#: browsers and image viewers famously round anything under 20ms up to 100ms. Reported rather
#: than silently produced, because "my 60fps preview plays at 10fps" is a bug report nobody
#: can diagnose from the file.
MIN_FRAME_MS = 20


def as_palette(frame: np.ndarray) -> Image.Image:
    """One RGBA frame as a palette image with a transparent index.

    `dither=NONE` is load-bearing: dithering invents pixels that are not in the art, which is
    the same damage `snap` exists to remove and would make a preview lie about the thing it
    is previewing.
    """
    rgba = Image.fromarray(frame, mode="RGBA")
    palette = rgba.convert("RGB").convert(
        "P", palette=Image.Palette.ADAPTIVE, colors=COLOURS, dither=Image.Dither.NONE
    )
    transparent = rgba.getchannel("A").point(lambda value: 255 if value < OPAQUE_AT else 0, "1")
    palette.paste(TRANSPARENT, transparent)
    return palette


def animated_gif(frames: list[np.ndarray], fps: int) -> bytes:
    """The frames as one animated GIF, at `fps` (R6.1).

    `disposal=2` — restore to background between frames — because these are cut-outs: without
    it every frame is painted over the last and a sprite that moves leaves a trail.
    """
    if not frames:
        raise SscError("no-frames", "there is nothing to animate")
    if fps < 1:
        raise SscError("invalid-fps", f"{fps} frames per second is not a frame rate")

    duration = max(round(1000 / fps), MIN_FRAME_MS)
    images = [as_palette(frame) for frame in frames]
    buffer = io.BytesIO()
    images[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=0,
        disposal=2,
        transparency=TRANSPARENT,
        optimize=False,
    )
    return buffer.getvalue()
