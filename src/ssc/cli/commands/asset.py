"""`ssc asset new` — create an asset directory and its record (R2.2, R2.3)."""

from __future__ import annotations

import click

from ssc.cli import meta
from ssc.cli.errors import UsageError
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
    directory = workspace.asset_dir(kind, key)

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
    meta.save(directory, meta.AssetMeta(key=key, kind=kind))
    return Result("asset new", f"created {kind}/{key}", data)


asset.add_command(asset_new)
