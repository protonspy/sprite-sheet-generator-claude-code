"""`tool bgremove --model` over a whole set: the model, the cache, and what is reported.

The chroma path is microseconds a frame and caches nothing; a model is seconds a frame
against weights it downloads, so this one caches. What it caches is keyed on the execution
provider as well as on the frame and the flags (`adr:0011`), because two providers can
differ in the last bit and one key over both would hand back a matte computed on a machine
the caller is not on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import Any

import numpy as np

from ssc.cli import cvruntime, devices
from ssc.cli.cache import Cache, cache_key
from ssc.cli.frames import Frame, decode_image, encode
from ssc.cli.meta import digest
from ssc.core.bgmodel import Matte, MatteParams, cut_out


@dataclass
class Matted:
    """The frames a model cut out, and what to report about the run."""

    frames: list[Frame] = field(default_factory=list)
    measurement: dict[str, Any] = field(default_factory=dict)


def _cut(image: np.ndarray, matte: Matte, params: MatteParams) -> bytes:
    made, _ = cut_out(image, matte(image), params)
    return encode(made)


def matte_frames(
    frames: list[Frame],
    *,
    model: str,
    device: str,
    params: MatteParams,
    cache: Cache | None = None,
) -> Matted:
    """Cut every frame out with `model`, reusing what the cache already holds.

    The model is loaded once for the set — the weights are the expensive part and a set is
    many frames — and the device is resolved before the load, so a device that is not there
    fails in the time it takes to ask.
    """
    matte, provider = cvruntime.matte_for(model, device)
    salt = devices.cache_salt(provider)
    key_params = {"model": model, "edge_trim": params.edge_trim, "despeckle": params.despeckle}

    cut: list[Frame] = []
    reused = 0
    transparent = opaque = 0
    for frame in frames:
        compute = partial(_cut, frame.image, matte, params)
        if cache is None:
            data = compute()
        else:
            key = cache_key(
                "tool bgremove --model",
                params=key_params,
                inputs=[digest(encode(frame.image))],
                salt=salt,
            )
            data, hit = cache.use(key, compute)
            reused += int(hit)
        made = decode_image(data, frame.name)
        cut.append(Frame(frame.name, made))
        transparent += int((made[..., 3] == 0).sum())
        opaque += int((made[..., 3] == 255).sum())

    return Matted(
        frames=cut,
        measurement={
            "transparent_px": transparent,
            "opaque_px": opaque,
            "model": model,
            # Which provider the entries were keyed on, so the re-run after switching
            # extras reads as a different key rather than as a broken cache (adr:0011).
            "provider": provider,
            "device": devices.device_of(provider),
            "reused": reused,
        },
    )
