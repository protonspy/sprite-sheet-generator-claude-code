"""`ssc image|video list|show` — specs/asset-listing R2 and R3.

Both nouns come out of one factory, so the tests that matter twice — the medium a command
reports, and the shape of its JSON — are asserted against each of them rather than against
`image` alone.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli import meta
from ssc.cli.app import main


def write_png(path: Path) -> bytes:
    """A 4x4 image with a real pixel grid, so `doctor` has something honest to measure."""
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[..., 3] = 255
    pixels[:2, :2, 0] = 255
    Image.fromarray(pixels, mode="RGBA").save(path)
    return path.read_bytes()


def add(directory: Path, path: str, stage: str, file_class: str, parents: list[str]) -> None:
    record = meta.load(directory)
    data = (directory / path).read_bytes() if (directory / path).exists() else b""
    meta.record(
        record,
        path=path,
        stage=stage,
        file_class=file_class,  # type: ignore[arg-type]
        data=data,
        produced_by=meta.Provenance(command="test"),
        derived_from=parents,
    )
    meta.save(directory, record)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One character with an image chain, a clip and a sidecar; one tile with an image."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    hero = tmp_path / "assets/character/hero"
    hero.mkdir(parents=True)
    meta.save(hero, meta.AssetMeta(key="hero", kind="character"))
    write_png(hero / "001_hero.png")
    write_png(hero / "002_hero.snap.png")
    (hero / "003_hero.mp4").write_bytes(b"not decoded by anything here")
    (hero / "004_hero.boxes.json").write_text("{}")
    add(hero, "001_hero.png", "anchor", "source", [])
    add(hero, "002_hero.snap.png", "snap", "derived", ["001_hero.png"])
    add(hero, "003_hero.mp4", "clip", "source", ["002_hero.snap.png"])
    add(hero, "004_hero.boxes.json", "boxes", "derived", [])

    grass = tmp_path / "assets/tile/grass"
    grass.mkdir(parents=True)
    meta.save(grass, meta.AssetMeta(key="grass", kind="tile"))
    write_png(grass / "001_grass.png")
    add(grass, "001_grass.png", "raw", "source", [])
    return tmp_path


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


# R2.1, R2.2, R2.6 — what exists, in one order, per medium.


def test_image_list_reports_every_image_in_chain_order(workspace: Path) -> None:
    code, payload = run("image", "list")
    assert code == 0
    assert [(entry["kind"], entry["key"], entry["path"]) for entry in payload["files"]] == [
        ("character", "hero", "001_hero.png"),
        ("character", "hero", "002_hero.snap.png"),
        ("tile", "grass", "001_grass.png"),
    ]
    assert payload["count"] == 3
    assert payload["summary"] == "3 images, 1 unclassified"


def test_a_listed_file_carries_what_a_caller_needs_to_act(workspace: Path) -> None:
    _, payload = run("image", "list", "--stage", "snap")
    assert payload["files"] == [
        {
            "kind": "character",
            "key": "hero",
            "stage": "snap",
            "class": "derived",
            "path": "002_hero.snap.png",
            "media": "image",
            "sha256": payload["files"][0]["sha256"],
            "derived_from": ["001_hero.png"],
            "produced_by": {"command": "test", "params": {}, "cache_key": None},
        }
    ]


def test_video_list_reports_only_videos(workspace: Path) -> None:
    code, payload = run("video", "list")
    assert code == 0
    assert [entry["path"] for entry in payload["files"]] == ["003_hero.mp4"]
    assert payload["files"][0]["media"] == "video"


# R1.2 — a file in neither medium is reported, not dropped.


def test_a_file_in_neither_medium_is_reported_by_both_listings(workspace: Path) -> None:
    for noun in ("image", "video"):
        _, payload = run(noun, "list")
        assert [entry["path"] for entry in payload["unclassified"]] == ["004_hero.boxes.json"]


# R2.3, R2.4, R2.5, R2.7 — the filters, and an empty answer that is not an error.


def test_a_kind_filters_the_listing(workspace: Path) -> None:
    _, payload = run("image", "list", "tile")
    assert [entry["key"] for entry in payload["files"]] == ["grass"]
    assert payload["unclassified"] == []


def test_a_class_filters_the_listing(workspace: Path) -> None:
    _, payload = run("image", "list", "--class", "source")
    assert [entry["path"] for entry in payload["files"]] == ["001_hero.png", "001_grass.png"]


def test_an_unknown_class_is_refused_by_the_parser(workspace: Path) -> None:
    result = CliRunner().invoke(main, ["image", "list", "--class", "invented"])
    assert result.exit_code == 2


def test_nothing_matching_is_an_empty_listing_and_exit_zero(workspace: Path) -> None:
    code, payload = run("image", "list", "--stage", "nobody-has-this")
    assert code == 0
    assert payload["files"] == []
    assert payload["count"] == 0
    assert payload["summary"] == "0 images"


def test_an_empty_workspace_lists_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    code, payload = run("image", "list")
    assert (code, payload["files"], payload["count"]) == (0, [], 0)


# R3.1, R3.4, R3.6 — one file, what produced it, and where it came from.


def test_show_defaults_to_the_last_file_of_that_medium(workspace: Path) -> None:
    code, payload = run("image", "show", "hero")
    assert code == 0
    assert payload["file"]["stage"] == "snap"
    assert payload["file"]["produced_by"]["command"] == "test"
    assert [entry["path"] for entry in payload["lineage"]] == ["001_hero.png"]


def test_show_reports_the_lineage_roots_first(workspace: Path) -> None:
    code, payload = run("video", "show", "hero")
    assert code == 0
    assert payload["file"]["path"] == "003_hero.mp4"
    assert [entry["path"] for entry in payload["lineage"]] == [
        "001_hero.png",
        "002_hero.snap.png",
    ]


def test_a_stage_is_addressed_by_name(workspace: Path) -> None:
    _, payload = run("image", "show", "hero", "--stage", "anchor")
    assert payload["file"]["path"] == "001_hero.png"
    assert payload["lineage"] == []


# R3.2, R3.3 — the address, and the refusal when it is not enough.


def test_an_asset_can_be_addressed_by_kind_and_key(workspace: Path) -> None:
    code, payload = run("image", "show", "tile/grass")
    assert (code, payload["file"]["key"]) == (0, "grass")


def test_a_bare_key_in_two_kinds_exits_two(workspace: Path, tmp_path: Path) -> None:
    twin = tmp_path / "assets/tile/hero"
    twin.mkdir(parents=True)
    meta.save(twin, meta.AssetMeta(key="hero", kind="tile"))

    code, payload = run("image", "show", "hero")
    assert code == 2
    assert payload["error"]["code"] == "ambiguous-key"
    assert "character" in payload["error"]["message"] and "tile" in payload["error"]["message"]
    assert payload["error"]["fix"].endswith("character/hero")


# R3.5 — the stage that is not there, and the medium that is not there.


def test_an_unknown_stage_exits_two_and_names_the_stages_there_are(workspace: Path) -> None:
    code, payload = run("image", "show", "hero", "--stage", "nobg")
    assert code == 2
    assert payload["error"]["code"] == "unknown-stage"
    assert "anchor, snap" in payload["error"]["message"]


def test_an_asset_with_no_file_of_that_medium_exits_two(workspace: Path) -> None:
    code, payload = run("video", "show", "tile/grass")
    assert code == 2
    assert payload["error"]["code"] == "no-file"
    assert payload["error"]["fix"] == "ssc video list tile"


# R3.8, R3.9, R3.10 — the measurement, and saying why when there is none.


def test_showing_an_image_measures_it(workspace: Path) -> None:
    _, payload = run("image", "show", "hero")
    checks = {finding["check"] for finding in payload["doctor"]["checks"]}
    # `seam` rides along skipped: `show` does not know whether this asset is meant to tile,
    # and a report that leaves a check out is indistinguishable from one where it was clean.
    assert checks == {
        "pixel_grid",
        "bleed",
        "drift",
        "halo",
        "palette",
        "flicker",
        "silhouette",
        "seam",
    }
    assert payload["doctor_skipped"] is None


def test_showing_a_video_reports_no_doctor_and_says_why(workspace: Path) -> None:
    _, payload = run("video", "show", "hero")
    assert payload["doctor"] is None
    assert "003_hero.mp4" in payload["doctor_skipped"]


def test_no_doctor_reports_the_file_without_measuring_it(workspace: Path) -> None:
    _, payload = run("image", "show", "hero", "--no-doctor")
    assert payload["doctor"] is None
    assert payload["doctor_skipped"] == "--no-doctor was given"
    assert payload["file"]["path"] == "002_hero.snap.png"


def test_a_record_whose_file_is_gone_still_shows_with_its_lineage(workspace: Path) -> None:
    """`ssc clean` removes a derived file *and* its record, so this state comes from
    somebody deleting by hand — and the record is exactly what explains it."""
    (workspace / "assets/character/hero/002_hero.snap.png").unlink()
    code, payload = run("image", "show", "hero")
    assert code == 0
    assert payload["doctor"] is None
    assert "not on disk" in payload["doctor_skipped"]


# R4.1, inherited from workspace-foundation — one object on stdout, both nouns.


@pytest.mark.parametrize("argv", [("image", "list"), ("video", "list"), ("image", "show", "hero")])
def test_json_is_one_object_and_nothing_else(workspace: Path, argv: tuple[str, ...]) -> None:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["command"] == f"{argv[0]} {argv[1]}"


@pytest.mark.skipif(sys.platform == "win32", reason="creating a symlink needs a privilege")
def test_show_refuses_a_recorded_file_that_symlinks_out_of_the_workspace(
    workspace: Path,
) -> None:
    """R4.2 end to end: the gate has to be in the command's path, not only in the library."""
    victim = workspace.parent / "victim.png"
    write_png(victim)
    target = workspace / "assets/character/hero/002_hero.snap.png"
    target.unlink()
    target.symlink_to(victim)

    code, payload = run("image", "show", "hero")
    assert code == 1
    assert payload["error"]["code"] == "path-escapes-asset"


@pytest.mark.parametrize("address", ["hero", "character/hero"])
def test_show_refuses_a_linked_asset_directory_by_either_address(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    link_dir: Callable[[Path, Path], None],
    address: str,
) -> None:
    """R4.1 end to end, through both branches of the address. Reported through the CLI
    because the two branches reach the asset directory by different routes, and the
    library test alone would not have caught one of them being unguarded."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    elsewhere = tmp_path / "outside" / "hero"
    elsewhere.mkdir(parents=True)
    meta.save(elsewhere, meta.AssetMeta(key="hero", kind="character"))
    write_png(elsewhere / "001_secret.png")
    add(elsewhere, "001_secret.png", "anchor", "source", [])
    (tmp_path / "assets" / "character").mkdir(parents=True)
    link_dir(tmp_path / "assets" / "character" / "hero", elsewhere)

    code, payload = run("image", "show", address)
    assert code == 1
    assert payload["error"]["code"] == "asset-escapes-workspace"


def test_without_json_a_human_gets_one_line(workspace: Path) -> None:
    result = CliRunner().invoke(main, ["image", "list"], catch_exceptions=False)
    assert result.output.strip() == "3 images, 1 unclassified"
