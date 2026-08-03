"""What a kind means — specs/asset-kinds R1, R2, R3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner

from ssc.cli import kinds
from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.errors import SscError


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def workspace_with(tmp_path: Path, declared: dict[str, Any]) -> ws.Workspace:
    space = ws.create(tmp_path)
    space.config_path.write_text(yaml.safe_dump({"schema": 1, "kinds": declared}), encoding="utf-8")
    return space


# R1.1, R1.2 — the six the package ships.


def test_the_six_built_ins_are_there() -> None:
    assert set(kinds.BUILT_INS) == {"character", "icon", "tile", "ui", "banner", "map"}


def test_every_built_in_declares_every_field() -> None:
    for profile in kinds.BUILT_INS.values():
        emitted = profile.as_dict()
        assert set(emitted) >= kinds.FIELDS | {"name"}


def test_a_character_animates_and_a_banner_does_not() -> None:
    """The profile is what a consumer reads instead of branching on the name."""
    assert kinds.BUILT_INS["character"].animates is True
    assert kinds.BUILT_INS["banner"].animates is False


# R1.3, R1.4, R2.3 — declared over built-in, field by field, with provenance.


def test_a_declared_kind_overrides_only_the_fields_it_states(tmp_path: Path) -> None:
    space = workspace_with(tmp_path, {"character": {"cell": "96x96"}})
    resolved = kinds.resolve("character", space)

    assert resolved.profile.cell == (96, 96)
    assert resolved.profile.anchor == "feet", "the field it did not state is inherited"
    assert resolved.source["cell"] == kinds.DECLARED
    assert resolved.source["anchor"] == kinds.BUILT_IN


def test_a_kind_of_its_own_needs_no_built_in(tmp_path: Path) -> None:
    space = workspace_with(tmp_path, {"portrait": {"cell": "128x160", "anchor": "centre"}})
    resolved = kinds.resolve("portrait", space)

    assert resolved.profile.cell == (128, 160)
    assert resolved.source["cell"] == kinds.DECLARED
    assert resolved.source["template"] == "default"


def test_outside_a_workspace_the_built_ins_are_still_there() -> None:
    """`snap` and `pixelart` run against loose PNGs, and may still speak of kinds."""
    assert set(kinds.every(None)) == set(kinds.BUILT_INS)


# R1.5 — a declaration that is not one.


def test_a_field_that_is_not_a_field_is_refused(tmp_path: Path) -> None:
    space = workspace_with(tmp_path, {"icon": {"colour": "red"}})
    with pytest.raises(SscError) as refused:
        kinds.resolve("icon", space)
    assert refused.value.code == "invalid-kind"
    assert "colour" in refused.value.message


@pytest.mark.parametrize(
    "declared",
    [
        {"icon": {"cell": "not-a-size"}},
        {"icon": {"animates": "yes"}},
        {"icon": {"checks": "palette"}},
    ],
)
def test_a_value_the_field_cannot_take_is_refused(tmp_path: Path, declared: dict) -> None:
    space = workspace_with(tmp_path, declared)
    with pytest.raises(SscError) as refused:
        kinds.resolve("icon", space)
    assert refused.value.code == "invalid-kind"


def test_a_kinds_key_that_is_not_a_map_is_refused(tmp_path: Path) -> None:
    space = ws.create(tmp_path)
    space.config_path.write_text(yaml.safe_dump({"schema": 1, "kinds": ["icon"]}), encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"


# R2 — discovering them.


def test_kind_list_reports_built_in_and_declared(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    workspace_with(tmp_path, {"portrait": {"cell": "64x80"}})
    code, payload = run("kind", "list")

    assert code == 0
    assert payload["count"] == 7
    assert "portrait" in {entry["name"] for entry in payload["kinds"]}


def test_kind_show_reports_where_each_field_came_from(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    workspace_with(tmp_path, {"character": {"cell": "96x96"}})
    code, payload = run("kind", "show", "character")

    assert code == 0
    assert payload["cell"] == {"width": 96, "height": 96}
    assert payload["source"]["cell"] == kinds.DECLARED
    assert payload["source"]["anchor"] == kinds.BUILT_IN


def test_an_unknown_kind_names_the_kinds_there_are(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    ws.create(tmp_path)
    code, payload = run("kind", "show", "sprite")

    assert code == 2
    assert payload["error"]["code"] == "unknown-kind"
    assert "character" in payload["error"]["message"]


def test_a_kind_that_is_not_a_name_stays_an_invalid_name(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Both refuse, and a caller reading the code should be told which went wrong —
    `workspace-foundation`'s own escape tests assert the first one."""
    monkeypatch.chdir(tmp_path)
    ws.create(tmp_path)
    code, payload = run("kind", "show", "../../escaped")
    assert code == 2
    assert payload["error"]["code"] == "invalid-name"


# R3.2 — asset new only accepts a kind that resolves.


def test_asset_new_refuses_a_kind_that_resolves_to_nothing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    ws.create(tmp_path)
    code, payload = run("asset", "new", "hero", "--kind", "sprite")

    assert code == 2
    assert payload["error"]["code"] == "unknown-kind"
    assert not (tmp_path / "assets/sprite").exists()


def test_asset_new_accepts_a_kind_a_project_declared(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    workspace_with(tmp_path, {"portrait": {"cell": "64x80"}})
    code, _ = run("asset", "new", "queen", "--kind", "portrait")

    assert code == 0
    assert (tmp_path / "assets/portrait/queen/meta.json").is_file()


def test_nothing_in_the_codebase_branches_on_a_kinds_name() -> None:
    """The defect `adr:0008` exists to prevent, as a grep rather than a type — every
    consumer reads a profile, so a comparison against a kind's name is the smell."""
    import re

    source = Path(__file__).resolve().parents[2] / "src"
    offending = [
        f"{path.relative_to(source)}:{number}"
        for path in source.rglob("*.py")
        if path.name != "kinds.py"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r'kind\s*==\s*["\']', line)
    ]
    assert offending == []
