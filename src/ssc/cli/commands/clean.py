"""`ssc clean` — delete what can be recomputed, and only that (R6).

`derived` is defined by being reproducible: a deterministic command computed it from a
source with recorded parameters, so deleting it costs a rerun. `source` is what a model
produced — it cost money, the model is not deterministic, and nothing regenerates it. That
asymmetry is the whole of this command, and it reads one field to honour it.
"""

from __future__ import annotations

import shutil

from ssc.cli import meta
from ssc.cli.listing import asset_dirs, inside
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace

__all__ = ["clean", "inside"]


@ssc_command(
    "clean",
    help="Delete derived files. Sources and outputs are never touched.",
    needs_workspace=True,
)
def clean(*, dry_run: bool, workspace: Workspace) -> Result:
    deleted: list[str] = []

    for directory in asset_dirs(workspace):
        record = meta.load(directory)
        removable = [entry for entry in record.files if entry.file_class == "derived"]
        if not removable:
            continue

        for entry in removable:
            target = inside(directory, entry.path)
            deleted.append(f"{record.kind}/{record.key}/{entry.path}")
            if dry_run:
                continue
            # A record whose file already went by hand is still a record to drop: leaving
            # it would let `--stage snap` resolve to a path that is not there.
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)

        if not dry_run:
            record.files = [entry for entry in record.files if entry.file_class != "derived"]
            meta.save(directory, record)

    summary = (
        f"{len(deleted)} derived file{'' if len(deleted) == 1 else 's'}"
        f"{' would be deleted' if dry_run else ' deleted'}"
    )
    return Result("clean", summary, {"deleted": deleted}, dry_run=dry_run)
