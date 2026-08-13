"""The agent harness `ssc init` lays out - the payload, the installer, the command.

Covers agent-harness R1.1-R3.5 and R4.1-R4.2: the payload ships inside the package,
`harness.install` writes it without overwriting, the sprite relay lands where the
selected agent reads it, and `ssc init --codex` / `--opencode` choose the target.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ssc.cli import harness
from ssc.cli import skills as skill_payload
from ssc.cli.app import main

RELAY = tuple(skill.name for skill in skill_payload.shipped())

DOC = {
    "claude": ("CLAUDE.md", ".claude", ".claude/skills"),
    "codex": ("AGENTS.md", ".codex", ".codex/skills"),
    "opencode": ("AGENTS.md", ".opencode", ".opencode/skills"),
}


def test_the_three_targets_are_exactly_the_three() -> None:
    assert [one.name for one in harness.TARGETS] == ["claude", "codex", "opencode"]


def test_the_payload_ships_a_root_instruction_file_for_each_agent() -> None:
    for name, (instruction, _, _) in DOC.items():
        t = harness.target(name)
        assert t.instruction_file == instruction
        assert len(harness.instruction_text(t)) > 0
        assert b"## Driving `ssc`" in harness.instruction_text(t)


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
