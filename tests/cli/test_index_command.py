"""`ssc index` — specs/engine-index R1.6, R1.7, R1.8, R1.9, R5.6."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from conftest import save_meta

from ssc.cli import meta
from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.frames import encode


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def swatch(width: int = 16, height: int = 16, value: int = 200) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :] = (value, value, value, 255)
    return image


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ws.Workspace:
    """One animating asset, one icon and one tile — the three artefact shapes at once."""
    monkeypatch.chdir(tmp_path)
    space = ws.create(tmp_path)

    hero = space.asset_dir("character", "hero")
    (hero / meta.FRAMES_DIR / "cut").mkdir(parents=True)
    record = meta.AssetMeta(key="hero", kind="character")
    payload = b""
    for number in (1, 2, 3):
        data = encode(swatch(value=number * 40))
        (hero / meta.FRAMES_DIR / "cut" / f"{number:03d}.png").write_bytes(data)
        payload += data
    meta.record(
        record,
        path=f"{meta.FRAMES_DIR}/cut",
        stage="cut",
        file_class="derived",
        data=payload,
        produced_by=meta.Provenance(command="test"),
    )
    (hero / "asset.yaml").write_text("playback:\n  fps: 10\n  mode: ping-pong\n", encoding="utf-8")
    save_meta(hero, record)

    for kind, key, size in (("icon", "potion", (16, 16)), ("tile", "grass", (32, 32))):
        directory = space.asset_dir(kind, key)
        directory.mkdir(parents=True)
        one = meta.AssetMeta(key=key, kind=kind)
        data = encode(swatch(*size))
        (directory / f"001_{key}.png").write_bytes(data)
        meta.record(
            one,
            path=f"001_{key}.png",
            stage="gen",
            file_class="derived",
            data=data,
            produced_by=meta.Provenance(command="test"),
        )
        save_meta(directory, one)

    return space


def index_json(space: ws.Workspace) -> dict[str, Any]:
    return json.loads((space.dist / "index.json").read_text(encoding="utf-8"))


# R1.6 — the images and the index in one run.


def test_index_writes_every_image_its_entries_name(workspace: ws.Workspace) -> None:
    code, payload = run("index")
    assert code == 0
    assert payload["sheets"] == ["character/hero"]
    assert payload["atlases"] == ["icon"]
    assert payload["tilesets"] == ["tile"]

    written = index_json(workspace)
    named = (
        [sheet["image"] for sheet in written["sheets"]]
        + [atlas["image"] for atlas in written["atlases"]]
        + [tileset["image"] for tileset in written["tilesets"]]
    )
    assert named
    for image in named:
        assert (workspace.dist / image).is_file(), image


def test_the_sidecar_reaches_the_index(workspace: ws.Workspace) -> None:
    run("index")
    playback = index_json(workspace)["sheets"][0]["playback"]
    assert playback["fps"] == 10
    assert playback["mode"] == "ping-pong"


# R1.7 — nothing outside dist/.


def test_index_writes_nothing_outside_dist(workspace: ws.Workspace) -> None:
    before = {
        path: path.read_bytes() for path in sorted(workspace.assets.rglob("*")) if path.is_file()
    }
    run("index")
    after = {
        path: path.read_bytes() for path in sorted(workspace.assets.rglob("*")) if path.is_file()
    }
    assert before == after
    assert sorted(child.name for child in workspace.root.iterdir()) == [
        "assets",
        "cache",
        "dist",
        "jobs",
        "ssc.yaml",
    ]


# R1.8 — a second run over an unchanged workspace writes the same bytes.


def test_a_second_run_is_byte_identical(workspace: ws.Workspace) -> None:
    run("index")
    first = {
        path.relative_to(workspace.dist): path.read_bytes()
        for path in sorted(workspace.dist.rglob("*"))
        if path.is_file()
    }
    run("index")
    second = {
        path.relative_to(workspace.dist): path.read_bytes()
        for path in sorted(workspace.dist.rglob("*"))
        if path.is_file()
    }
    assert first == second
    assert first, "there was something to compare"


def test_a_rebuild_replaces_rather_than_refusing(workspace: ws.Workspace) -> None:
    # `dist/` is output, so a build that refused because its own last output is there would
    # need a `clean` before every run.
    assert run("index")[0] == 0
    assert run("index")[0] == 0


# R1.9 — dry run.


def test_a_dry_run_reports_every_file_and_writes_none(workspace: ws.Workspace) -> None:
    code, payload = run("index", "--dry-run")
    assert code == 0
    assert payload["dry_run"] is True
    assert "index.json" in payload["written"]
    assert any(name.startswith("sheets/") for name in payload["written"])
    assert not workspace.dist.exists()


# R5.6 — a format ssc does not emit.


def test_an_unknown_format_is_refused_before_anything_is_written(
    workspace: ws.Workspace,
) -> None:
    code, payload = run("index", "--format", "unity")
    assert code == 2
    assert payload["error"]["code"] == "unknown-format"
    assert not workspace.dist.exists()


@pytest.mark.parametrize("name", ["generic", "pixi", "phaser", "godot"])
def test_every_format_builds_the_same_files(workspace: ws.Workspace, name: str) -> None:
    run("index", "--format", name)
    images = sorted(
        path.relative_to(workspace.dist).as_posix()
        for path in workspace.dist.rglob("*.png")
        if path.is_file()
    )
    assert images == [
        "atlases/icon.png",
        "sheets/character/hero.png",
        "tilesets/tile.png",
    ]
    assert index_json(workspace)["format"] == name


# R1.5 — an asset with nothing to publish is reported, and the rest are indexed.


def test_an_asset_with_no_image_is_reported_and_the_rest_are_indexed(
    workspace: ws.Workspace,
) -> None:
    empty = workspace.asset_dir("icon", "unmade")
    empty.mkdir(parents=True)
    save_meta(empty, meta.AssetMeta(key="unmade", kind="icon"))

    code, payload = run("index")
    assert code == 0
    assert payload["skipped"] == [{"kind": "icon", "key": "unmade", "why": "records no image"}]
    assert payload["atlases"] == ["icon"]


def test_a_named_stage_is_what_gets_published(workspace: ws.Workspace) -> None:
    code, payload = run("index", "--stage", "cut")
    assert code == 0
    assert payload["sheets"] == ["character/hero"]
    # The icon and the tile record `gen`, not `cut`, so they are the ones left out.
    assert sorted(one["key"] for one in payload["skipped"]) == ["grass", "potion"]
