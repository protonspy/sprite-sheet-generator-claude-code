"""Loading a model under the `[cv]` extra — the one place the optional import lives.

Everything about the extra being absent is here, so that no command grows its own
`try: import rembg`. A missing extra is a refusal carrying the install command, never a
traceback: the caller ran a real command on a real install, and "what to type next" is the
whole of what they need back.

The provider comes from `ssc.cli.devices`, and it is part of the cache key, so a matte
computed on CUDA and one computed on CPU are two entries rather than one.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from ssc.cli import devices
from ssc.cli.errors import SscError, UsageError
from ssc.core.bgmodel import MODELS, Matte

#: What to install to get here. `[cv]` rather than `[cv-gpu]`: the CPU build is the one
#: that always works, and `ssc info` is where a GPU box is told it could do better.
INSTALL = "uv pip install 'sprite-sheet-generator-claude-code[cv]'"


def _rembg() -> Any:
    """The `rembg` module, or a refusal naming the extra that carries it."""
    try:
        import rembg  # type: ignore[import-not-found]
    except ImportError:
        raise SscError(
            "cv-extra-missing",
            "removing a background by model needs the [cv] extra, which is not installed",
            fix=INSTALL,
        ) from None
    return rembg


def matte_for(model: str, device: str = "auto") -> tuple[Matte, str]:
    """A callable returning one soft mask per frame, and the provider it runs on.

    The session is built once and closed over, because loading weights is the expensive
    part and a set is many frames. The extra is checked before the device is resolved: with
    nothing installed both refusals are true, and "install the extra" is the one a caller
    can act on, where "no execution provider is usable" describes a consequence of it.
    Nothing has been downloaded by the time either fires.
    """
    if model not in MODELS:
        raise UsageError(
            "unknown-model",
            f"{model!r} is not a background-removal model ssc ships",
            fix=f"use one of: {', '.join(MODELS)}",
        )
    rembg = _rembg()
    provider = devices.resolve(device)
    session = rembg.new_session(MODELS[model], providers=[provider])

    def matte(image: np.ndarray) -> np.ndarray:
        mask: Any = rembg.remove(image[..., :3], session=session, only_mask=True)
        return np.asarray(mask)

    return matte, provider
