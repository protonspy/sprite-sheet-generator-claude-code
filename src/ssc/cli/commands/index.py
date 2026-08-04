"""`ssc index` — turn a workspace into the `dist/` an engine loads.

The model is `cli/index.py` and the shapes are `cli/formats.py`. What is here is the command:
the flags, the writing, and the one report a caller reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from ssc.cli import formats
from ssc.cli import index as model
from ssc.cli.atomic import Directory
from ssc.cli.frames import encode
from ssc.cli.main import ssc_command
from ssc.cli.names import check_relative_path
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace

INDEX_NAME = "index.json"


def rendered(payload: dict[str, Any]) -> bytes:
    """The index as bytes, in the one spelling that makes a second run identical (R1.8).

    `sort_keys` and a fixed indent, and no trailing state of any kind — no timestamp, no
    version of `ssc`, no path from the machine it ran on. A field like that is what turns a
    reproducible build into a diff on every run.
    """
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_into(root: Path, relative: str, data: bytes) -> Path:
    """Write one file under `root`, replacing what is there.

    `replace` rather than `write_new`: `dist/` is rebuilt, and a build that refuses because
    its own last output is still there would need a `clean` before every run. The path is
    checked for escape even though every one of them is composed from names `check_name`
    already accepted — the composition is the part that could go wrong later.
    """
    check_relative_path(relative, "a dist path")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with Directory.open(target.parent) as held:
        return held.replace(target.name, data)


def write_dist(
    workspace: Workspace, built: model.Built, payload: dict[str, Any], *, dry_run: bool
) -> list[str]:
    """Every image, then the index that names them (R1.6, R1.7, R1.9).

    The images first and the index last, so a run interrupted half way leaves an index that
    still describes the last complete build rather than one naming files nobody wrote.
    """
    written = [*sorted(built.images), INDEX_NAME]
    if dry_run:
        return written

    workspace.dist.mkdir(parents=True, exist_ok=True)
    for relative in sorted(built.images):
        write_into(workspace.dist, relative, encode(built.images[relative]))
    write_into(workspace.dist, INDEX_NAME, rendered(payload))
    return written


@ssc_command(
    "index",
    help="Build dist/ — the sheets, atlases and tilesets an engine loads.",
    needs_workspace=True,
)
@click.option("--extrude", type=int, default=0, help="Repeat each atlas entry's border outwards.")
@click.option(
    "--padding", type=int, default=0, help="Pixels between atlas entries and at the edge."
)
@click.option("--stage", default=None, help="Publish this stage. Defaults to the last recorded.")
@click.option(
    "--format",
    "name",
    default=formats.DEFAULT_FORMAT,
    help=f"One of: {', '.join(formats.FORMATS)}.",
)
def index(
    name: str,
    stage: str | None,
    padding: int,
    extrude: int,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """R1, R3, R5.

    The whole index does not travel in the result: it is on disk, it is the point of the
    command, and a caller that wants it reads the file. What comes back is what was written
    and what was left out, which is what a caller has to act on.
    """
    # Refused before any packing: a format nobody emits should cost a typo's worth of time,
    # not a whole build's (R5.6).
    formats.emit(model.Built(), name=name)

    groups, skipped = model.gather(workspace, stage=stage)
    built = model.build(groups, skipped, padding=padding, extrude=extrude)
    payload = formats.emit(built, name=name)
    written = write_dist(workspace, built, payload, dry_run=dry_run)

    covered = len(built.sheets) + len(built.atlases) + len(built.tilesets)
    return Result(
        "index",
        f"{covered} artefact{'' if covered == 1 else 's'} in {name}"
        + (f", {len(built.skipped)} asset skipped" if len(built.skipped) == 1 else "")
        + (f", {len(built.skipped)} assets skipped" if len(built.skipped) > 1 else ""),
        {
            "format": name,
            "sheets": [sheet.id for sheet in built.sheets],
            "atlases": [atlas.id for atlas in built.atlases],
            "tilesets": [tileset.id for tileset in built.tilesets],
            "skipped": [one.as_dict() for one in built.skipped],
            "written": written,
        },
        dry_run=dry_run,
    )
