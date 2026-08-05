"""`ssc tool doctor` — measure an asset, name the fix for every defect.

The one `tool` command with no `--out`: it opens files read-only and writes nothing.
"""

from __future__ import annotations

from pathlib import Path

import click
import numpy as np

from ssc.cli import kinds
from ssc.cli import workspace as ws
from ssc.cli.args import parse_guides
from ssc.cli.errors import SscError
from ssc.cli.frames import load_input
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.doctor import (
    BleedParams,
    Check,
    ConsistencyParams,
    NineSliceParams,
    PaletteParams,
    Report,
    SilhouetteParams,
    check_bleed,
    check_consistency,
    check_drift,
    check_flicker,
    check_halo,
    check_nineslice,
    check_palette,
    check_pixel_grid,
    check_seam,
    check_silhouette,
)
from ssc.core.doctor.finding import skipped

#: `--cell` needs a ceiling of its own: the silhouette mask is built at the target size, so
#: an unbounded cell allocates and labels an unbounded array from an 8x8 input. The ceiling
#: on what gets *decoded* is `frames.MAX_PIXELS`, shared with every other reader in the
#: project rather than restated here.
MAX_CELL = 4096


def measure(
    frames: list[np.ndarray],
    *,
    cell: tuple[int, int] | None = None,
    palette: tuple[tuple[int, int, int], ...] = (),
    colour_limit: int | None = None,
    grid: tuple[int, int] | None = None,
    chroma: tuple[int, int, int] | None = None,
    seam: bool = False,
    nineslice: tuple[int, int, int, int] | None = None,
    want_nineslice: bool = False,
    min_consistency: float | None = None,
) -> Report:
    """Every check, in a stable order, on whatever was given.

    A check that does not apply reports `skipped` with its reason rather than being left
    out: a report that omits what it did not run is indistinguishable from one where
    nothing was wrong.

    `seam` is the one check that has to be *asked for* (tile-assets R2.4). The seven are
    meaningful on any asset; `seam` is meaningful only on something meant to tile, and run
    by default it would report every character frame as broken for the unremarkable fact
    that its left edge is not its right edge. `consistency` is always on, like `drift` and
    `flicker`: it needs a set, skips on a single frame, and reports a number rather than a
    judgement unless `min_consistency` was given.
    """
    first = frames[0]
    palette_params = PaletteParams(limit=colour_limit, allowed=palette)
    silhouette_params = SilhouetteParams(cell=cell) if cell else None
    bleed_params = (
        BleedParams(cols=grid[0], rows=grid[1], chroma=chroma) if grid is not None else None
    )
    consistency_params = ConsistencyParams(min_consistency=min_consistency)

    return Report(
        findings=[
            check_pixel_grid(first),
            check_bleed(first, bleed_params),
            check_drift(frames),
            check_halo(first),
            check_palette(first, palette_params),
            check_flicker(frames),
            check_silhouette(first, silhouette_params),
            check_seam(first)
            if seam
            else skipped(Check.SEAM, "seam applies to tiles; ask for it with --check seam"),
            check_nineslice(first, NineSliceParams(guides=nineslice))
            if want_nineslice
            else skipped(
                Check.NINESLICE,
                "nineslice applies to panels; ask for it with --check nineslice",
            ),
            check_consistency(frames, consistency_params),
        ]
    )


def parse_hex(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise SscError(
            "invalid-colour",
            f"{value!r} is not a 6-digit hex colour",
            fix="write it as rrggbb, for example 0d2b45",
        )
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


@ssc_command("doctor", help="Measure an asset's defects and name the fix for each.")
@click.option("--guides", default=None, help="left,right,top,bottom — what nineslice needs.")
@click.option("--kind", default=None, help="Run the checks this kind declares.")
@click.option(
    "--check",
    "asked_for",
    multiple=True,
    type=click.Choice([str(Check.SEAM), str(Check.NINESLICE)]),
    help="Run a check that is not one of the seven. Repeatable.",
)
@click.option("--chroma", default=None, help="Key colour for bleed when there is no alpha.")
@click.option("--palette", default=None, help="Comma-separated hex colours the art may use.")
@click.option("--colors", "colour_limit", type=int, default=None, help="Colour budget.")
@click.option("--cell", default=None, help="Target cell as WxH, e.g. 64x64. Silhouette needs it.")
@click.option("--rows", type=int, default=None, help="Sheet rows. With --cols, enables bleed.")
@click.option("--cols", type=int, default=None, help="Sheet columns. With --rows, enables bleed.")
@click.option(
    "--min-consistency",
    "min_consistency",
    type=float,
    default=None,
    help="Below this mean shape similarity the set is inconsistent. None reports the number only.",
)
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def doctor(
    source: Path,
    cols: int | None,
    rows: int | None,
    cell: str | None,
    colour_limit: int | None,
    palette: str | None,
    chroma: str | None,
    asked_for: tuple[str, ...],
    kind: str | None,
    guides: str | None,
    min_consistency: float | None,
    *,
    dry_run: bool,
) -> Result:
    frames = load_input(source)
    # Two ways to ask for the same check, because there are two callers. A person types
    # `--check seam`; a harness names the asset's kind and gets whatever that profile
    # declares, which is where a project decides what its tiles are measured against.
    wanted = set(asked_for)
    if kind is not None:
        wanted |= set(kinds.resolve(kind, ws.require()).profile.checks)

    target_cell: tuple[int, int] | None = None
    if cell:
        parts = cell.lower().split("x")
        if len(parts) != 2 or not all(part.isdigit() for part in parts):
            raise SscError("invalid-cell", f"{cell!r} is not a size like 64x64", fix="use WxH")
        target_cell = (int(parts[0]), int(parts[1]))
        if not all(0 < side <= MAX_CELL for side in target_cell):
            raise SscError(
                "invalid-cell",
                f"{cell!r} is outside 1..{MAX_CELL}; the mask is built at the target size",
                fix=f"use a cell up to {MAX_CELL}x{MAX_CELL}",
            )

    grid = (cols, rows) if cols is not None and rows is not None else None
    allowed = tuple(parse_hex(part) for part in palette.split(",")) if palette else ()

    report = measure(
        frames,
        cell=target_cell,
        palette=allowed,
        colour_limit=colour_limit,
        grid=grid,
        chroma=parse_hex(chroma) if chroma else None,
        seam=str(Check.SEAM) in wanted,
        want_nineslice=str(Check.NINESLICE) in wanted,
        nineslice=parse_guides(guides),
        min_consistency=min_consistency,
    )

    if grid is None and (cols is not None or rows is not None):
        report = Report(
            findings=[
                skipped(Check.BLEED, "a grid needs both --cols and --rows")
                if finding.check is Check.BLEED
                else finding
                for finding in report.findings
            ]
        )

    defects = len(report.defects)
    summary = (
        f"{len(frames)} frame{'' if len(frames) == 1 else 's'}: "
        f"{defects} defect{'' if defects == 1 else 's'}"
    )
    # Measuring is the job, and it succeeded. Exiting non-zero on a defect would make a
    # clean run and a broken tool indistinguishable to a harness.
    return Result("tool doctor", summary, report.as_dict(), dry_run=dry_run)
