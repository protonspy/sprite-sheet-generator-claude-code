"""R1 — finding a workspace, creating one, and what happens without one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.errors import UsageError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


def test_a_directory_with_the_marker_is_a_workspace(tmp_path: Path) -> None:
    (tmp_path / ws.MARKER).write_text("schema: 1\n")
    found = ws.find(tmp_path)
    assert found is not None
    assert found.root == tmp_path.resolve()


def test_the_search_walks_up(tmp_path: Path) -> None:
    """R1.4 — running from inside `assets/character/hero/` still finds the root."""
    (tmp_path / ws.MARKER).write_text("schema: 1\n")
    deep = tmp_path / "assets/character/hero"
    deep.mkdir(parents=True)
    found = ws.find(deep)
    assert found is not None
    assert found.root == tmp_path.resolve()


def test_no_marker_anywhere_is_no_workspace(tmp_path: Path) -> None:
    assert ws.find(tmp_path) is None


def test_requiring_one_that_is_missing_names_the_command_that_makes_it(tmp_path: Path) -> None:
    with pytest.raises(UsageError) as raised:
        ws.require(tmp_path)
    assert raised.value.code == "no-workspace"
    assert raised.value.exit_code == 2
    assert raised.value.fix == "ssc init"


def test_the_paths_hang_off_the_root(tmp_path: Path) -> None:
    workspace = ws.Workspace(root=tmp_path)
    assert workspace.assets == tmp_path / "assets"
    assert workspace.cache == tmp_path / "cache"


def test_an_asset_lives_under_its_kind(tmp_path: Path) -> None:
    """adr:0007 — kind first, then key."""
    workspace = ws.Workspace(root=tmp_path)
    assert workspace.asset_dir("character", "hero") == tmp_path / "assets/character/hero"


def test_creating_lays_out_the_three_things(tmp_path: Path) -> None:
    """R1.2."""
    workspace = ws.create(tmp_path)
    assert workspace.config_path.is_file()
    assert workspace.assets.is_dir()
    assert workspace.cache.is_dir()


def test_the_config_records_only_its_schema(tmp_path: Path) -> None:
    """Inventing keys for budget or kinds now would be inventing later leaves' designs."""
    import yaml

    ws.create(tmp_path)
    assert yaml.safe_load((tmp_path / ws.MARKER).read_text()) == {"schema": ws.SCHEMA}


def test_creating_over_an_existing_workspace_is_refused(tmp_path: Path) -> None:
    """R1.3."""
    ws.create(tmp_path)
    with pytest.raises(UsageError) as raised:
        ws.create(tmp_path)
    assert raised.value.code == "workspace-exists"


def test_a_command_that_declares_no_workspace_runs_without_one(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R1.6 — `snap` and `pixelart` work on loose files for somebody who never ran init."""
    monkeypatch.chdir(tmp_path)

    @ssc_command("standalone")
    def standalone(*, dry_run: bool) -> Result:
        return Result("standalone", "ran")

    assert CliRunner().invoke(standalone, []).exit_code == 0


def test_init_creates_a_workspace_and_says_where(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert Path(payload["config"]).is_file()
    assert Path(payload["assets"]).is_dir()


def test_init_twice_is_invalid_usage(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    result = CliRunner().invoke(main, ["init", "--json"], catch_exceptions=False)
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "workspace-exists"


def test_init_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R4.3."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--dry-run", "--json"], catch_exceptions=False)
    assert json.loads(result.output)["dry_run"] is True
    assert list(tmp_path.iterdir()) == []


def test_init_dry_run_refuses_where_the_real_run_would(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A dry run that reports success where the real one fails is worse than no dry run."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    result = CliRunner().invoke(main, ["init", "--dry-run"], catch_exceptions=False)
    assert result.exit_code == 2
