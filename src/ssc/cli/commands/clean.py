"""`ssc clean` — delete what can be recomputed, and only that (R6).

`derived` is defined by being reproducible: a deterministic command computed it from a
source with recorded parameters, so deleting it costs a rerun. `source` is what a model
produced — it cost money, the model is not deterministic, and nothing regenerates it. That
asymmetry is the whole of this command, and it reads one field to honour it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ssc.cli import meta
from ssc.cli.errors import SscError
from ssc.cli.listing import asset_dirs
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace


def inside(directory: Path, relative: str) -> Path:
    """Resolve `relative` against `directory` and refuse anything that leaves it.

    `meta.py` already rejects an escaping path when the record is built or loaded. This
    is the second check, at the moment of deleting, because one validation gap is all
    that would otherwise stand between a bad record and `shutil.rmtree` on somebody's
    home directory — and a symlink can move the target after validation.
    """
    target = (directory / relative).resolve()
    root = directory.resolve()
    if target != root and root not in target.parents:
        raise SscError(
            "path-escapes-asset",
            f"{relative!r} resolves to {target}, which is outside {root}",
            fix=f"remove that record from {meta.META_NAME}",
        )
    if target == root:
        raise SscError(
            "path-escapes-asset",
            f"{relative!r} is the asset directory itself, which clean never deletes",
            fix=f"remove that record from {meta.META_NAME}",
        )
    return target


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
