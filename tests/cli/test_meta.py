"""R2 · R3 — the asset record: filenames, classes, stages, and provenance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import load_meta, save_meta

from ssc.cli import meta
from ssc.cli.app import main
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError, UsageError


def asset() -> meta.AssetMeta:
    return meta.AssetMeta(key="hero", kind="character")


def add(record: meta.AssetMeta, path: str, stage: str, file_class: str = "derived") -> None:
    meta.record(
        record,
        path=path,
        stage=stage,
        file_class=file_class,  # type: ignore[arg-type]
        data=path.encode(),
        produced_by=meta.Provenance(command="test"),
    )


def test_a_filename_carries_its_number_and_its_stages() -> None:
    """R2.1 — one `ls` reads the whole chain in order."""
    assert meta.filename(1, "anchor_s", [], "png") == "001_anchor_s.png"
    assert meta.filename(2, "anchor_s", ["snap"], "png") == "002_anchor_s.snap.png"
    assert meta.filename(3, "anchor_s", ["snap", "nobg"], ".png") == "003_anchor_s.snap.nobg.png"


def test_prefixes_are_zero_padded_and_keep_sorting_past_nine() -> None:
    assert meta.filename(9, "a", [], "png") < meta.filename(10, "a", [], "png")


def test_the_next_prefix_follows_the_highest_used() -> None:
    record = asset()
    add(record, "001_anchor.png", "anchor")
    add(record, "002_anchor.snap.png", "snap")
    assert record.next_prefix() == 3


def test_deleting_a_file_never_renumbers_the_ones_that_remain() -> None:
    """The actual guarantee. A gap in the middle stays a gap, so `ssc clean` cannot
    shuffle the numbers a human has been reading."""
    record = asset()
    add(record, "001_anchor.png", "anchor")
    add(record, "002_anchor.snap.png", "snap")
    add(record, "003_anchor.nobg.png", "nobg")

    record.files = [entry for entry in record.files if entry.stage != "snap"]

    assert [entry.path for entry in record.files] == ["001_anchor.png", "003_anchor.nobg.png"]
    assert record.next_prefix() == 4


def test_the_number_freed_by_deleting_the_last_file_is_handed_out_again() -> None:
    """Stated rather than prevented: the prefix is presentation, never an address (R2.4),
    so reissuing the highest one costs nothing. Anything stronger would need a high-water
    mark in the schema for no benefit."""
    record = asset()
    add(record, "001_anchor.png", "anchor")
    add(record, "002_anchor.snap.png", "snap")

    record.files = [entry for entry in record.files if entry.stage != "snap"]

    assert record.next_prefix() == 2


def test_an_empty_asset_starts_at_one() -> None:
    assert asset().next_prefix() == 1


def test_a_stage_resolves_without_anybody_counting_prefixes() -> None:
    """R3.3 — the point of recording a stage at all."""
    record = asset()
    add(record, "001_anchor.png", "anchor")
    add(record, "002_anchor.snap.png", "snap")
    assert record.stage("snap").path == "002_anchor.snap.png"


def test_an_unknown_stage_says_which_ones_exist() -> None:
    record = asset()
    add(record, "001_anchor.png", "anchor")
    with pytest.raises(UsageError) as raised:
        record.stage("nobg")
    assert raised.value.code == "unknown-stage"
    assert "anchor" in raised.value.message


def test_two_files_cannot_share_a_stage() -> None:
    """R3.4 — an ambiguity resolved by taking the first match goes unnoticed for months."""
    record = asset()
    add(record, "001_anchor.png", "anchor")
    with pytest.raises(UsageError) as raised:
        add(record, "002_other.png", "anchor")
    assert raised.value.code == "stage-taken"
    assert len(record.files) == 1


def test_one_path_cannot_be_recorded_twice() -> None:
    record = asset()
    add(record, "001_anchor.png", "anchor")
    with pytest.raises(SscError) as raised:
        add(record, "001_anchor.png", "other")
    assert raised.value.code == "file-recorded"


def test_a_record_carries_the_digest_of_what_was_written() -> None:
    """R3.1 — the record has to be checkable against the file, not merely descriptive."""
    record = asset()
    meta.record(
        record,
        path="001_anchor.png",
        stage="anchor",
        file_class="source",
        data=b"pixels",
        produced_by=meta.Provenance(command="gen image", params={"seed": 7}),
        derived_from=[],
    )
    entry = record.files[0]
    assert entry.sha256 == meta.digest(b"pixels")
    assert entry.produced_by.params == {"seed": 7}


def test_a_class_outside_the_three_is_rejected() -> None:
    """R3.2 — exactly one class, from a closed set. `clean` reads nothing else."""
    with pytest.raises(ValueError):
        meta.FileRecord(
            path="x.png",
            stage="x",
            **{"class": "temporary"},  # type: ignore[arg-type]
            sha256="0" * 64,
            produced_by=meta.Provenance(command="t"),
        )


def test_the_record_round_trips_through_disk(tmp_path: Path) -> None:
    record = asset()
    add(record, "001_anchor.png", "anchor", "source")
    save_meta(tmp_path, record)
    assert load_meta(tmp_path) == record


def test_the_written_json_uses_the_field_names_the_contract_promises(tmp_path: Path) -> None:
    """`class` and `schema`, not `file_class` and `schema_version` — the JSON is the
    public interface, and a harness reads it, not the Python."""
    record = asset()
    add(record, "001_anchor.png", "anchor", "source")
    save_meta(tmp_path, record)
    payload = json.loads((tmp_path / meta.META_NAME).read_text())
    assert payload["schema"] == meta.SCHEMA
    assert payload["files"][0]["class"] == "source"


def test_loading_from_a_directory_that_is_not_an_asset_says_how_to_make_one(
    tmp_path: Path,
) -> None:
    with pytest.raises(UsageError) as raised:
        load_meta(tmp_path)
    assert raised.value.code == "no-asset"
    assert raised.value.fix is not None


def test_frames_is_the_only_subdirectory(tmp_path: Path) -> None:
    """R2.5, listed through the held directory per R3.7."""
    (tmp_path / meta.FRAMES_DIR).mkdir()
    with Directory.open(tmp_path) as held:
        meta.check_layout(held)

        (tmp_path / "sprites").mkdir()
        with pytest.raises(SscError) as raised:
            meta.check_layout(held)
    assert raised.value.code == "unexpected-subdirectory"
    assert "sprites" in raised.value.message


def test_asset_new_creates_the_directory_and_the_record(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R2.2."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    result = runner.invoke(
        main, ["asset", "new", "hero", "--kind", "character", "--json"], catch_exceptions=False
    )
    assert result.exit_code == 0
    directory = tmp_path / "assets/character/hero"
    assert json.loads(result.output)["path"] == str(directory)
    assert load_meta(directory).kind == "character"


def test_asset_new_refuses_a_key_the_kind_already_has(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R2.3."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    runner.invoke(main, ["asset", "new", "hero", "--kind", "character"], catch_exceptions=False)
    result = runner.invoke(
        main, ["asset", "new", "hero", "--kind", "character", "--json"], catch_exceptions=False
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "asset-exists"


def test_two_kinds_may_share_a_key(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Uniqueness is per kind. adr:0007 says why, and this is the behaviour it bought."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    runner.invoke(main, ["asset", "new", "grass", "--kind", "tile"], catch_exceptions=False)
    result = runner.invoke(
        main, ["asset", "new", "grass", "--kind", "icon"], catch_exceptions=False
    )
    assert result.exit_code == 0


def test_asset_new_dry_run_writes_nothing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["init"], catch_exceptions=False)
    runner.invoke(
        main, ["asset", "new", "hero", "--kind", "character", "--dry-run"], catch_exceptions=False
    )
    assert not (tmp_path / "assets/character/hero").exists()


def test_asset_new_outside_a_workspace_is_invalid_usage(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R1.5."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        main, ["asset", "new", "hero", "--kind", "character", "--json"], catch_exceptions=False
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "no-workspace"
