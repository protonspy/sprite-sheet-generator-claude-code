"""`ssc clean` deletes files, so the two gates that keep it inside an asset are tested
against the exact attacks the security review demonstrated.

The first gate is `meta.py`, which will not load a record naming a path outside the asset.
The second is `clean.inside`, which re-resolves at the moment of deleting — one validation
gap should not be all that stands between a hand-edited file and `shutil.rmtree`.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner

from ssc.cli import meta
from ssc.cli.app import main
from ssc.cli.commands.clean import inside
from ssc.cli.errors import SscError


def poisoned_workspace(tmp_path: Path, path_value: str) -> Path:
    """A workspace whose one asset records `path_value` as a deletable file."""
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    directory = tmp_path / "assets/character/hero"
    directory.mkdir(parents=True)
    (directory / meta.META_NAME).write_text(
        json.dumps(
            {
                "schema": 1,
                "key": "hero",
                "kind": "character",
                "created_at": "2026-08-02T00:00:00Z",
                "files": [
                    {
                        "path": path_value,
                        "stage": "evil",
                        "class": "derived",
                        "sha256": "0" * 64,
                        "produced_by": {"command": "hand-edit", "params": {}, "cache_key": None},
                        "derived_from": [],
                        "written_at": "2026-08-02T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.mark.parametrize("path_value", ["../../../../victim", "..", ".", "/etc/passwd"])
def test_clean_will_not_load_a_record_that_points_outside(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_value: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    victim = tmp_path.parent / "victim"
    victim.mkdir(exist_ok=True)
    (victim / "paid-for.png").write_bytes(b"not reproducible")

    poisoned_workspace(tmp_path, path_value)
    result = CliRunner().invoke(main, ["clean", "--json"], catch_exceptions=False)

    assert result.exit_code == 1
    error = json.loads(result.output)["error"]
    assert error["code"] == "meta-invalid"
    # The reason, not just a count: an operator told to fix a file by hand needs to
    # know which field is wrong.
    assert "files.0.path" in error["message"]
    assert (victim / "paid-for.png").exists()


def test_the_delete_gate_refuses_an_escaping_path_on_its_own(tmp_path: Path) -> None:
    """`inside` is the second gate, tested without the first: it has to hold alone."""
    asset = tmp_path / "assets/character/hero"
    asset.mkdir(parents=True)
    with pytest.raises(SscError) as raised:
        inside(asset, "../../../../etc")
    assert raised.value.code == "path-escapes-asset"


def test_the_delete_gate_refuses_the_asset_directory_itself(tmp_path: Path) -> None:
    """`.` names the asset, sources and all. It is not a derived file."""
    asset = tmp_path / "assets/character/hero"
    asset.mkdir(parents=True)
    with pytest.raises(SscError):
        inside(asset, ".")


def test_the_delete_gate_allows_what_belongs(tmp_path: Path) -> None:
    asset = tmp_path / "assets/character/hero"
    (asset / "frames").mkdir(parents=True)
    assert inside(asset, "frames/003.png") == (asset / "frames/003.png").resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="creating a symlink needs a privilege")
def test_a_symlink_cannot_move_the_target_after_validation(tmp_path: Path) -> None:
    """The reason the second gate re-resolves rather than trusting the recorded string."""
    asset = tmp_path / "assets/character/hero"
    asset.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (asset / "002_anchor.snap.png").symlink_to(victim, target_is_directory=True)

    with pytest.raises(SscError) as raised:
        inside(asset, "002_anchor.snap.png")
    assert raised.value.code == "path-escapes-asset"
    assert victim.is_dir()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_a_written_file_is_not_world_readable(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    mode = os.stat(tmp_path / "ssc.yaml").st_mode & 0o777
    assert mode == 0o600


def test_asset_new_cannot_write_outside_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The escape the security review demonstrated: two ordinary CLI arguments."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    result = runner.invoke(
        main,
        ["asset", "new", "pwn", "--kind", "../../../../escaped", "--json"],
        catch_exceptions=False,
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "invalid-name"
    assert not (tmp_path.parent / "escaped").exists()


def test_an_absolute_kind_cannot_discard_the_workspace_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Path("/w/assets") / "C:/Windows"` is `C:/Windows` — one argument, no `..` needed."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    result = runner.invoke(
        main, ["asset", "new", "pwn", "--kind", "C:/Windows/Temp", "--json"], catch_exceptions=False
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "invalid-name"


def test_asset_new_refuses_a_kind_directory_that_is_a_link_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, link_dir: Callable[[Path, Path], None]
) -> None:
    """A valid name is not a valid destination. `assets/<kind>/` linked elsewhere makes an
    otherwise ordinary `--kind character` create a directory and write `meta.json` outside
    the workspace — reading was already guarded, creating was not."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    link_dir(tmp_path / "assets" / "character", elsewhere)

    result = runner.invoke(
        main, ["asset", "new", "hero", "--kind", "character", "--json"], catch_exceptions=False
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["error"]["code"] == "asset-escapes-workspace"
    assert not (elsewhere / "hero").exists()
