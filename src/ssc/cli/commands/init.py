"""`ssc init` — lay out a workspace here (R1.2, R1.3), with the selected agent's harness."""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli import harness as harness_data
from ssc.cli import workspace as ws
from ssc.cli.errors import UsageError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@ssc_command("init", help="Create a workspace in the current directory.")
@click.option(
    "--codex",
    "want_codex",
    is_flag=True,
    default=False,
    help="Lay out the Codex harness (AGENTS.md, .codex/).",
)
@click.option(
    "--opencode",
    "want_opencode",
    is_flag=True,
    default=False,
    help="Lay out the OpenCode harness (AGENTS.md, .opencode/).",
)
@click.option(
    "--no-skills",
    "with_skills",
    flag_value=False,
    default=True,
    help="Skip the sprite-* skills; the workspace is laid out without them.",
)
def init(want_codex: bool, want_opencode: bool, with_skills: bool, *, dry_run: bool) -> Result:
    if want_codex and want_opencode:
        # R1.4 — an exclusive choice, refused before anything is written.
        raise UsageError(
            "agent-conflict",
            "--codex and --opencode are alternatives; pick one agent",
            fix="run ssc init again with --codex or --opencode, not both",
        )

    if want_codex:
        agent = "codex"
    elif want_opencode:
        agent = "opencode"
    else:
        agent = "claude"
    harness = harness_data.target(agent)

    directory = Path.cwd().resolve()
    marker = directory / ws.MARKER

    # Checked before the dry-run branch on purpose: "what would happen" and "what happens"
    # have to agree, and what happens here is a refusal.
    if marker.exists():
        raise UsageError(
            "workspace-exists",
            f"{marker} already exists",
            fix="use it, or run ssc init somewhere else",
        )

    paths: dict[str, object] = {
        "root": str(directory),
        "config": str(marker),
        "assets": str(directory / "assets"),
        "cache": str(directory / "cache"),
    }
    if dry_run:
        laid = harness_data.install(directory, agent, with_skills=with_skills, dry_run=True)
        paths["agent"] = agent
        paths["written"] = list(laid.written)
        paths["kept"] = list(laid.kept)
        if with_skills:
            paths["skills"] = list(laid.skills.written)
        return Result(
            "init",
            f"would create a workspace in {directory} for the {agent} harness",
            paths,
            dry_run=True,
        )

    ws.create(directory)
    laid = harness_data.install(directory, agent, with_skills=with_skills)
    paths["agent"] = agent
    paths["written"] = list(laid.written)
    paths["kept"] = list(laid.kept)

    summary = f"workspace created in {directory}, with the {agent} harness"
    if with_skills:
        paths["skills"] = list(laid.skills.written)
        paths["skills_kept"] = list(laid.skills.kept)
        summary = f"{summary} and {len(laid.skills.written)} skills in {harness.skills_dir}"
    return Result("init", summary, paths)
