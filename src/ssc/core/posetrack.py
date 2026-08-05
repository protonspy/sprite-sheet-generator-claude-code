"""Pose tracking through an animation cycle, reported per frame — plan task 10.1.

The model-backed half of the motion-consistency leaf. A pose model gives back keypoints
per frame; this module holds the tracking and the report and never the import. Where the
extra actually lives is `ssc.cli.cvruntime`, which loads an ONNX pose model under the
`[cv]` extra on the execution provider `--device` picks — the same provider/cache
infrastructure `bgremove --model` rides (`adr:0011`), which is why this leaf depends on 8.3
rather than growing a second runtime.

"Tracking" here is identity, not correspondence: a pose model returns keypoints in a fixed
index order (nose, left eye, …), so a frame walked through a cycle keeps the same landmark
at the same index, and the report is one row per frame. A model that returned an unordered
set would need a correspondence pass here; the model ssc ships does not, and the contract
the `PoseModel` callable satisfies is that the index is stable.

Pure, in the same sense as the rest of `core`: the model is injected as a callable returning
keypoints, so this module holds the per-frame report and the set-level summary and never the
import. A test injects a callable that returns a known skeleton; the runtime injects one
that runs the weights.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

#: What a model gives back: one `(K, 3)` array per frame — `x`, `y` in frame pixels and a
#: `score` in 0..1 — with the same landmark at the same index on every frame. Every model
#: under this leaf is asked for exactly this and nothing else, so a second model is a new
#: name in `POSE_MODELS` rather than a new code path.
PoseModel = Callable[[np.ndarray], np.ndarray]

#: The 17 COCO keypoints MoveNet returns, in the index order it returns them. The names are
#: what a per-frame report carries so a reader does not have to know that index 3 is the left
#: ear. A model with a different skeleton is a different `PoseModel` contract, not a flag.
KEYPOINT_NAMES = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)

#: How many keypoints the contract requires. A model returning a different count has a
#: different skeleton and does not satisfy `PoseModel`; refusing it here is cheaper than
#: indexing past the end of `KEYPOINT_NAMES` in a report.
KEYPOINT_COUNT = len(KEYPOINT_NAMES)

#: The pose models this leaf knows, and the ONNX weights each name downloads. `movenet` is
#: MoveNet SinglePose Lightning — 17 COCO keypoints, the smallest model that answers on a
#: CPU box and the one the cache warms against; a second model is a new name here rather than
#: a new code path. The URL is the resolve link Hugging Face serves the file at, so a cache
#: miss is one `httpx.get` rather than a model zoo of ssc's own.
POSE_MODELS = {
    "movenet": "https://huggingface.co/Xenova/movenet-singlepose-lightning/resolve/main/onnx/model.onnx",
}

#: Below this score a keypoint is taken as absent. 0.3 is MoveNet's own threshold for
#: "present"; a number nobody can reproduce from the spec would be the wrong thing to ship.
MIN_SCORE = 0.3


@dataclass(frozen=True)
class Pose:
    """One frame's keypoints, plus what a report needs without re-deriving it."""

    #: `(KEYPOINT_COUNT, 3)` — `x`, `y` in frame pixels, `score` in 0..1.
    keypoints: np.ndarray
    #: How many landmarks scored at or above `MIN_SCORE`, the count a per-frame summary
    #: leads with.
    visible: int

    def as_dict(self) -> dict[str, object]:
        """One row of the per-frame report: a landmark per entry, plus the visible count.

        `x`/`y` are rounded to one pixel — sub-pixel pose on pixel art is a precision the
        source does not have — and `score` to two places, which is the resolution at which
        "present" and "absent" are distinguishable without carrying noise.
        """
        names = KEYPOINT_NAMES
        landmarks: list[dict[str, object]] = []
        for index in range(self.keypoints.shape[0]):
            x, y, score = self.keypoints[index]
            landmarks.append(
                {
                    "name": names[index],
                    "x": round(float(x), 1),
                    "y": round(float(y), 1),
                    "score": round(float(score), 2),
                }
            )
        return {"visible": self.visible, "landmarks": landmarks}


@dataclass(frozen=True)
class PoseTrack:
    """Every frame's pose, and what to report about the run."""

    frames: list[Pose] = field(default_factory=list)
    measurement: dict[str, object] = field(default_factory=dict)


def track(
    frames: list[np.ndarray],
    model: PoseModel,
    *,
    min_score: float = MIN_SCORE,
) -> PoseTrack:
    """Run `model` over every frame and collect one `Pose` per frame.

    The model is called once per frame — pose is per-frame, not a temporal model, and a set
    is many frames — and each result is checked against the contract before it is kept, so a
    model that returns the wrong shape fails here with a named refusal rather than producing
    a report with a landmark missing.
    """
    poses: list[Pose] = []
    visible_total = 0
    score_total = 0.0
    scored = 0
    for frame in frames:
        keypoints = model(frame)
        checked = np.asarray(keypoints, dtype=np.float32)
        if checked.shape != (KEYPOINT_COUNT, 3):
            raise ValueError(
                f"a pose model returned shape {checked.shape}, not "
                f"({KEYPOINT_COUNT}, 3) (x, y, score)"
            )
        scores = checked[:, 2]
        in_range = scores[(scores >= 0.0) & (scores <= 1.0)]
        if in_range.size:
            score_total += float(in_range.mean())
            scored += 1
        visible = int(np.count_nonzero(scores >= min_score))
        visible_total += visible
        poses.append(Pose(keypoints=checked, visible=visible))

    measurement: dict[str, object] = {
        "frames": len(poses),
        "landmarks": KEYPOINT_COUNT,
        "min_score": min_score,
    }
    if poses:
        measurement["visible_mean"] = round(visible_total / len(poses), 2)
        measurement["score_mean"] = round(score_total / scored, 2) if scored else 0.0
    return PoseTrack(frames=poses, measurement=measurement)
