"""R6.1 · R6.2 · R6.3 — `ssc clean` deletes `derived` and nothing else.

Written before `ssc clean` existed. A `source` is what a model produced: it cost money and
it is not reproducible, so "clean deleted my anchor" is not a bug you fix afterwards. The
first test here is the one that mattered.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from conftest import load_meta, save_meta

from ssc.cli import meta
from ssc.cli.app import main


def workspace_with_a_chain(tmp_path: Path) -> Path:
    """An asset carrying one file of each class, with real bytes behind each record."""
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    directory = tmp_path / "assets/character/hero"
    directory.mkdir(parents=True)
    (directory / "001_anchor.png").write_bytes(b"paid for")
    (directory / "002_anchor.snap.png").write_bytes(b"computed")
    (directory / "003_anchor.sheet.png").write_bytes(b"delivered")

    record = meta.AssetMeta(key="hero", kind="character")
    for path, stage, file_class, data in (
        ("001_anchor.png", "anchor", "source", b"paid for"),
        ("002_anchor.snap.png", "snap", "derived", b"computed"),
        ("003_anchor.sheet.png", "sheet", "output", b"delivered"),
    ):
        meta.record(
            record,
            path=path,
            stage=stage,
            file_class=file_class,  # type: ignore[arg-type]
            data=data,
            produced_by=meta.Provenance(command="test"),
        )
    save_meta(directory, record)
    return directory


def test_a_source_survives(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    directory = workspace_with_a_chain(tmp_path)
    CliRunner().invoke(main, ["clean"], catch_exceptions=False)
    assert (directory / "001_anchor.png").read_bytes() == b"paid for"


def test_an_output_survives(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    directory = workspace_with_a_chain(tmp_path)
    CliRunner().invoke(main, ["clean"], catch_exceptions=False)
    assert (directory / "003_anchor.sheet.png").exists()


def test_the_derived_file_goes(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    directory = workspace_with_a_chain(tmp_path)
    result = CliRunner().invoke(main, ["clean", "--json"], catch_exceptions=False)
    assert result.exit_code == 0
    assert not (directory / "002_anchor.snap.png").exists()
    assert json.loads(result.output)["deleted"] == ["character/hero/002_anchor.snap.png"]


def test_the_record_follows_the_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R6.3 — a record pointing at nothing is worse than no record, because the next
    command believes it."""
    monkeypatch.chdir(tmp_path)
    directory = workspace_with_a_chain(tmp_path)
    CliRunner().invoke(main, ["clean"], catch_exceptions=False)
    stages = {entry.stage for entry in load_meta(directory).files}
    assert stages == {"anchor", "sheet"}


def test_dry_run_deletes_nothing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    directory = workspace_with_a_chain(tmp_path)
    result = CliRunner().invoke(main, ["clean", "--dry-run", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["deleted"] == ["character/hero/002_anchor.snap.png"]
    assert (directory / "002_anchor.snap.png").exists()
    assert len(load_meta(directory).files) == 3


def test_a_derived_record_whose_file_already_went_is_still_tidied(
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """Someone deleted it by hand. The record has to go too, or `--stage snap` resolves
    to a path that is not there."""
    monkeypatch.chdir(tmp_path)
    directory = workspace_with_a_chain(tmp_path)
    (directory / "002_anchor.snap.png").unlink()
    CliRunner().invoke(main, ["clean"], catch_exceptions=False)
    assert {entry.stage for entry in load_meta(directory).files} == {"anchor", "sheet"}


def test_cleaning_twice_is_not_an_error(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    workspace_with_a_chain(tmp_path)
    CliRunner().invoke(main, ["clean"], catch_exceptions=False)
    second = CliRunner().invoke(main, ["clean", "--json"], catch_exceptions=False)
    assert second.exit_code == 0
    assert json.loads(second.output)["deleted"] == []


def test_clean_outside_a_workspace_is_a_usage_error(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["clean", "--json"], catch_exceptions=False)
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["fix"] == "ssc init"
