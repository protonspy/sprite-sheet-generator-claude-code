"""`ssc tool normalise` — the sets of one asset on one baseline, centre and canvas.

`tool align` locks one anchor across the frames of a set; nothing else makes idle's
baseline agree with walk's, or keeps the character one height in both. `normalise` is the
cross-set gate: it resamples each set onto one visible height (4.1), aligns every frame of
every set onto one anchor pixel through `plan_alignment`, and lays each set out as a sheet
through `pack`. Padding and layout are those two; this command orchestrates them and the
scale decision, and reimplements none of them.
"""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli.errors import UsageError
from ssc.cli.frames import read_frames, write_one
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.assemble import ANCHOR_MODES, CanvasTooLarge
from ssc.core.normalise import normalise_sets


def _set_name(source: Path) -> str:
    """The stem a set's sheet is written under: a file's stem, or a directory's name."""
    return source.stem if source.is_file() else source.name


@ssc_command(
    "normalise",
    help="Put the sets of one asset on one baseline, centre, canvas and scale.",
)
@click.option(
    "--in",
    "sources",
    multiple=True,
    required=True,
    type=click.Path(path_type=Path),
    help="A frame set (an image, or a directory of frames). Repeat once per animation.",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(path_type=Path),
    help="Directory to write one sheet per set.",
)
@click.option("--cols", "columns", type=int, default=0, help="Columns per sheet. Default: one row.")
@click.option(
    "--anchor",
    "mode",
    type=click.Choice(ANCHOR_MODES),
    default="feet",
    help="Which anchor to align on. Must match the one `align` used.",
)
def normalise(
    sources: tuple[Path, ...],
    out: Path,
    columns: int,
    mode: str,
    *,
    dry_run: bool,
) -> Result:
    if columns < 0:
        raise UsageError(
            "invalid-cols",
            f"--cols {columns} is negative",
            fix="use 0 for one row, or a positive column count",
        )

    frames_per_set = [read_frames(Path(source)) for source in sources]
    sets = [[frame.image for frame in frames] for frames in frames_per_set]
    try:
        result = normalise_sets(sets, mode=mode, columns=columns)
    except CanvasTooLarge as refused:
        raise UsageError(
            "canvas-too-large", str(refused), fix="normalise smaller sets, or in stages"
        ) from refused
    except ValueError as refused:
        raise UsageError(
            "cannot-normalise",
            str(refused),
            fix="point --in at non-empty frame sets; a blank set has no height to scale from",
        ) from refused

    sheet_reports: list[dict[str, object]] = []
    for source, sheet, frames in zip(sources, result.sheets, frames_per_set, strict=True):
        target = out / f"{_set_name(Path(source))}.png"
        write_one(target, sheet, dry_run=dry_run)
        sheet_reports.append(
            {"name": _set_name(Path(source)), "frames": len(frames), "written": str(target)}
        )

    cell = result.layout.cell
    summary = (
        f"{len(result.sheets)} set{'' if len(result.sheets) == 1 else 's'} on {cell[0]}x{cell[1]}"
    )
    return Result(
        "tool normalise",
        summary,
        {**result.as_dict(), "sheets": sheet_reports},
        dry_run=dry_run,
    )
