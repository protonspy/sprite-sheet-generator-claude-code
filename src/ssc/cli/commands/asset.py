"""`ssc asset new` — create an asset directory and its record (R2.2, R2.3)."""

from __future__ import annotations

import click

from ssc.cli import kinds, meta
from ssc.cli.errors import UsageError
from ssc.cli.listing import bound, placed
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace


@click.group("asset", help="Create and inspect assets.")
def asset() -> None:
    """Grouped under a noun because `ssc asset new` reads as what it does, and because
    later leaves add verbs here rather than at the top level."""


@ssc_command("new", help="Create an asset of the given kind.", needs_workspace=True)
@click.option("--kind", required=True, help="The asset's kind, e.g. character, tile, icon.")
@click.argument("key")
def asset_new(key: str, kind: str, *, dry_run: bool, workspace: Workspace) -> Result:
    # The kind has to resolve to a profile (R3.2). A typo here would otherwise create an
    # asset of a kind nothing knows anything about, and surface commands later as a cell
    # size nobody chose.
    kinds.resolve(kind, workspace)
    # `asset_dir` validates the two names as strings; it cannot see that `assets/<kind>/`
    # is a link pointing somewhere else on disk. This is a route that *creates* an asset,
    # so without the check a linked kind directory makes `mkdir` and `meta.json` land
    # outside the workspace — and every later command then reads an asset the workspace
    # does not own.
    directory = placed(workspace, workspace.asset_dir(kind, key))

    # Uniqueness is per kind, not global — see adr:0007-group-assets-by-kind-then-key for
    # why two kinds are allowed to share a key.
    if meta.path_of(directory).exists():
        raise UsageError(
            "asset-exists",
            f"{kind}/{key} already exists at {directory}",
            fix="choose another key, or work with the one that is there",
        )

    data = {"key": key, "kind": kind, "path": str(directory)}
    if dry_run:
        return Result("asset new", f"would create {kind}/{key}", data, dry_run=True)

    directory.mkdir(parents=True, exist_ok=True)
    # Held and checked again, now that the path exists. The first check ran against a
    # `<kind>/` that may not have existed yet, and `resolve()` reads a missing component
    # literally — so a link planted between the check and `mkdir` would have been invisible
    # to it and followed by `mkdir(parents=True)`. `bound` re-checks *and* keeps the
    # directory it checked, which is what the write below goes through: re-checking alone
    # left the swap open for the statements between the check and the write.
    with bound(workspace, directory) as held:
        meta.save(held, meta.AssetMeta(key=key, kind=kind))
    return Result("asset new", f"created {kind}/{key}", data)


asset.add_command(asset_new)
