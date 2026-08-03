"""What a kind means — specs/asset-kinds R1, R2, R3."""

from __future__ import annotations

import json
import re
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


#: The shapes `adr:0008`'s consequence actually forbids. The first version of this matched
#: only a literal `kind == "..."`, which is narrower than the claim it enforces: a
#: `kind.startswith(...)`, a `match kind:`, a membership test against literals or the
#: reversed comparison would all have sailed through — and the five M2 leaves that consume a
#: profile are exactly where one of those would appear.
BRANCHES_ON_A_NAME = re.compile(
    r"""kind\w*\s*(?:==|!=)\s*["']
      | ["']\w+["']\s*(?:==|!=)\s*kind\b
      | kind\w*\s*\.startswith\(
      | kind\w*\s+(?:not\s+)?in\s*[\[{(]\s*["']
      | match\s+\w*kind\w*\s*:
    """,
    re.VERBOSE,
)


def test_nothing_in_the_codebase_branches_on_a_kinds_name() -> None:
    """The defect `adr:0008` exists to prevent, as a grep rather than a type — every
    consumer reads a profile, so a comparison against a kind's name is the smell."""
    source = Path(__file__).resolve().parents[2] / "src"
    offending = [
        f"{path.relative_to(source)}:{number}"
        for path in source.rglob("*.py")
        if path.name != "kinds.py"
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if BRANCHES_ON_A_NAME.search(line)
    ]
    assert offending == []


@pytest.mark.parametrize(
    "line",
    [
        'if kind == "character":',
        'if asset.kind != "tile":',
        'if "character" == kind:',
        'if kind.startswith("char"):',
        'if kind in {"character", "icon"}:',
        "match kind:",
    ],
)
def test_the_grep_catches_each_shape_it_claims_to(line: str) -> None:
    """A check nobody has verified is a check nobody should rely on — and this one is the
    sole enforcement of R3.1 in the whole codebase."""
    assert BRANCHES_ON_A_NAME.search(line)


@pytest.mark.parametrize(
    "line", ["profile = resolve(kind, workspace)", "available = kinds.every(workspace)"]
)
def test_the_grep_does_not_flag_reading_a_profile(line: str) -> None:
    assert not BRANCHES_ON_A_NAME.search(line)


# The security review's two: `ssc.yaml` is the first attacker-influenced structured input.


@pytest.mark.parametrize("document", ["- a\n- b\n", "just a string\n"])
def test_a_config_that_is_not_a_map_is_refused(tmp_path: Path, document: str) -> None:
    """`document.get` on a list is an AttributeError, and `cli/main.py` catches only
    SscError — so it left the command as a traceback rather than as JSON."""
    space = ws.create(tmp_path)
    space.config_path.write_text(document, encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"


@pytest.mark.parametrize("value", ["5", "true", "[1, 2]", "0", "false", '""', "[]"])
def test_a_kind_declared_as_something_other_than_a_map_is_refused(
    tmp_path: Path, value: str
) -> None:
    """The falsy cases are the ones the first version missed: `every` reached `merge` with
    `.get(name) or {}`, so `character: 0` became an empty declaration and resolved silently
    to the built-in defaults instead of being refused."""
    space = ws.create(tmp_path)
    space.config_path.write_text(f"schema: 1\nkinds:\n  character: {value}\n", encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-kind"
    assert "character" in refused.value.message


def test_an_anchor_that_is_not_one_is_refused_here_and_not_three_commands_later(
    tmp_path: Path,
) -> None:
    """The promise validate-on-read makes: `anchor: cetnre` would otherwise be coerced to a
    string and fall through to centre behaviour in whichever leaf reads it."""
    space = workspace_with(tmp_path, {"icon": {"anchor": "cetnre"}})
    with pytest.raises(SscError) as refused:
        kinds.resolve("icon", space)
    assert refused.value.code == "invalid-kind"
    assert "feet" in refused.value.message


@pytest.mark.parametrize("value", [{"x": 1}, None, True, [{"a": 1}]])
def test_a_name_field_that_is_not_a_name_is_refused(tmp_path: Path, value: Any) -> None:
    """Coercing with `str()` accepted every one of these silently."""
    space = workspace_with(tmp_path, {"icon": {"template": value}})
    with pytest.raises(SscError) as refused:
        kinds.resolve("icon", space)
    assert refused.value.code == "invalid-kind"


def test_anchors_and_aliases_are_refused(tmp_path: Path) -> None:
    """`safe_load` blocks arbitrary object construction but does not bound alias expansion:
    six levels of `&a: [*b x 50]` is a kilobyte on disk and hangs every kind-aware command
    in the workspace. A config file has no legitimate use for an anchor."""
    bomb = "schema: 1\nkinds:\n  a: &x {cell: 8x8}\n  b: *x\n"
    space = ws.create(tmp_path)
    space.config_path.write_text(bomb, encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"
    assert "anchors" in refused.value.message


def test_a_config_past_the_size_ceiling_is_refused_before_it_is_parsed(tmp_path: Path) -> None:
    space = ws.create(tmp_path)
    space.config_path.write_text("schema: 1\n# " + "x" * kinds.MAX_CONFIG_BYTES, encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"
    assert "ceiling" in refused.value.message


def test_a_deeply_nested_document_is_a_refusal_not_a_stack_overflow(tmp_path: Path) -> None:
    """PyYAML's own scanner raises RecursionError, which is not a YAMLError and escaped."""
    space = ws.create(tmp_path)
    space.config_path.write_text("kinds: " + "[" * 20_000 + "]" * 20_000, encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"


# The re-review's three, all one class: an exception that is not an SscError.


@pytest.mark.parametrize("document", ["schema: 1\nkinds:\n  123: {}\n", "kinds:\n  true: {}\n"])
def test_a_kind_named_by_a_non_string_key_is_refused(tmp_path: Path, document: str) -> None:
    """YAML keys are not necessarily strings, and a non-string one blew up at `sorted(...)`
    before `check_name` ever saw it."""
    space = ws.create(tmp_path)
    space.config_path.write_text(document, encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"


def test_a_field_named_by_a_non_string_key_is_refused(tmp_path: Path) -> None:
    space = ws.create(tmp_path)
    space.config_path.write_text("kinds:\n  icon:\n    5: value\n", encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-kind"


def test_bytes_that_are_not_utf8_are_a_refusal(tmp_path: Path) -> None:
    """`UnicodeDecodeError` is a ValueError, not a YAMLError, so it escaped the tuple."""
    space = ws.create(tmp_path)
    space.config_path.write_bytes(b'schema: 1\nkinds:\n  a: {template: "\xff\xfe"}\n')
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"


@pytest.mark.parametrize("value", ["0", '""', "[]", "false"])
def test_a_falsy_kinds_value_of_the_wrong_type_is_refused(tmp_path: Path, value: str) -> None:
    """`or {}` short-circuited before the type check, so a file that plainly declares
    something reported 'no kinds declared'."""
    space = ws.create(tmp_path)
    space.config_path.write_text(f"schema: 1\nkinds: {value}\n", encoding="utf-8")
    with pytest.raises(SscError) as refused:
        kinds.every(space)
    assert refused.value.code == "invalid-config"


def test_the_anchors_a_profile_may_name_are_the_ones_assemble_implements() -> None:
    """A value that must match between places, from one place. It was four copies."""
    from ssc.core.assemble import ANCHOR_MODES

    assert kinds.ANCHORS is ANCHOR_MODES
