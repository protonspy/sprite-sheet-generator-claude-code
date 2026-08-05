"""Loading a model under the `[cv]` extra — the one place the optional import lives.

Everything about the extra being absent is here, so that no command grows its own
`try: import rembg` or `try: import onnxruntime`. A missing extra is a refusal carrying the
install command, never a traceback: the caller ran a real command on a real install, and
"what to type next" is the whole of what they need back.

The provider comes from `ssc.cli.devices`, and it is part of the cache key, so a matte
computed on CUDA and one computed on CPU are two entries rather than one. The pose model
rides the same provider and the same cache (`adr:0011`, `adr:0012`): a CPU pose and a CUDA
pose are likewise two entries, which is why `pose` depends on 8.3 rather than growing a
second runtime.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from ssc.cli import devices
from ssc.cli.errors import SscError, UsageError
from ssc.core.bgmodel import MODELS, Matte
from ssc.core.posetrack import KEYPOINT_COUNT, POSE_MODELS, PoseModel

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


# ── pose ─────────────────────────────────────────────────────────────────────────────


def _onnxruntime() -> Any:
    """The `onnxruntime` module, or a refusal naming the extra that carries it.

    `rembg` pulls `onnxruntime` in, so an install with the `[cv]` extra has both; but pose
    loads the session directly rather than through `rembg`, so this is the import that fails
    first on a bare install. The refusal is the same one `bgremove --model` raises, for the
    same extra, so a caller told to install once is not told to install twice.
    """
    try:
        import onnxruntime  # type: ignore[import-not-found]
    except ImportError:
        raise SscError(
            "cv-extra-missing",
            "pose tracking needs the [cv] extra, which is not installed",
            fix=INSTALL,
        ) from None
    return onnxruntime


def _model_dir() -> Path:
    """Where downloaded model weights live, so a cache miss is not a re-download.

    One directory per user, not per workspace: weights are a one-time cost and a workspace
    that re-downloaded them on every `ssc init` would be the thing this exists to prevent.
    `LOCALAPPDATA` on Windows, `XDG_CACHE_HOME` or `~/.cache` elsewhere — the same hierarchy
    every other tool on the machine uses, so `du` finds it where a person would look.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    path = root / "ssc" / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _weights(url: str) -> Path:
    """The path to an ONNX model, downloading it once if it is not already there.

    The filename is the last path segment of the URL, so two URLs that disagree on the model
    do not collide on disk. A download that fails is a refusal, not a traceback: the caller
    ran a real command and what they need back is "it could not reach the weights", with the
    URL so the failure is reproducible by hand.
    """
    target = _model_dir() / url.rsplit("/", 1)[-1]
    if target.is_file():
        return target
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)
    except (httpx.HTTPError, OSError) as failed:
        raise SscError(
            "model-download-failed",
            f"could not download the pose model from {url}: {failed}",
            fix="check the network and re-run; the weights cache under "
            "LOCALAPPDATA/ssc/models (or ~/.cache/ssc/models)",
        ) from failed
    return target


#: The square input side MoveNet Lightning takes. Documented rather than read off the
#: session, because the model's own input shape is the contract this preprocessing has to
#: match, and a mismatch is a wrong result rather than a crash.
MOVENET_INPUT = 192


def pose_model_for(model: str, device: str = "auto") -> tuple[PoseModel, str]:
    """A callable returning one `(KEYPOINT_COUNT, 3)` pose per frame, and the provider.

    The session is built once and closed over, because loading weights is the expensive part
    and a cycle is many frames. As with `matte_for`, the extra is checked before the device
    is resolved: with nothing installed both refusals are true, and "install the extra" is
    the one a caller can act on. The provider is the one `--device` picked, never a
    fallback, and it is what the caller folds into the cache key.

    The callable scales MoveNet's normalized output back into the frame's own pixels, so the
    pure core can stay shape-agnostic: it receives `x`, `y` in frame pixels and a `score` in
    0..1, which is the `PoseModel` contract.
    """
    if model not in POSE_MODELS:
        raise UsageError(
            "unknown-model",
            f"{model!r} is not a pose model ssc ships",
            fix=f"use one of: {', '.join(POSE_MODELS)}",
        )
    runtime = _onnxruntime()
    provider = devices.resolve(device)
    session = runtime.InferenceSession(str(_weights(POSE_MODELS[model])), providers=[provider])

    spec = session.get_inputs()[0]
    input_name = spec.name
    output_name = session.get_outputs()[0].name
    # NHWC ([1, H, W, 3]) is MoveNet's own layout; a NCHW export transposes here so the same
    # callable answers both. Read off the shape rather than assuming, because guessing wrong
    # silently swaps width for height.
    channels_last = spec.shape[-1] == 3 if len(spec.shape) == 4 else True

    def pose(image: np.ndarray) -> np.ndarray:
        from ssc.core.resize import ResizeParams, resize

        height, width = image.shape[:2]
        rgb = image[..., :3].astype(np.float32)
        if rgb.shape[:2] != (MOVENET_INPUT, MOVENET_INPUT):
            # The one resampler the pipeline allows (`tests/test_no_other_resampler.py` is
            # the invariant): nearest neighbour, through `core.resize`. Pose input is a
            # model's tensor, not finished art, but the invariant is blanket by design — a
            # second resampler anywhere is the thing it exists to refuse.
            rgb = resize(rgb, ResizeParams(width=MOVENET_INPUT, height=MOVENET_INPUT))
        rgb = rgb / 255.0
        batched = rgb[None, ...] if channels_last else rgb.transpose(2, 0, 1)[None, ...]
        result: Any = session.run([output_name], {input_name: batched})[0]
        # MoveNet returns [1, 1, 17, 3] as (y, x, score), each normalized 0..1 against the
        # 192x192 input. Map back into the frame's pixels and hand the core its contract.
        flat = np.asarray(result, dtype=np.float32).reshape(-1, 3)
        keypoints = np.empty((KEYPOINT_COUNT, 3), dtype=np.float32)
        keypoints[:, 0] = flat[:, 1] * width  # x
        keypoints[:, 1] = flat[:, 0] * height  # y
        keypoints[:, 2] = np.clip(flat[:, 2], 0.0, 1.0)  # score
        return keypoints

    return pose, provider
