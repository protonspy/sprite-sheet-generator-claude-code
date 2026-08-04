"""`ssc run` and `ssc status` — specs/gates-and-resume R4.1..R4.9.

The resume tests are the point: every one of them kills the run and starts a fresh command,
so what is asserted is that the *repository* said where things stood.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main
from ssc.core.bgremove import PRESETS


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def green_png(path: Path) -> None:
    frame = np.zeros((12, 12, 4), dtype=np.uint8)
    frame[..., :3] = PRESETS["green"]
    frame[..., 3] = 255
    frame[4:8, 4:8, :3] = (200, 30, 30)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame, mode="RGBA").save(path)


def declare(root: Path, *steps: dict[str, Any]) -> None:
    document = yaml.safe_load((root / "ssc.yaml").read_text(encoding="utf-8")) or {}
    document["pipeline"] = list(steps)
    (root / "ssc.yaml").write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")


@pytest.fixture
def hero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace with one character asset holding two cut frames."""
    monkeypatch.chdir(tmp_path)
    assert run("init")[0] == 0
    assert run("asset", "new", "hero", "--kind", "character")[0] == 0

    sheet = tmp_path / "sheet.png"
    frame = np.zeros((12, 24, 4), dtype=np.uint8)
    frame[..., :3] = PRESETS["green"]
    frame[..., 3] = 255
    frame[4:8, 4:8, :3] = (200, 30, 30)
    frame[4:8, 16:20, :3] = (30, 200, 30)
    Image.fromarray(frame, mode="RGBA").save(sheet)
    assert (
        run("tool", "cut", "--in", str(sheet), "--grid", "2x1", "--asset", "character/hero")[0] == 0
    )
    return tmp_path


# R4.7 — no pipeline.
def test_a_workspace_with_no_pipeline_refuses_to_run(hero: Path) -> None:
    code, payload = run("run", "character/hero")
    assert code == 2
    assert payload["error"]["code"] == "no-pipeline"


def test_a_workspace_with_no_pipeline_refuses_to_report_status(hero: Path) -> None:
    code, payload = run("status", "character/hero")
    assert code == 2
    assert payload["error"]["code"] == "no-pipeline"


# R4.1 — the steps run in order.
def test_a_pipeline_runs_every_step_and_records_each_stage(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    code, payload = run("run", "character/hero")
    assert code == 0
    assert payload["complete"] is True
    assert payload["ran"] == ["nobg", "pixels"]

    record = json.loads((hero / "assets/character/hero/meta.json").read_text(encoding="utf-8"))
    assert {entry["stage"] for entry in record["files"]} >= {"frames", "nobg", "pixels"}
    assert (hero / "assets/character/hero/frames/nobg").is_dir()
    assert len(list((hero / "assets/character/hero/frames/pixels").glob("*.png"))) == 2


# R4.2 — resuming skips what is recorded.
def test_running_again_does_nothing_because_the_stages_are_recorded(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})
    assert run("run", "character/hero")[0] == 0

    code, payload = run("run", "character/hero")
    assert code == 0
    assert payload["ran"] == []
    assert payload["complete"] is True


def test_a_pipeline_extended_afterwards_runs_only_the_new_step(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})
    assert run("run", "character/hero")[0] == 0

    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    code, payload = run("run", "character/hero")
    assert code == 0
    assert payload["ran"] == ["pixels"]


# R4.3 — a gated step stops the run once its output exists.
def test_a_gated_step_produces_its_output_then_opens_a_gate_and_stops(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}, "gate": "key ok?"},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    code, payload = run("run", "character/hero")
    assert code == 3
    assert payload["ok"] is True
    assert payload["complete"] is False
    assert payload["ran"] == ["nobg"]
    assert payload["stopped_at"] == "nobg"
    assert payload["gate"]["question"] == "key ok?"
    # The output the person is being asked about exists.
    assert (hero / "assets/character/hero/frames/nobg").is_dir()
    # The step after it did not run.
    assert not (hero / "assets/character/hero/frames/pixels").exists()


def test_the_gate_points_at_the_material_to_look_at(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove", "gate": "key ok?"})
    _, payload = run("run", "character/hero")
    assert Path(payload["gate"]["material"]).is_dir()


def test_running_again_while_the_gate_is_pending_stops_in_the_same_place(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "gate": "key ok?"},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    assert run("run", "character/hero")[0] == 3

    code, payload = run("run", "character/hero")
    assert code == 3
    assert payload["ran"] == []
    assert payload["stopped_at"] == "nobg"


# R4.4 — an approved gate lets the run continue.
def test_approving_the_gate_lets_the_run_finish(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "gate": "key ok?"},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.nobg", "--choice", "as-is")[0] == 0

    code, payload = run("run", "character/hero")
    assert code == 0
    assert payload["complete"] is True
    assert payload["ran"] == ["pixels"]


# R4.5 — a rejected gate stops the run and says so.
def test_rejecting_the_gate_stops_the_run(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "gate": "key ok?"},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "reject", "hero.nobg", "--why", "the edges halo")[0] == 0

    code, payload = run("run", "character/hero")
    assert code == 1
    assert payload["error"]["code"] == "gate-rejected"
    assert "the edges halo" in payload["error"]["message"]
    assert not (hero / "assets/character/hero/frames/pixels").exists()


