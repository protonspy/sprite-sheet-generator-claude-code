"""`ssc clean` — delete what can be recomputed, and only that (R6).

`derived` is defined by being reproducible: a deterministic command computed it from a
source with recorded parameters, so deleting it costs a rerun. `source` is what a model
produced — it cost money, the model is not deterministic, and nothing regenerates it. That
asymmetry is the whole of this command, and it reads one field to honour it.
"""

from __future__ import annotations

from ssc.cli import meta
from ssc.cli.listing import asset_dirs, bound, inside
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

        if dry_run:
            deleted += [f"{record.kind}/{record.key}/{entry.path}" for entry in removable]
            continue

        # Held for the whole asset (R3.7). `asset_dirs` checked this directory when it
        # scanned, and the scan is one loop iteration per asset ago — so both the deletes
        # and the record that follows them go through the directory rather than through
        # that path a second time. The deletes especially: this is the only command in
        # `ssc` that removes anything, and one of the things it removes is `frames/`, a
        # directory. A path re-resolved through a link turns that into `shutil.rmtree`
        # somewhere nobody asked for, which is a worse outcome than any write.
        with bound(workspace, directory) as held:
            for entry in removable:
                # Still checked as a string against the record, which is where a
                # hand-edited `meta.json` is caught; `delete` is what refuses to *cross* a
                # link, which a resolved path cannot promise once the root can move.
                inside(held.path, entry.path)
                deleted.append(f"{record.kind}/{record.key}/{entry.path}")
                # A record whose file already went by hand is still a record to drop:
                # leaving it would let `--stage snap` resolve to a path that is not there.
                held.delete(entry.path)

            record.files = [entry for entry in record.files if entry.file_class != "derived"]
            meta.save(held, record)

    summary = (
        f"{len(deleted)} derived file{'' if len(deleted) == 1 else 's'}"
        f"{' would be deleted' if dry_run else ' deleted'}"
    )
    return Result("clean", summary, {"deleted": deleted}, dry_run=dry_run)
