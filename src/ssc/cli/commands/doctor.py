"""`ssc tool doctor` — measure an asset, name the fix for every defect.

The one `tool` command with no `--out`: it opens files read-only and writes nothing.
"""

from __future__ import annotations

from pathlib import Path

import click
import numpy as np
from PIL import Image

from ssc.cli.errors import SscError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.doctor import (
    BleedParams,
    Check,
    PaletteParams,
    Report,
    SilhouetteParams,
    check_bleed,
    check_drift,
    check_flicker,
    check_halo,
    check_palette,
    check_pixel_grid,
    check_silhouette,
)
from ssc.core.doctor.finding import skipped

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

#: A ceiling on what will be decoded. `doctor` reads art a model produced or somebody
#: downloaded, so the input is attacker-influenced: a fine checkerboard that is tiny on
#: disk decodes to hundreds of megabytes and gives every detector tens of millions of
#: cells to chew through. Pillow's own bomb threshold is both higher and raised as an
#: exception type this project does not otherwise handle, so the limit is stated here.
MAX_PIXELS = 64_000_000

#: The same reasoning for `--cell`: the silhouette mask is built at the target size, so an
#: unbounded cell allocates and labels an unbounded array from an 8x8 input.
MAX_CELL = 4096


def load_image(path: Path) -> np.ndarray:
    try:
        with Image.open(path) as handle:
            width, height = handle.size
            if width * height > MAX_PIXELS:
                raise SscError(
                    "image-too-large",
                    f"{path} is {width}x{height}, over the {MAX_PIXELS:,}-pixel ceiling",
                    fix="scale it down first, or measure a smaller region",
                )
            return np.array(handle.convert("RGBA"))
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as unreadable:
        # DecompressionBombError is a bare Exception, not an OSError, so it would otherwise
        # leave the command as a traceback rather than as this project's error contract.
        raise SscError(
            "unreadable-image",
            f"{path} could not be read as an image: {unreadable}",
            fix="check the file, or point --in at a PNG",
        ) from unreadable


def load_input(path: Path) -> list[np.ndarray]:
    """One image, or a directory read as a frame set sorted by filename.

    Sorted by filename because that is the order the frames were written in and the only
    ordering that survives being copied around; `drift` and `flicker` both depend on
    adjacency meaning something.
    """
    if path.is_file():
        return [load_image(path)]
    if path.is_dir():
        frames = sorted(child for child in path.iterdir() if child.suffix.lower() in IMAGE_SUFFIXES)
        if not frames:
            raise SscError(
                "no-images",
                f"{path} holds no images",
                fix="point --in at a file, or at a directory of frames",
            )
        return [load_image(frame) for frame in frames]
    raise SscError(
        "no-input",
        f"{path} is neither a file nor a directory",
        fix="point --in at an image or at a directory of frames",
    )


def measure(
    frames: list[np.ndarray],
    *,
    cell: tuple[int, int] | None = None,
    palette: tuple[tuple[int, int, int], ...] = (),
    colour_limit: int | None = None,
    grid: tuple[int, int] | None = None,
    chroma: tuple[int, int, int] | None = None,
) -> Report:
    """Every check, in a stable order, on whatever was given.

    A check that does not apply reports `skipped` with its reason rather than being left
    out: a report that omits what it did not run is indistinguishable from one where
    nothing was wrong.
    """
    first = frames[0]
    palette_params = PaletteParams(limit=colour_limit, allowed=palette)
    silhouette_params = SilhouetteParams(cell=cell) if cell else None
    bleed_params = (
        BleedParams(cols=grid[0], rows=grid[1], chroma=chroma) if grid is not None else None
    )

    return Report(
        findings=[
            check_pixel_grid(first),
            check_bleed(first, bleed_params),
            check_drift(frames),
            check_halo(first),
            check_palette(first, palette_params),
            check_flicker(frames),
            check_silhouette(first, silhouette_params),
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
@click.option("--chroma", default=None, help="Key colour for bleed when there is no alpha.")
@click.option("--palette", default=None, help="Comma-separated hex colours the art may use.")
@click.option("--colors", "colour_limit", type=int, default=None, help="Colour budget.")
@click.option("--cell", default=None, help="Target cell as WxH, e.g. 64x64. Silhouette needs it.")
@click.option("--rows", type=int, default=None, help="Sheet rows. With --cols, enables bleed.")
@click.option("--cols", type=int, default=None, help="Sheet columns. With --rows, enables bleed.")
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
    *,
    dry_run: bool,
) -> Result:
    frames = load_input(source)

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
