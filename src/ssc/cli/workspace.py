"""Finding the workspace, and the paths inside it.

A workspace is a directory holding `ssc.yaml` (R1.1). Commands that touch assets need one;
commands that take `--in` and `--out` deliberately do not (R1.6), because `snap` and
`pixelart` have to be usable against a directory of loose PNGs by somebody who has never
run `ssc init`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ssc.cli.atomic import write_new
from ssc.cli.errors import UsageError
from ssc.cli.names import check_name

MARKER = "ssc.yaml"
SCHEMA = 1


@dataclass(frozen=True)
class Workspace:
    """A located workspace. Every path a command needs hangs off `root`."""

    root: Path

    @property
    def config_path(self) -> Path:
        return self.root / MARKER

    @property
    def assets(self) -> Path:
        return self.root / "assets"

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def jobs(self) -> Path:
        """Local operational state, git-ignored, and `ssc clean` does not touch it: its rule
        is that it deletes `derived` files, and a job record is neither derived nor an
        asset. See adr:0005-a-job-always-exists."""
        return self.root / "jobs"

    def asset_dir(self, kind: str, key: str) -> Path:
        """`assets/<kind>/<key>/` — kind first. See adr:0007-group-assets-by-kind-then-key.

        Both arguments are validated here rather than at each call site, because this is
        the one place they become a path. `assets / "../.." / key` escapes the workspace,
        and `assets / "C:/Windows"` discards `assets` entirely.
        """
        return self.assets / check_name(kind, "kind") / check_name(key, "key")


def find(start: Path | None = None) -> Workspace | None:
    """Search `start` and its ancestors for the marker. `None` if there is none."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if (directory / MARKER).is_file():
            return Workspace(root=directory)
    return None


def require(start: Path | None = None) -> Workspace:
    """The same search, but a command that needs a workspace and has none is a usage
    error carrying the command that creates one (R1.5)."""
    workspace = find(start)
    if workspace is None:
        raise UsageError(
            "no-workspace",
            f"no {MARKER} in this directory or any parent",
            fix="ssc init",
        )
    return workspace


def create(directory: Path) -> Workspace:
    """Lay out a new workspace (R1.2), refusing where one already exists (R1.3).

    `ssc.yaml` is almost empty on purpose: kind profiles, budget and palette are later
    leaves, and inventing their keys now would be inventing their design.
    """
    directory = directory.resolve()
    if (directory / MARKER).exists():
        raise UsageError(
            "workspace-exists",
            f"{directory / MARKER} already exists",
            fix="use it, or run ssc init somewhere else",
        )
    workspace = Workspace(root=directory)
    write_new(workspace.config_path, yaml.safe_dump({"schema": SCHEMA}, sort_keys=True).encode())
    workspace.assets.mkdir(parents=True, exist_ok=True)
    workspace.cache.mkdir(parents=True, exist_ok=True)
    workspace.jobs.mkdir(parents=True, exist_ok=True)
    return workspace
