"""The whole chain on one fixture — plans/ssc-completion.md 2.1.

Base image, poses, pixel art, sheet, `doctor`, `dist/index.json`, each step consuming
exactly what the previous one wrote. Every leaf has its own suite; what none of them can
see is the *contract between* leaves — a stage renamed, a file moved, a field dropped —
which breaks the chain while every suite stays green. This one test goes red instead.

The paid step runs against the same fake client as `test_gen_commands.py`: nothing here
reaches the network, and the suite passes with no `FAL_KEY`.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from click.testing import CliRunner
from conftest import load_meta
from PIL import Image

from ssc.cli import fal, models
from ssc.cli import gen as pipeline
from ssc.cli.app import main
from ssc.cli.commands import gen as commands
from ssc.core.bgremove import PRESETS

NANO = "fal-ai/nano-banana-2"


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def pose_sheet() -> bytes:
    """Two 64x64 poses side by side on chroma green — the 'model output' the fake returns.

    64x64 because that is the character profile's cell, and the index publishes the
    profile's cell rather than measuring the frames.
    """
    sheet = np.zeros((64, 128, 4), dtype=np.uint8)
    sheet[..., :3] = PRESETS["green"]
    sheet[..., 3] = 255
    sheet[16:48, 16:40, :3] = (200, 30, 30)  # pose one
    sheet[16:48, 88:112, :3] = (200, 30, 30)  # pose two, shifted
    sheet[40:48, 80:88, :3] = (30, 30, 200)
    buffer = io.BytesIO()
    Image.fromarray(sheet, mode="RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


class Completed:
    error = None


@dataclass
class Handle:
    request_id: str = "req-chain"


@dataclass
class FakeClient:
    """The functions `cli/fal.py` needs, answering every job with the pose sheet."""

    submitted: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def submit(self, application: str, arguments: dict[str, Any]) -> Any:
        self.submitted.append((application, dict(arguments)))
        return Handle()

    def status(self, application: str, request_id: str) -> Any:
        return Completed()

    def result(self, application: str, request_id: str) -> dict[str, Any]:
        return {"images": [{"url": "https://v3.fal.media/files/poses.png"}]}

    def cancel(self, application: str, request_id: str) -> None:  # pragma: no cover
        raise AssertionError("nothing here cancels")

    def encode(self, data: str | bytes, content_type: str) -> str:
        return f"data:{content_type};base64,AAAA"

    def upload(self, data: str | bytes, content_type: str) -> str:  # pragma: no cover
        return "https://v3.fal.media/files/uploaded.png"


@pytest.fixture
def space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace whose one paid call answers with the pose sheet, offline."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(fal.KEY_VARIABLE, "a-fal-key-for-tests")
    shipped = models.load
    monkeypatch.setattr(commands, "provider", lambda: fal.Fal(api=FakeClient()))
    monkeypatch.setattr(models, "load", lambda: shipped(fetch=lambda _: None))
    monkeypatch.setattr(pipeline.fal, "fetch", lambda url, **rest: pose_sheet())

    assert run("init")[0] == 0
    document = yaml.safe_load((tmp_path / "ssc.yaml").read_text(encoding="utf-8")) or {}
    document["models"] = {"image": NANO}
    document["pipeline"] = [
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 4}},
    ]
    (tmp_path / "ssc.yaml").write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    return tmp_path


def test_the_chain_end_to_end(space: Path) -> None:
    # Base image: one paid generation lands the pose sheet in the asset, stage `gen`.
    assert run("asset", "new", "hero", "--kind", "character")[0] == 0
    code, payload = run("gen", "image", "--asset", "character/hero", "--prompt", "two poses")
    assert code == 0, payload
    hero = space / "assets" / "character" / "hero"
    generated = hero / load_meta(hero).stage("gen").path
    assert generated.is_file()

    # Poses: the sheet cut into one frame per pose.
    code, payload = run(
        "tool", "cut", "--in", str(generated), "--grid", "2x1", "--asset", "character/hero"
    )
    assert code == 0, payload

    # Pixel art: the declared pipeline carries the frames through nobg and pixels.
    code, payload = run("run", "character/hero")
    assert code == 0, payload
    assert payload["complete"] is True
    assert payload["ran"] == ["nobg", "pixels"]
    pixels = hero / "frames" / "pixels"
    assert len(list(pixels.glob("*.png"))) == 2

    # Doctor: measures the frames the pipeline just wrote, and a defect is a
    # measurement, not a failure.
    code, payload = run("tool", "doctor", "--in", str(pixels), "--cell", "64x64")
    assert code == 0, payload
    assert {entry["check"] for entry in payload["checks"]} >= {"pixel_grid", "flicker"}

    # The sidecar the index reads playback from.
    (hero / "asset.yaml").write_text("playback:\n  fps: 8\n  mode: loop\n", encoding="utf-8")

    # Index: one dist/index.json declaring the sheet the chain produced.
    code, payload = run("index")
    assert code == 0, payload
    assert payload["sheets"] == ["character/hero"]
    assert payload["skipped"] == []

    written = json.loads((space / "dist" / "index.json").read_text(encoding="utf-8"))
    (sheet,) = written["sheets"]
    assert sheet["cell"] == {"width": 64, "height": 64}
    assert sheet["playback"]["fps"] == 8

    image = Image.open(space / "dist" / sheet["image"])
    assert image.size == (128, 64)
    # Transparency in the published sheet proves the index published the processed
    # frames — the raw generation had no transparent pixel anywhere.
    assert np.asarray(image.convert("RGBA"))[..., 3].min() == 0
