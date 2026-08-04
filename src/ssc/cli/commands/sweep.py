"""`ssc tool sweep` — run one command across a range of its parameters and compare.

The command that produces the material a human decision is taken on. It measures every
variant and it ranks nothing: `specs/sweep-and-review/` R2.3 reports which variant had the
fewest defects as an arithmetic fact, and `ssc gate approve` is where somebody decides.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import click

from ssc.cli import steps, sweep
from ssc.cli import workspace as ws
from ssc.cli.atomic import write_new
from ssc.cli.commands.doctor import measure
from ssc.cli.errors import SscError, UsageError
from ssc.cli.frames import Frame, read_frames, write_frames, write_one
from ssc.cli.main import ssc_command
from ssc.cli.names import check_name
from ssc.cli.output import Result
from ssc.core.contact import ContactParams, cell_for, draw_labels, sheet

SCHEMA = 1

#: The report, and the name R4.3 checks for to decide a directory already holds a sweep.
REPORT_NAME = "sweep.json"
CONTACT_NAME = "contact.png"
VARIANTS_DIR = "variants"

#: `--columns` is a dial whose cost is its own value: it multiplies the contact sheet's
#: width, and the canvas is allocated before a single pixel is copied into it. Every other
#: number in this leaf is bounded — the variant ceiling, each registry parameter, the
#: decoder's pixel ceiling — and this one was not, so `--columns 2000000000` was one flag
#: away from allocating everything the machine has. There is never a reason to exceed the
#: number of variants, because a column past the last one holds nothing.
MAX_COLUMNS = sweep.MAX_VARIANTS


def review_dir(out: Path | None, key: str | None) -> Path:
    """Where the comparison goes (R4.2).

    `--out` is the general form, because `sweep` is a `tool` command and has to work outside
    a workspace like every other one. `review/<key>/` is what a caller inside a workspace
    gets for naming the asset instead — a convenience over the general form, never a
    requirement for one.
    """
    if out is not None and key is not None:
        raise UsageError(
            "two-destinations",
            "give either --out or --key, not both",
            fix="--key writes into review/<key>/ inside the workspace; --out writes anywhere",
        )
    if out is not None:
        return out
    if key is None:
        raise UsageError(
            "no-destination",
            "a sweep needs somewhere to put the comparison",
            fix="give --out <path>, or --key <asset> inside a workspace",
        )
    return ws.require().root / "review" / check_name(key, "key")


def clear(where: Path, *, replace: bool) -> None:
    """R4.3 — a directory that already holds a sweep is not written over by accident.

    `--replace` deletes the previous sweep rather than merging into it. Merging is the
    plausible-looking alternative and it is worse: a second sweep with a narrower range
    would leave the wider one's variants behind, and the contact sheet would show a
    comparison that no single invocation produced.

    **It removes this sweep's three artefacts and nothing else.** The first version called
    `shutil.rmtree(where)` on the whole destination, which is a different and much larger
    promise than "replace the sweep": `--out` is any path a caller names, so pointing it at
    a directory that also holds something else — an asset's own directory, on a re-run for
    convenience — deleted that too. `project.md` is unambiguous that nothing deletes a
    `source` file, and a source is what a model produced: it cost money and is not
    reproducible. No attacker is needed to reach it, only a reused path, and the test that
    covered `--replace` used a directory holding nothing but the sweep, which is exactly
    why it stayed green.
    """
    if not (where / REPORT_NAME).exists():
        return
    if not replace:
        raise UsageError(
            "sweep-exists",
            f"{where} already holds a sweep",
            fix=f"pass --replace to run it again, or write to another path: rm -r {where}",
        )
    shutil.rmtree(where / VARIANTS_DIR, ignore_errors=True)
    (where / CONTACT_NAME).unlink(missing_ok=True)
    (where / REPORT_NAME).unlink(missing_ok=True)


def run_one(
    command: steps.Runnable, frames: list[Frame], given: dict[str, Any]
) -> tuple[steps.Outcome | None, str | None]:
    """One variant, and why it failed if it did (R2.4).

    Broad on purpose, and this is the one place in the project where that is right: a sweep
    exists to find out which parameters work, so a parameter that blows up in the middle of
    the range is a *result*. Stopping there would throw away the eleven variants that did
    run and leave the caller no comparison at all.
    """
    try:
        return command.run([frame.image for frame in frames], given), None
    except Exception as failed:
        return None, f"{type(failed).__name__}: {failed}"


@ssc_command("sweep", help="Run one command across a range of its parameters and compare.")
@click.option("--replace", is_flag=True, help="Replace a sweep already in the destination.")
@click.option("--columns", type=int, default=0, help="Contact sheet columns. Near-square if unset.")
@click.option("--key", default=None, help="Write into review/<key>/ inside the workspace.")
@click.option("--out", default=None, type=click.Path(path_type=Path), help="Where to write.")
@click.option(
    "--vary",
    "declared",
    multiple=True,
    required=True,
    help="name=a,b,c or name=first..last:step. Repeatable; every combination is run.",
)
@click.option("--command", "which", required=True, help="The command to sweep.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def sweep_command(
    source: Path,
    which: str,
    declared: tuple[str, ...],
    out: Path | None,
    key: str | None,
    columns: int,
    replace: bool,
    *,
    dry_run: bool,
) -> Result:
    if not 0 <= columns <= MAX_COLUMNS:
        raise UsageError(
            "invalid-columns",
            f"--columns {columns} is outside 0..{MAX_COLUMNS}",
            fix=f"pass 0 for a near-square sheet, or up to {MAX_COLUMNS}",
        )

    command = steps.runnable(which)
    points = sweep.expand([sweep.parse_vary(one) for one in declared])

    # Every point is parsed and bound-checked before any of them runs (R1.7). Discovering at
    # variant 11 of 12 that a value was out of range has already spent the eleven.
    parsed = [command.read(point.values) for point in points]

    where = review_dir(out, key)
    frames = read_frames(source)

    if dry_run:
        # R4.5 — nothing is written, and what *would* have been is the useful part.
        return Result(
            "tool sweep",
            f"would run {len(points)} variant{'' if len(points) == 1 else 's'} of {which}",
            {
                "command": which,
                "input": str(source),
                "review": str(where),
                "variants": [
                    {"index": point.index, "name": _name(point), "parameters": point.values}
                    for point in points
                ],
            },
            dry_run=True,
        )

    clear(where, replace=replace)

    reported: list[dict[str, Any]] = []
    cells = []
    for point, given in zip(points, parsed, strict=True):
        name = _name(point)
        outcome, why = run_one(command, frames, given)
        if outcome is None:
            reported.append(
                {
                    "index": point.index,
                    "name": name,
                    "parameters": point.values,
                    "status": "failed",
                    "reason": why,
                }
            )
            cells.append(cell_for([], f"{point.index} {point.label} — failed"))
            continue

        into = where / VARIANTS_DIR / name
        written = write_frames(
            source,
            into,
            [Frame(frame.name, image) for frame, image in zip(frames, outcome.frames, strict=True)],
        )
        report = measure(outcome.frames)
        reported.append(
            {
                "index": point.index,
                "name": name,
                "parameters": point.values,
                "status": "ok",
                "path": str(into),
                "written": [str(path) for path in written],
                "doctor": report.as_dict(),
                **outcome.measurement,
            }
        )
        cells.append(cell_for(outcome.frames, f"{point.index} {point.label}"))

    params = ContactParams(columns=columns)
    write_one(where / CONTACT_NAME, draw_labels(sheet(cells, params), cells, params))

    # R2.3 — arithmetic on a measurement, and deliberately not a recommendation. A variant
    # that keyed the whole frame away has no defects because it has nothing left to be
    # wrong; `design.md` carries why this is reported rather than acted on.
    clean = [one for one in reported if one["status"] == "ok"]
    fewest = min(clean, key=lambda one: one["doctor"]["defects"], default=None)

    document = {
        "schema": SCHEMA,
        "command": which,
        "input": str(source),
        "parameters": [one for one in declared],
        "review": str(where),
        "contact_sheet": str(where / CONTACT_NAME),
        "fewest_defects": None if fewest is None else fewest["index"],
        "variants": reported,
    }
    write_one_json(where / REPORT_NAME, document)

    failed = len(reported) - len(clean)
    return Result(
        "tool sweep",
        f"{len(reported)} variant{'' if len(reported) == 1 else 's'} of {which} in {where}"
        + (f", {failed} failed" if failed else ""),
        document,
    )


def _name(point: sweep.Point) -> str:
    """`00_tol-40` — the index first, so an `ls` sorts the way the sweep ran.

    The index is also what makes it unique: two points of a float range can render the same
    label, and a name that collides would silently overwrite a variant.
    """
    return f"{point.index:02d}_{point.label}"


def write_one_json(path: Path, document: dict[str, Any]) -> Path:
    try:
        return write_new(path, (json.dumps(document, indent=2, sort_keys=True) + "\n").encode())
    except OSError as unwritable:
        raise SscError(
            "sweep-unwritable",
            f"{path} could not be written: {unwritable}",
            fix="check that the destination is writable",
        ) from unwritable
