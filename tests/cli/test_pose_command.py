"""`tool pose` under the `[cv]` extra — plan task 10.1.

`onnxruntime` is not installed in this project's environment and is not going to be: the
extra is optional by design. So the model is injected — `cvruntime.pose_model_for` is the
seam, and the refusal for an absent extra is exercised for real, because that is the path a
user without the extra actually takes.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli import cvruntime, devices
from ssc.cli.app import main
from ssc.cli.cache import Cache
from ssc.cli.errors import SscError, UsageError
from ssc.cli.frames import Frame
from ssc.cli.pose import pose_frames
from ssc.core.posetrack import KEYPOINT_COUNT

CPU = devices.PROVIDERS["cpu"]


def write_frame(path: Path, width: int = 8, height: int = 8) -> Path:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., :3] = 180
    image[..., 3] = 255
    Image.fromarray(image, mode="RGBA").save(path)
    return path


def a_pose(image: np.ndarray) -> np.ndarray:
    """A skeleton that sits at the frame's centre, so a real-ish report has somewhere to put it."""
    h, w = image.shape[:2]
    keypoints = np.zeros((KEYPOINT_COUNT, 3), dtype=np.float32)
    keypoints[:, 0] = w / 2.0  # x
    keypoints[:, 1] = h / 2.0  # y
    keypoints[:, 2] = 0.9  # score
    return keypoints


def test_the_extra_being_absent_is_a_refusal_and_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller ran a real command, so what comes back is what to type next."""
    real_import = builtins.__import__

    def without_onnxruntime(name: str, *args: object, **kwargs: object) -> object:
        if name == "onnxruntime":
            raise ImportError("no module named onnxruntime")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", without_onnxruntime)

    with pytest.raises(SscError) as raised:
        cvruntime.pose_model_for("movenet", "cpu")

    assert raised.value.code == "cv-extra-missing"
    assert "[cv]" in (raised.value.fix or "")


def test_the_extra_being_absent_reaches_the_command_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_frame(tmp_path / "in.png")

    def missing(model: str, device: str = "auto"):  # type: ignore[no-untyped-def]
        raise SscError("cv-extra-missing", "not installed", fix=cvruntime.INSTALL)

    monkeypatch.setattr(cvruntime, "pose_model_for", missing)

    result = CliRunner().invoke(
        main,
        ["tool", "pose", "--in", str(source), "--model", "movenet", "--json"],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["error"]["code"] == "cv-extra-missing"
    assert "[cv]" in payload["error"]["fix"]


def test_an_unknown_model_is_refused_before_anything_is_loaded() -> None:
    with pytest.raises(UsageError) as raised:
        cvruntime.pose_model_for("openpose", "cpu")
    assert raised.value.code == "unknown-model"


def test_the_command_reports_one_pose_per_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_frame(tmp_path / "in.png")
    monkeypatch.setattr(cvruntime, "pose_model_for", lambda model, device="auto": (a_pose, CPU))

    result = CliRunner().invoke(
        main,
        ["tool", "pose", "--in", str(source), "--model", "movenet", "--json"],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["model"] == "movenet"
    assert payload["provider"] == CPU
    assert payload["device"] == "cpu"
    assert payload["poses"][0]["visible"] == KEYPOINT_COUNT
    assert payload["poses"][0]["landmarks"][0]["name"] == "nose"


def test_a_directory_is_read_as_an_ordered_cycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_frame(tmp_path / "001.png")
    write_frame(tmp_path / "002.png")
    write_frame(tmp_path / "003.png")
    monkeypatch.setattr(cvruntime, "pose_model_for", lambda model, device="auto": (a_pose, CPU))

    result = CliRunner().invoke(
        main,
        ["tool", "pose", "--in", str(tmp_path), "--json"],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["frames"] == 3  # the aggregate count
    assert isinstance(payload["poses"], list) and len(payload["poses"]) == 3  # the per-frame rows


def test_a_cached_pose_is_reused_and_keyed_on_the_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 8.3 reaching its second consumer: the same frame on two providers is two entries."""
    calls = {"n": 0}

    def counting(image: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        return a_pose(image)

    frames = [Frame("001.png", np.zeros((8, 8, 4), dtype=np.uint8))]
    cache = Cache(tmp_path / "cache")

    monkeypatch.setattr(cvruntime, "pose_model_for", lambda model, device="auto": (counting, CPU))
    first = pose_frames(frames, model="movenet", device="auto", cache=cache)
    second = pose_frames(frames, model="movenet", device="auto", cache=cache)

    assert calls["n"] == 1
    assert first.measurement["reused"] == 0
    assert second.measurement["reused"] == 1

    cuda = devices.PROVIDERS["cuda"]
    monkeypatch.setattr(cvruntime, "pose_model_for", lambda model, device="auto": (counting, cuda))
    third = pose_frames(frames, model="movenet", device="auto", cache=cache)

    assert calls["n"] == 2
    assert third.measurement["reused"] == 0
    assert third.measurement["provider"] == cuda


def test_without_a_workspace_nothing_is_cached_and_the_run_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [Frame("001.png", np.zeros((8, 8, 4), dtype=np.uint8))]
    monkeypatch.setattr(cvruntime, "pose_model_for", lambda model, device="auto": (a_pose, CPU))

    tracked = pose_frames(frames, model="movenet", device="auto", cache=None)

    assert tracked.measurement["reused"] == 0
    assert len(tracked.track.frames) == 1


def test_an_invalid_min_score_is_refused(tmp_path: Path) -> None:
    source = write_frame(tmp_path / "in.png")
    result = CliRunner().invoke(
        main,
        ["tool", "pose", "--in", str(source), "--min-score", "1.5", "--json"],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)
    assert result.exit_code == 2
    assert payload["error"]["code"] == "invalid-score"
