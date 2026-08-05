"""`tool pose` over a whole set: the model, the cache, and what is reported.

The model is seconds a frame against weights it downloads, so this one caches — for the
same reason `matte` does, and on the same key shape. What is cached is keyed on the
execution provider as well as on the frame and the model (`adr:0011`, `adr:0012`), because
two providers can differ in the last bit and one key over both would hand back a pose
computed on a machine the caller is not on.

The pure core (`ssc.core.posetrack.track`) calls the `PoseModel` once per frame; the cache
wraps that callable here so a re-run of the same set on the same provider reuses every
frame's keypoints without `track` knowing a cache exists.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import numpy as np

from ssc.cli import cvruntime, devices
from ssc.cli.cache import Cache, cache_key
from ssc.cli.frames import Frame, encode
from ssc.cli.meta import digest
from ssc.core.posetrack import MIN_SCORE, PoseTrack, track


@dataclass
class Tracked:
    """The poses a model produced, and what to report about the run."""

    track: PoseTrack = field(default_factory=PoseTrack)
    measurement: dict[str, Any] = field(default_factory=dict)


def _serialise(keypoints: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, keypoints)
    return buffer.getvalue()


def _deserialise(data: bytes) -> np.ndarray:
    return np.asarray(np.load(io.BytesIO(data)), dtype=np.float32)


def pose_frames(
    frames: list[Frame],
    *,
    model: str,
    device: str,
    cache: Cache | None = None,
    min_score: float = MIN_SCORE,
) -> Tracked:
    """Track pose across every frame with `model`, reusing what the cache already holds.

    The model is loaded once for the set — the weights are the expensive part and a cycle is
    many frames — and the device is resolved before the load, so a device that is not there
    fails in the time it takes to ask. The cache wraps the per-frame callable, so `track`
    stays pure and a warm cache short-circuits the model without the core knowing.
    """
    pose, provider = cvruntime.pose_model_for(model, device)
    salt = devices.cache_salt(provider)
    key_params = {"model": model, "min_score": min_score}
    reused = 0

    def cached_model(image: np.ndarray) -> np.ndarray:
        compute = partial(pose, image)
        if cache is None:
            return compute()
        key = cache_key(
            "tool pose",
            params=key_params,
            inputs=[digest(encode(image))],
            salt=salt,
        )
        data, hit = cache.use(key, lambda: _serialise(compute()))
        nonlocal reused
        reused += int(hit)
        return _deserialise(data)

    # The contract `track` checks (KEYPOINT_COUNT, 3) is enforced against the cached array
    # too, so a cache entry written by a model with a different skeleton is refused on read
    # rather than producing a report with a landmark missing.
    pose_track = track([frame.image for frame in frames], cached_model, min_score=min_score)

    return Tracked(
        track=pose_track,
        measurement={
            "model": model,
            # Which provider the entries were keyed on, so the re-run after switching extras
            # reads as a different key rather than as a broken cache (adr:0011).
            "provider": provider,
            "device": devices.device_of(provider),
            "reused": reused,
            **pose_track.measurement,
        },
    )


def per_frame(track_result: PoseTrack) -> list[dict[str, object]]:
    """The report rows — one per frame — in the order the frames arrived."""
    return [pose.as_dict() for pose in track_result.frames]
