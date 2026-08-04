"""`ssc tool sweep` — specs/sweep-and-review R1.1, R1.5, R1.7, R2.1, R2.2, R2.3, R2.4, R4.*."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main
from ssc.core.bgremove import PRESETS


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def green_png(path: Path, width: int = 12, height: int = 12) -> Path:
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    frame[..., :3] = PRESETS["green"]
    frame[..., 3] = 255
    frame[4:8, 4:8, :3] = (200, 30, 30)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(frame, mode="RGBA").save(path)
    return path


@pytest.fixture
def art(tmp_path: Path) -> Path:
    return green_png(tmp_path / "hero.png")


@pytest.fixture
def art_set(tmp_path: Path) -> Path:
    source = tmp_path / "frames"
    for name in ("001_a.png", "002_b.png"):
        green_png(source / name)
    return source


# R1.1, R4.1 — one variant per point, all of it in one directory.
def test_a_sweep_writes_one_variant_per_point(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60,80",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert code == 0
    assert len(payload["variants"]) == 3
    assert all(one["status"] == "ok" for one in payload["variants"])
    assert {one["name"] for one in payload["variants"]} == {"00_tol-40", "01_tol-60", "02_tol-80"}
    for one in payload["variants"]:
        assert Path(one["path"]).is_dir()


def test_a_sweep_of_a_frame_set_writes_every_frame_of_every_variant(
    art_set: Path, tmp_path: Path
) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--in",
        str(art_set),
        "--out",
        str(where),
    )
    assert code == 0
    for one in payload["variants"]:
        assert len(one["written"]) == 2


# R1.2 — the cross product, through the command.
def test_two_varied_parameters_run_every_combination(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--vary",
        "mode=flood,global",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "review"),
    )
    assert code == 0
    assert len(payload["variants"]) == 4
    assert payload["variants"][0]["parameters"] == {"tol": "40", "mode": "flood"}


# R2.1, R2.2 — every variant is measured.
def test_every_variant_carries_its_own_doctor_report(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "review"),
    )
    assert code == 0
    for one in payload["variants"]:
        assert "checks" in one["doctor"]
        assert isinstance(one["doctor"]["defects"], int)
        assert isinstance(one["doctor"]["warnings"], int)


# R2.3 — reported as a measurement.
def test_the_fewest_defects_variant_is_named(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "review"),
    )
    assert code == 0
    counts = {one["index"]: one["doctor"]["defects"] for one in payload["variants"]}
    assert payload["fewest_defects"] in counts
    assert counts[payload["fewest_defects"]] == min(counts.values())


# R3.1 — the contact sheet.
def test_a_contact_sheet_is_written(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert code == 0
    assert Path(payload["contact_sheet"]).is_file()
    assert (where / "contact.png").is_file()


# R4.4 — the report can be read without the invocation that produced it.
def test_the_report_records_the_command_the_input_and_the_range(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    document = json.loads((where / "sweep.json").read_text(encoding="utf-8"))
    assert document["command"] == "bgremove"
    assert document["input"] == str(art)
    assert document["parameters"] == ["tol=40,60"]
    assert document["schema"] == 1


# R1.5, R1.6, R1.7 — refused before anything runs.
def test_a_command_that_cannot_be_swept_is_refused(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "gen",
        "--vary",
        "tol=40",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert code == 2
    assert payload["error"]["code"] == "unknown-command"
    assert not where.exists()


def test_a_parameter_the_command_does_not_take_is_refused(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tolerance=40",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert code == 2
    assert payload["error"]["code"] == "unknown-parameter"
    assert not where.exists()


def test_a_value_out_of_bounds_is_refused_before_any_variant_runs(
    art: Path, tmp_path: Path
) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,99999",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-value"
    # The valid first point did not run either.
    assert not where.exists()


def test_a_product_over_the_ceiling_is_refused_by_the_command(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=0..80:10",
        "--vary",
        "edge_trim=0..70:10",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "review"),
    )
    assert code == 2
    assert payload["error"]["code"] == "too-many-variants"


# R4.3 — a directory that already holds a sweep.
def test_a_second_sweep_into_the_same_directory_is_refused(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    argv = (
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert run(*argv)[0] == 0
    code, payload = run(*argv)
    assert code == 2
    assert payload["error"]["code"] == "sweep-exists"


def test_replace_runs_it_again(art: Path, tmp_path: Path) -> None:
    where = tmp_path / "review"
    argv = (
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert run(*argv)[0] == 0
    assert run(*argv, "--replace")[0] == 0


def test_replace_does_not_leave_the_previous_sweeps_variants_behind(
    art: Path, tmp_path: Path
) -> None:
    where = tmp_path / "review"
    run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60,80",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40",
        "--in",
        str(art),
        "--out",
        str(where),
        "--replace",
    )
    assert sorted(child.name for child in (where / "variants").iterdir()) == ["00_tol-40"]


# R4.2 — review/<key>/ inside a workspace.
def test_a_key_inside_a_workspace_writes_into_review(
    art: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    assert run("init")[0] == 0

    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40",
        "--in",
        str(art),
        "--key",
        "hero",
    )
    assert code == 0
    assert Path(payload["review"]) == workspace / "review" / "hero"
    assert (workspace / "review" / "hero" / "sweep.json").is_file()


def test_neither_out_nor_key_is_refused(art: Path) -> None:
    code, payload = run(
        "tool", "sweep", "--command", "bgremove", "--vary", "tol=40", "--in", str(art)
    )
    assert code == 2
    assert payload["error"]["code"] == "no-destination"


def test_both_out_and_key_is_refused(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "review"),
        "--key",
        "hero",
    )
    assert code == 2
    assert payload["error"]["code"] == "two-destinations"


# R4.5 — dry run.
def test_a_dry_run_writes_nothing_and_says_what_it_would_have_run(
    art: Path, tmp_path: Path
) -> None:
    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60",
        "--in",
        str(art),
        "--out",
        str(where),
        "--dry-run",
    )
    assert code == 0
    assert payload["dry_run"] is True
    assert len(payload["variants"]) == 2
    assert not where.exists()


# R2.4 — one variant failing does not end the sweep.
def test_a_variant_that_fails_is_recorded_and_the_rest_still_run(
    art: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssc.cli import steps

    real = steps.REGISTRY["bgremove"].run

    def explode_on_sixty(images: list[np.ndarray], given: dict[str, Any]) -> steps.Outcome:
        if given.get("tol") == 60:
            raise ValueError("this tolerance is unwell")
        return real(images, given)

    monkeypatch.setitem(
        steps.REGISTRY,
        "bgremove",
        steps.Runnable("bgremove", {"tol": steps.whole(0, 442)}, explode_on_sixty),
    )

    where = tmp_path / "review"
    code, payload = run(
        "tool",
        "sweep",
        "--command",
        "bgremove",
        "--vary",
        "tol=40,60,80",
        "--in",
        str(art),
        "--out",
        str(where),
    )
    assert code == 0
    states = {one["index"]: one["status"] for one in payload["variants"]}
    assert states == {0: "ok", 1: "failed", 2: "ok"}
    failed = next(one for one in payload["variants"] if one["status"] == "failed")
    assert "this tolerance is unwell" in failed["reason"]
    # The contact sheet still covers every point, including the empty cell.
    assert Path(payload["contact_sheet"]).is_file()
