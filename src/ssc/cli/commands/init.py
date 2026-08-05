"""`ssc init` — lay out a workspace here (R1.2, R1.3), with the harness skills in it."""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli import skills as skills_data
from ssc.cli import workspace as ws
from ssc.cli.errors import UsageError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@ssc_command("init", help="Create a workspace in the current directory.")
@click.option(
    "--no-skills",
    "with_skills",
    flag_value=False,
    default=True,
    help="Skip the sprite-* skills; the workspace is laid out without them.",
)
def init(with_skills: bool, *, dry_run: bool) -> Result:
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
        if with_skills:
            paths["skills"] = list(skills_data.install(directory, dry_run=True).written)
        return Result("init", f"would create a workspace in {directory}", paths, dry_run=True)

    ws.create(directory)
    summary = f"workspace created in {directory}"
    if with_skills:
        # The skills are how an agent drives this workspace, so they are laid out with it
        # rather than fetched later — see `ssc.cli.skills`.
        installed = skills_data.install(directory)
        paths["skills"] = list(installed.written)
        paths["skills_kept"] = list(installed.kept)
        summary = f"{summary}, with {len(installed.written)} skills in {skills_data.SKILLS_DIR}"
    return Result("init", summary, paths)
