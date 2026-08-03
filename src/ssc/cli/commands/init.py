"""`ssc init` — lay out a workspace here (R1.2, R1.3)."""

from __future__ import annotations

from pathlib import Path

from ssc.cli import workspace as ws
from ssc.cli.errors import UsageError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@ssc_command("init", help="Create a workspace in the current directory.")
def init(*, dry_run: bool) -> Result:
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

    paths = {
        "root": str(directory),
        "config": str(marker),
        "assets": str(directory / "assets"),
        "cache": str(directory / "cache"),
    }
    if dry_run:
        return Result("init", f"would create a workspace in {directory}", paths, dry_run=True)

    ws.create(directory)
    return Result("init", f"workspace created in {directory}", paths)
