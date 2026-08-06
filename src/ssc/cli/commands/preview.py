"""`ssc tool preview` — render a frame set as a GIF, or a labelled contact sheet.

The renderer is `core.preview`'s composition (`order`, `contact`) and `cli.preview`'s encoder
(`animated_gif`) — the same one `ssc preview` uses, so the index path and the frame-set path
render through one renderer and this command grows no second one (engine-index R6). What is
here is reading frames off disk, cutting a sheet by its grid when the input is a sheet, and
writing the file; the rest is delegated.
"""

from __future__ import annotations

from pathlib import Path

import click
import numpy as np

from ssc.cli.args import parse_cell
from ssc.cli.atomic import write_new
from ssc.cli.errors import UsageError
from ssc.cli.frames import read_frames
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.preview import render
from ssc.core import preview as core_preview


def _frames(
    source: Path,
    cell: tuple[int, int] | None,
    cols: int | None,
    rows: int | None,
    frame_count: int | None,
) -> list[np.ndarray]:
    """The frames to render: a frame set read off disk, or a sheet cut by its grid.

    `--cell` is the one disambiguator: a single image with `--cell` is a sheet, a single image
    without it is a one-frame set. A grid half-named — `--cell` without `--cols`/`--rows`, or
    the pair without `--cell` — is a usage error rather than a guess, because the grid is what
    `tool bounds` measures and what `ssc index` writes, and inventing it here would give the
    project three places that decide it.
    """
    frames = [frame.image for frame in read_frames(source)]

    if cell is None:
        if cols is not None or rows is not None or frame_count is not None:
            missing = "--cell"
            raise UsageError(
                "incomplete-grid",
                f"--cols/--rows/--frames were given without {missing}",
                fix=f"pass {missing} to cut a sheet, or drop the flags to preview the set",
            )
        return frames

    # `--cell` was given: the input is a sheet, so it must be one image with a full grid.
    if cols is None or rows is None:
        missing = "--cols" if cols is None else "--rows"
        raise UsageError(
            "incomplete-grid",
            f"--cell was given without {missing}",
            fix=f"pass {missing} too, or drop --cell to preview the image as one frame",
        )
    if len(frames) != 1:
        raise UsageError(
            "incomplete-grid",
            "--cell cuts a sheet, but --in is a frame set, not one image",
            fix="drop --cell to preview the set, or point --in at the sheet image",
        )

    count = frame_count if frame_count is not None else cols * rows
    try:
        return core_preview.frames_from_sheet(frames[0], cell, cols, rows, count)
    except ValueError as refused:
        raise UsageError(
            "grid-mismatch", str(refused), fix="check the cell size and grid against the sheet"
        ) from refused


@ssc_command("preview", help="Render a frame set as a GIF, or a labelled contact sheet.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="A frame set (an image, or a directory of frames), or a sheet with --cell.",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(path_type=Path),
    help="File to write — .gif for the animation, .png with --contact.",
)
@click.option("--fps", type=int, default=8, help="Frames per second.")
@click.option(
    "--mode",
    type=click.Choice(core_preview.MODES),
    default="loop",
    help="Playback order: loop, ping-pong, or reverse.",
)
@click.option("--cell", default=None, help="Cell as WxH. With --in a sheet, cuts it into frames.")
@click.option("--cols", type=int, default=None, help="Columns in the sheet grid.")
@click.option("--rows", type=int, default=None, help="Rows in the sheet grid.")
@click.option(
    "--frames",
    "frame_count",
    type=int,
    default=None,
    help="Frames in the sheet (needs --cell). Default: the whole grid.",
)
@click.option(
    "--contact", "as_contact", is_flag=True, help="A labelled contact sheet instead of a GIF."
)
def preview(
    source: Path,
    out: Path,
    fps: int,
    mode: str,
    cell: str | None,
    cols: int | None,
    rows: int | None,
    frame_count: int | None,
    as_contact: bool,
    *,
    dry_run: bool,
) -> Result:
    if fps < 1:
        raise UsageError("invalid-fps", f"--fps {fps} is not a frame rate", fix="use 1 or more")

    frames = _frames(source, parse_cell(cell), cols, rows, frame_count)
    data, _suffix = render(frames, fps=fps, mode=mode, contact=as_contact)
    ordered = core_preview.order(len(frames), mode)

    if not dry_run:
        write_new(out, data)

    return Result(
        "tool preview",
        f"{len(ordered)} frame{'' if len(ordered) == 1 else 's'} as {out.name}",
        {
            "frames": len(frames),
            "ordered": len(ordered),
            "fps": fps,
            "mode": mode,
            "contact": as_contact,
            "written": [str(out)],
        },
        dry_run=dry_run,
    )