# R3.2 through a run — an adopted default does not stop it again.
def test_a_gate_on_an_adopted_topic_does_not_stop_the_run(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove", "gate": "key ok?"})
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.nobg", "--choice", "as-is", "--default")[0] == 0

    assert run("asset", "new", "boss", "--kind", "character")[0] == 0
    green_png(hero / "assets/character/boss/frames/001.png")
    record = json.loads((hero / "assets/character/boss/meta.json").read_text(encoding="utf-8"))
    record["files"].append(
        {
            "path": "frames",
            "stage": "frames",
            "class": "derived",
            "sha256": "0" * 64,
            "produced_by": {"command": "test", "params": {}, "cache_key": None},
            "derived_from": [],
            "written_at": "2026-08-04T12:00:00Z",
        }
    )
    (hero / "assets/character/boss/meta.json").write_text(json.dumps(record), encoding="utf-8")

    code, payload = run("run", "character/boss")
    assert code == 0
    assert payload["complete"] is True


# R4.6 — status.
def test_status_reports_every_step_and_what_runs_next(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    code, payload = run("status", "character/hero")
    assert code == 0
    assert [one["state"] for one in payload["steps"]] == ["outstanding", "outstanding"]
    assert payload["next"] == "nobg"
    assert payload["blocked_by"] is None


def test_status_reports_what_is_done_after_a_partial_run(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "gate": "key ok?"},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    run("run", "character/hero")

    code, payload = run("status", "character/hero")
    assert code == 0
    assert [one["state"] for one in payload["steps"]] == ["blocked", "outstanding"]
    assert payload["blocked_by"] == "nobg"
    assert payload["done"] == 0


def test_status_of_a_finished_pipeline_has_no_next(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})
    run("run", "character/hero")

    code, payload = run("status", "character/hero")
    assert code == 0
    assert payload["next"] is None
    assert payload["done"] == 1


# R4.8, R4.9 — refused before anything runs.
def test_a_step_that_would_bill_refuses_the_run(hero: Path) -> None:
    declare(hero, {"stage": "art", "command": "gen image"})
    code, payload = run("run", "character/hero")
    assert code == 2
    assert payload["error"]["code"] == "paid-step"


def test_a_bad_later_step_stops_the_run_before_the_first_one(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colours": 8}},
    )
    code, payload = run("run", "character/hero")
    assert code == 2
    assert payload["error"]["code"] == "unknown-parameter"
    assert not (hero / "assets/character/hero/frames/nobg").exists()


# --dry-run.
def test_a_dry_run_says_what_would_run_and_writes_nothing(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})
    code, payload = run("run", "character/hero", "--dry-run")
    assert code == 0
    assert payload["would_run"] == "nobg"
    assert not (hero / "assets/character/hero/frames/nobg").exists()


def test_an_asset_that_does_not_exist_is_refused(hero: Path) -> None:
    declare(hero, {"stage": "nobg", "command": "bgremove"})
    code, payload = run("run", "character/nobody")
    assert code == 2
    assert payload["error"]["code"] == "no-asset"


# Frames are read through the held directory, with a byte ceiling — not by resolving a
# path and handing it to `Image.open`.
def test_a_step_reads_its_source_frames_through_the_binding(
    hero: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssc.cli.atomic import Directory

    seen: list[str] = []
    real = Directory.read

    def watched(self: Directory, relative: str, *, max_bytes: int | None = None) -> bytes:
        seen.append(relative)
        if relative.startswith("frames/"):
            # `meta.json` is legitimately read without one; a frame is not.
            assert max_bytes is not None, f"{relative} was read with no byte ceiling"
        return real(self, relative, max_bytes=max_bytes)

    monkeypatch.setattr(Directory, "read", watched)

    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})
    assert run("run", "character/hero")[0] == 0
    assert [name for name in seen if name.startswith("frames/")] == [
        "frames/001.png",
        "frames/002.png",
    ]


def test_a_recorded_stage_whose_files_are_gone_is_a_finding(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 8}},
    )
    for child in (hero / "assets/character/hero/frames").glob("*.png"):
        child.unlink()

    code, payload = run("run", "character/hero")
    assert code == 1
    assert payload["error"]["code"] == "stage-missing"


# The ceiling on a whole set, which `read_frames` enforces and the hand-rolled bound read
# initially lost: per-file limits do not bound N files.
def test_a_stage_over_the_set_pixel_ceiling_is_refused(
    hero: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patched on `listing`, which is where the bound read moved when
    # `specs/engine-index/` needed the same one for every asset at once.
    from ssc.cli import listing

    monkeypatch.setattr(listing, "MAX_SET_PIXELS", 200)
    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})

    code, payload = run("run", "character/hero")
    assert code == 1
    assert payload["error"]["code"] == "set-too-large"


def test_a_stage_inside_the_set_pixel_ceiling_still_runs(
    hero: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssc.cli import listing

    monkeypatch.setattr(listing, "MAX_SET_PIXELS", 100_000)
    declare(hero, {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}})
    assert run("run", "character/hero")[0] == 0
