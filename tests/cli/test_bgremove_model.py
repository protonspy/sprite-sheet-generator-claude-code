"""`tool bgremove --model` under the `[cv]` extra — plan tasks 9.1 and 9.2.

`rembg` is not installed in this project's environment and is not going to be: the extra is
optional by design. So the model is injected — `cvruntime.matte_for` is the seam, and the
refusal for an absent extra is exercised for real, because that is the path a user without
the extra actually takes.
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
from ssc.cli.matte import matte_frames
from ssc.core.bgmodel import MatteParams

CPU = devices.PROVIDERS["cpu"]


def write_frame(path: Path, width: int = 8, height: int = 8) -> Path:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., :3] = 180
    image[..., 3] = 255
    Image.fromarray(image, mode="RGBA").save(path)
    return path


def a_matte(cut_at: int = 4):  # type: ignore[no-untyped-def]
    """A model that keeps the right-hand side of every frame."""

    def matte(image: np.ndarray) -> np.ndarray:
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        mask[:, cut_at:] = 255
        return mask

    return matte


def test_the_extra_being_absent_is_a_refusal_and_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 9.2 — the caller ran a real command, so what comes back is what to type next."""
    real_import = builtins.__import__

    def without_rembg(name: str, *args: object, **kwargs: object) -> object:
        if name == "rembg":
            raise ImportError("no module named rembg")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", without_rembg)

    with pytest.raises(SscError) as raised:
        cvruntime.matte_for("birefnet", "cpu")

    assert raised.value.code == "cv-extra-missing"
    assert "[cv]" in (raised.value.fix or "")


def test_the_extra_being_absent_reaches_the_command_as_a_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_frame(tmp_path / "in.png")

    def missing(model: str, device: str = "auto"):  # type: ignore[no-untyped-def]
        raise SscError("cv-extra-missing", "not installed", fix=cvruntime.INSTALL)

    monkeypatch.setattr(cvruntime, "matte_for", missing)

    result = CliRunner().invoke(
        main,
        [
            "tool",
            "bgremove",
            "--in",
            str(source),
            "--out",
            str(tmp_path / "out.png"),
            "--model",
            "rembg",
            "--json",
        ],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["error"]["code"] == "cv-extra-missing"
    assert "[cv]" in payload["error"]["fix"]
    assert not (tmp_path / "out.png").exists()


def test_an_unknown_model_is_refused_before_anything_is_loaded() -> None:
    with pytest.raises(UsageError) as raised:
        cvruntime.matte_for("segment-everything", "cpu")
    assert raised.value.code == "unknown-model"


def test_the_command_cuts_the_set_out_with_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = write_frame(tmp_path / "in.png")
    monkeypatch.setattr(cvruntime, "matte_for", lambda model, device="auto": (a_matte(), CPU))

    out = tmp_path / "out.png"
    result = CliRunner().invoke(
        main,
        [
            "tool",
            "bgremove",
            "--in",
            str(source),
            "--out",
            str(out),
            "--model",
            "birefnet",
            "--json",
        ],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["model"] == "birefnet"
    assert payload["provider"] == CPU
    assert payload["device"] == "cpu"
    written = np.asarray(Image.open(out).convert("RGBA"))
    assert written[0, 0, 3] == 0
    assert written[0, 7, 3] == 255


def test_the_chroma_path_is_untouched_when_no_model_is_named(tmp_path: Path) -> None:
    """The free path stays the default: `--model` is opt-in."""
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[..., :3] = (0x00, 0xB1, 0x40)
    image[3:5, 3:5, :3] = (10, 10, 10)
    image[..., 3] = 255
    source = tmp_path / "in.png"
    Image.fromarray(image, mode="RGBA").save(source)

    out = tmp_path / "out.png"
    result = CliRunner().invoke(
        main,
        ["tool", "bgremove", "--in", str(source), "--out", str(out), "--json"],
        catch_exceptions=False,
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert "model" not in payload
    assert payload["mode"] == "flood"


def test_a_cached_matte_is_reused_and_keyed_on_the_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 8.3 reaching its consumer: the same frame on two providers is two entries."""
    calls = {"n": 0}

    def counting(image: np.ndarray) -> np.ndarray:
        calls["n"] += 1
        return a_matte()(image)

    frames = [Frame("001.png", np.zeros((8, 8, 4), dtype=np.uint8))]
    cache = Cache(tmp_path / "cache")

    monkeypatch.setattr(cvruntime, "matte_for", lambda model, device="auto": (counting, CPU))
    first = matte_frames(frames, model="rembg", device="auto", params=MatteParams(), cache=cache)
    second = matte_frames(frames, model="rembg", device="auto", params=MatteParams(), cache=cache)

    assert calls["n"] == 1
    assert first.measurement["reused"] == 0
    assert second.measurement["reused"] == 1

    cuda = devices.PROVIDERS["cuda"]
    monkeypatch.setattr(cvruntime, "matte_for", lambda model, device="auto": (counting, cuda))
    third = matte_frames(frames, model="rembg", device="auto", params=MatteParams(), cache=cache)

    assert calls["n"] == 2
    assert third.measurement["reused"] == 0
    assert third.measurement["provider"] == cuda


def test_without_a_workspace_nothing_is_cached_and_the_run_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frames = [Frame("001.png", np.zeros((8, 8, 4), dtype=np.uint8))]
    monkeypatch.setattr(cvruntime, "matte_for", lambda model, device="auto": (a_matte(), CPU))

    matted = matte_frames(frames, model="rembg", device="auto", params=MatteParams(), cache=None)

    assert matted.measurement["reused"] == 0
    assert len(matted.frames) == 1
