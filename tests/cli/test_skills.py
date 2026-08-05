"""The skills a workspace gets from `ssc init` — plan task 4.3."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ssc.cli import skills
from ssc.cli.app import main

RELAY = (
    "sprite-animation",
    "sprite-character",
    "sprite-cleanup",
    "sprite-integrate",
    "sprite-resource",
    "sprite-style",
)


def test_the_six_relay_skills_ship_in_the_package() -> None:
    """They are a template `ssc` installs, so they travel inside it."""
    assert tuple(skill.name for skill in skills.shipped()) == RELAY


def test_every_shipped_skill_carries_its_frontmatter() -> None:
    """A SKILL.md with no `name:` is a file the harness will not load."""
    for skill in skills.shipped():
        assert skill.text.startswith("---\n")
        assert f"name: {skill.name}\n" in skill.text


def test_install_writes_each_skill_where_the_harness_reads_it(tmp_path: Path) -> None:
    installed = skills.install(tmp_path)
    assert len(installed.written) == len(RELAY)
    assert installed.kept == ()
    for name in RELAY:
        written = tmp_path / ".claude" / "skills" / name / "SKILL.md"
        assert written.is_file()
        assert f"name: {name}\n" in written.read_text(encoding="utf-8")


def test_install_keeps_a_skill_that_is_already_there(tmp_path: Path) -> None:
    """A project may have edited the relay; an install that reverted it silently is worse
    than one that reports doing nothing."""
    mine = tmp_path / ".claude" / "skills" / "sprite-style"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("mine", encoding="utf-8")

    installed = skills.install(tmp_path)

    assert (mine / "SKILL.md").read_text(encoding="utf-8") == "mine"
    assert ".claude/skills/sprite-style/SKILL.md" in installed.kept
    assert ".claude/skills/sprite-style/SKILL.md" not in installed.written


def test_install_dry_run_writes_nothing(tmp_path: Path) -> None:
    installed = skills.install(tmp_path, dry_run=True)
    assert len(installed.written) == len(RELAY)
    assert not (tmp_path / ".claude").exists()


def test_init_lays_the_skills_out_with_the_workspace(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert len(payload["skills"]) == len(RELAY)
    assert payload["skills_kept"] == []
    assert (tmp_path / ".claude" / "skills" / "sprite-integrate" / "SKILL.md").is_file()


def test_init_no_skills_lays_out_only_the_workspace(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--no-skills", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert "skills" not in payload
    assert not (tmp_path / ".claude").exists()
    assert (tmp_path / "assets").is_dir()


def test_init_dry_run_names_the_skills_and_writes_none(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["init", "--dry-run", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert payload["dry_run"] is True
    assert len(payload["skills"]) == len(RELAY)
    assert list(tmp_path.iterdir()) == []
