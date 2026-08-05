"""`ssc tool style` — the project-locked palette path (task 5.1).

The palette is a *project* decision: locked once from a preset into `palette.json`, then
applied to every asset. These tests hold the contract the harness skill `sprite-style`
names — that locking is a one-time act, that a locked palette cannot be overridden per
call, and that the absence of a palette is answered with the exact command that locks one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner

from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.frames import encode
from ssc.cli.palettes import PALETTE_FILE, preset_names


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def swatch(colour: tuple[int, int, int]) -> np.ndarray:
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[:, :] = (*colour, 255)
    return image


@pytest.fixture
def space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ws.Workspace:
    """A workspace with two frames staged, and no palette locked yet."""
    monkeypatch.chdir(tmp_path)
    workspace = ws.create(tmp_path)
    frames = workspace.root / "frames"
    frames.mkdir()
    (frames / "001.png").write_bytes(encode(swatch((100, 100, 100))))
    (frames / "002.png").write_bytes(encode(swatch((200, 30, 30))))
    return workspace


def test_the_four_presets_ship() -> None:
    assert set(preset_names()) == {"pico8", "nes", "gameboy", "sweetie16"}


def test_locking_a_preset_writes_palette_json_and_applies_it(space: ws.Workspace) -> None:
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
        "--preset",
        "gameboy",
    )
    assert code == 0, payload

    locked = json.loads((space.root / PALETTE_FILE).read_text(encoding="utf-8"))
    assert locked["preset"] == "gameboy"
    assert len(locked["palette"]) == 4

    # Every output pixel is one of the four gameboy colours.
    from PIL import Image

    palette = {c.lower().lstrip("#") for c in locked["palette"]}
    for name in ("001.png", "002.png"):
        rgb = np.asarray(Image.open(space.root / "out" / name).convert("RGB"))
        for pixel in rgb.reshape(-1, 3):
            hexed = "".join(f"{v:02x}" for v in pixel)
            assert hexed in palette


def test_a_locked_palette_is_applied_without_a_preset(space: ws.Workspace) -> None:
    # Lock first.
    assert (
        run(
            "tool",
            "style",
            "--in",
            str(space.root / "frames"),
            "--out",
            str(space.root / "out"),
            "--preset",
            "pico8",
        )[0]
        == 0
    )

    # Second call: no --preset, applies the locked one.
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out2"),
    )
    assert code == 0, payload
    assert payload["preset"] == "pico8"


def test_a_locked_palette_refuses_a_per_call_preset(space: ws.Workspace) -> None:
    assert (
        run(
            "tool",
            "style",
            "--in",
            str(space.root / "frames"),
            "--out",
            str(space.root / "out"),
            "--preset",
            "pico8",
        )[0]
        == 0
    )

    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out2"),
        "--preset",
        "nes",
    )
    assert code != 0
    assert payload["error"]["code"] == "palette-locked"


def test_no_palette_and_no_preset_names_the_lock_command(space: ws.Workspace) -> None:
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code != 0
    assert payload["error"]["code"] == "no-palette"
    fix = payload["error"]["fix"]
    for name in ("pico8", "nes", "gameboy", "sweetie16"):
        assert name in fix


def test_an_unknown_preset_is_refused(space: ws.Workspace) -> None:
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
        "--preset",
        "mega-drive",
    )
    assert code != 0
    assert payload["error"]["code"] == "unknown-preset"


def test_a_dry_run_lock_writes_no_palette_file(space: ws.Workspace) -> None:
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
        "--preset",
        "gameboy",
        "--dry-run",
    )
    assert code == 0, payload
    assert not (space.root / PALETTE_FILE).is_file()
    assert "would lock" in payload["summary"]


def test_a_malformed_palette_json_is_refused(space: ws.Workspace) -> None:
    (space.root / PALETTE_FILE).write_text("{not json", encoding="utf-8")
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code != 0
    assert payload["error"]["code"] == "invalid-palette"


def _set_dither(space: ws.Workspace, value: str | None) -> None:
    """Write `style: {dither: ...}` into ssc.yaml, or remove the section."""
    import yaml

    config_path = space.config_path
    document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if value is None:
        document.pop("style", None)
    else:
        document["style"] = {"dither": value}
    config_path.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")


def _lock(space: ws.Workspace) -> None:
    assert (
        run(
            "tool",
            "style",
            "--in",
            str(space.root / "frames"),
            "--out",
            str(space.root / "out0"),
            "--preset",
            "pico8",
        )[0]
        == 0
    )


def test_dither_defaults_to_none_with_no_style_section(space: ws.Workspace) -> None:
    _lock(space)
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code == 0, payload
    assert payload["dither"] == "none"


def test_ordered_dither_is_read_from_ssc_yaml(space: ws.Workspace) -> None:
    _lock(space)
    _set_dither(space, "ordered")
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code == 0, payload
    assert payload["dither"] == "ordered"


def test_floyd_steinberg_dither_is_read_from_ssc_yaml(space: ws.Workspace) -> None:
    _lock(space)
    _set_dither(space, "floyd-steinberg")
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code == 0, payload
    assert payload["dither"] == "floyd-steinberg"


def test_an_invalid_dither_is_refused(space: ws.Workspace) -> None:
    _lock(space)
    _set_dither(space, "bayesian")
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code != 0
    assert payload["error"]["code"] == "invalid-dither"


def test_style_section_that_is_not_a_map_is_refused(space: ws.Workspace) -> None:
    _lock(space)
    import yaml

    config_path = space.config_path
    document = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    document["style"] = "ordered"
    config_path.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    code, payload = run(
        "tool",
        "style",
        "--in",
        str(space.root / "frames"),
        "--out",
        str(space.root / "out"),
    )
    assert code != 0
    assert payload["error"]["code"] == "invalid-config"
