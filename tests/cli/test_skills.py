"""The skills a workspace gets from `ssc init` — plan task 4.3."""

from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from ssc.cli import kinds, skills
from ssc.cli.app import main

RELAY = (
    "sprite-background",
    "sprite-boxart",
    "sprite-icons",
    "sprite-sheet",
    "sprite-still",
    "sprite-tilemap",
    "sprite-ui",
)


def description(skill: skills.Skill) -> str:
    """The `description:` line of a skill's frontmatter.

    One line however long it runs, because that is what the harness reads to decide
    whether the skill applies at all.
    """
    for line in skill.text.splitlines():
        if line.startswith("description:"):
            return line
    raise AssertionError(f"{skill.name} carries no description")


def claims(kind: str, text: str) -> bool:
    """Whether a description claims to drive `kind`.

    Two forms, and only two: the kind backticked, or `--kind <name>`. Prose does not
    count — `sprite-icons` says "background removal" in its own description, and a
    whole-word match would read that as a claim to drive the `background` kind.
    """
    return bool(re.search(rf"`{re.escape(kind)}`|--kind {re.escape(kind)}\b", text))


def test_the_relay_skills_ship_in_the_package() -> None:
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
    mine = tmp_path / ".claude" / "skills" / "sprite-ui"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("mine", encoding="utf-8")

    installed = skills.install(tmp_path)

    assert (mine / "SKILL.md").read_text(encoding="utf-8") == "mine"
    assert ".claude/skills/sprite-ui/SKILL.md" in installed.kept
    assert ".claude/skills/sprite-ui/SKILL.md" not in installed.written


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
    assert (tmp_path / ".claude" / "skills" / "sprite-sheet" / "SKILL.md").is_file()


def test_init_lays_out_a_skill_the_payload_gained(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """R1.5 — a skill is data. The three added for the kinds nothing drove reach a
    workspace through the installer that was already there, unchanged."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init", "--json"], catch_exceptions=False)

    for name in ("sprite-background", "sprite-still", "sprite-boxart"):
        assert (tmp_path / ".claude" / "skills" / name / "SKILL.md").is_file(), name


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


def test_every_built_in_kind_is_driven_by_a_skill() -> None:
    """R1.1, R1.2, R1.4 — a kind the payload declares and no skill claims is a run an
    agent composes from scratch every time it is asked for one."""
    shipped = skills.shipped()

    unclaimed = sorted(
        kind
        for kind in kinds.BUILT_INS
        if not any(claims(kind, description(skill)) for skill in shipped)
    )

    assert not unclaimed, f"no shipped skill drives {unclaimed}"


def test_the_coverage_check_reads_the_descriptions_it_thinks_it_reads() -> None:
    """The floor under the test above. A `claims` that matched nothing would report
    every kind covered by an empty payload and never fail again."""
    by_name = {skill.name: skill for skill in skills.shipped()}

    assert len(kinds.BUILT_INS) >= 8
    assert claims("icon", description(by_name["sprite-icons"]))
    assert not claims("background", "description: strips the background from a frame")
