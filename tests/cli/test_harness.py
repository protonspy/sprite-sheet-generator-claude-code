"""The agent harness `ssc init` lays out - the payload, the installer, the command.

Covers agent-harness R1.1-R3.5 and R4.1-R4.2: the payload ships inside the package,
`harness.install` writes it without overwriting, the sprite relay lands where the
selected agent reads it, and `ssc init --codex` / `--opencode` choose the target.

It also holds the three instruction texts to the CLI they describe. That is not what
agent-harness asked for - the leaf puts the harness contents out of scope - but the doc
is what an agent acts on before it has run anything, and it had drifted: a `doctor`
invocation that does not parse, two checks the map never named, three fixes the code
never emits. `plans/harness-accuracy.md` is where that was corrected, and these are the
tests that stop it happening twice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ssc.cli import harness, kinds, models
from ssc.cli import skills as skill_payload
from ssc.cli.app import main
from ssc.core.doctor import Check

RELAY = tuple(skill.name for skill in skill_payload.shipped())

DOC = {
    "claude": ("CLAUDE.md", ".claude", ".claude/skills"),
    "codex": ("AGENTS.md", ".codex", ".codex/skills"),
    "opencode": ("AGENTS.md", ".opencode", ".opencode/skills"),
}

TARGET_NAMES = tuple(one.name for one in harness.TARGETS)


def doc(name: str) -> str:
    return harness.instruction_text(harness.target(name)).decode("utf-8")


def test_the_three_targets_are_exactly_the_three() -> None:
    assert [one.name for one in harness.TARGETS] == ["claude", "codex", "opencode"]


def test_the_payload_ships_a_root_instruction_file_for_each_agent() -> None:
    for name, (instruction, _, _) in DOC.items():
        t = harness.target(name)
        assert t.instruction_file == instruction
        assert len(harness.instruction_text(t)) > 0
        assert b"## Driving `ssc`" in harness.instruction_text(t)


def test_the_three_docs_differ_only_in_their_title_and_their_skills_path() -> None:
    """One text, three headers. The drift this catches already happened once: a rename
    swept through the two `AGENTS.md` copies and left "a work goes from nothing to
    dist/index.json" and a sentence with its verb gone, neither of which the Claude copy
    had. Every other line is the same fact, so every other line is compared."""
    claude = doc("claude").splitlines()
    for agent in ("codex", "opencode"):
        other = doc(agent).splitlines()
        assert len(other) == len(claude), f"{agent}: the docs are not the same length"
        differing = [n for n, (a, b) in enumerate(zip(claude, other, strict=True)) if a != b]
        assert len(differing) == 2, f"{agent}: {len(differing)} lines differ, expected 2"
        title, skills = differing
        assert title == 0
        assert other[title] == "# AGENTS.md"
        assert other[skills] == f"## Skills — `.{agent}/skills/`"


@pytest.mark.parametrize("agent", TARGET_NAMES)
def test_the_doc_names_every_check_doctor_ships(agent: str) -> None:
    """A check absent from the defect map is one the agent reads as clean.

    `consistency` and `scale` were both missing, and both are always on - so a run that
    measured them saw a status the doc could not explain and a fix it never named.
    """
    text = doc(agent)
    missing = sorted(str(check) for check in Check if f"`{check}`" not in text)
    assert not missing, f"{agent}: the defect map does not name {', '.join(missing)}"


@pytest.mark.parametrize("agent", TARGET_NAMES)
def test_the_doc_names_every_built_in_kind(agent: str) -> None:
    text = doc(agent)
    missing = sorted(name for name in kinds.BUILT_INS if f"`{name}`" not in text)
    assert not missing, f"{agent}: the kind list does not name {', '.join(missing)}"


@pytest.mark.parametrize("agent", TARGET_NAMES)
def test_the_doc_names_the_default_model_for_each_medium(agent: str) -> None:
    """The endpoint verbatim, not the family - the doc is what gets typed at `--model`."""
    text = doc(agent)
    registry = models.load(fetch=lambda _: None)
    for media, endpoint in sorted(registry.defaults.items()):
        assert f"`{endpoint}`" in text, f"{agent}: no {media} default named"


@pytest.mark.parametrize("agent", TARGET_NAMES)
def test_the_doc_points_at_ssc_kind_list_rather_than_a_closed_set(agent: str) -> None:
    """A kind is a profile, not an enum - `adr:0008`. A doc that lists the built-ins and
    stops there tells a project its own kinds do not exist."""
    assert "ssc kind list" in doc(agent)


@pytest.mark.parametrize("agent", TARGET_NAMES)
def test_the_doc_names_the_commands_its_own_exit_codes_and_flags_imply(agent: str) -> None:
    """Exit `3` is a gate pending and `--no-wait` strands a job, so a doc that states one
    and never names the command that clears it leaves the agent with nowhere to go."""
    text = doc(agent)
    for command in ("ssc gate", "ssc run", "ssc status", "ssc job"):
        assert command in text, f"{agent}: {command} is never named"


@pytest.mark.parametrize("agent", TARGET_NAMES)
def test_the_doc_never_sends_the_agent_at_a_doctor_invocation_that_does_not_parse(
    agent: str,
) -> None:
    """`tool doctor` has no positional argument: it reads `--in`, and `--kind` is how a
    harness asks for the checks a profile declares."""
    text = doc(agent)
    assert "ssc tool doctor <asset>" not in text
    assert "tool doctor --in" in text


def test_install_writes_the_doc_and_the_relay_where_the_agent_reads(tmp_path: Path) -> None:
    """Default is Claude; the skills land in `.claude/skills/` today and must keep
    landing there, or projects that edited the relay would look like them never did."""
    laid = harness.install(tmp_path, "claude")
    assert laid.agent == "claude"
    assert (tmp_path / "CLAUDE.md").is_file()
    assert any(path.startswith(".claude/skills/") for path in laid.written)
    for name in RELAY:
        assert (tmp_path / ".claude" / "skills" / name / "SKILL.md").is_file()


def test_install_keeps_files_that_are_already_there(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("mine", encoding="utf-8")

    laid = harness.install(tmp_path, "claude")

    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == "mine"
    assert "CLAUDE.md" in laid.kept
    assert "CLAUDE.md" not in laid.written


def test_init_defaults_to_the_claude_harness(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["agent"] == "claude"
    assert (tmp_path / "CLAUDE.md").is_file()
    assert not (tmp_path / "AGENTS.md").exists()
    assert (tmp_path / ".claude" / "skills" / "sprite-sheet" / "SKILL.md").is_file()


def test_init_codex_lays_out_the_codex_harness(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--codex", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["agent"] == "codex"
    assert (tmp_path / "AGENTS.md").is_file()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".codex" / "skills" / "sprite-icons" / "SKILL.md").is_file()


def test_init_opencode_lays_out_the_opencode_harness(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--opencode", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["agent"] == "opencode"
    assert (tmp_path / "AGENTS.md").is_file()
    assert not (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".opencode" / "skills" / "sprite-tilemap" / "SKILL.md").is_file()


def test_init_with_both_agent_flags_is_a_usage_error_that_writes_nothing(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """R1.4 — the target is an exclusive choice, and the refusal precedes the write."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        main, ["init", "--codex", "--opencode", "--json"], catch_exceptions=False
    )

    assert result.exit_code == 2
    assert json.loads(result.output)["error"]["code"] == "agent-conflict"
    assert list(tmp_path.iterdir()) == []


def test_init_dry_run_writes_nothing_and_reports_the_agent(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R4.2 — a dry run names what the selected agent would have written."""
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        main, ["init", "--opencode", "--dry-run", "--json"], catch_exceptions=False
    )
    payload = json.loads(result.output)

    assert payload["dry_run"] is True
    assert payload["agent"] == "opencode"
    assert len(payload["written"]) == len(RELAY) + 1
    assert list(tmp_path.iterdir()) == []
