"""`tool recolour` — map one palette onto another, the free variant path.

A red slime and a blue slime are one asset and a colour map rather than two paid
generations (task 5.3). The frames are already quantized against a source palette;
`--from` names that palette and `--to` the target, aligned by position — colour 0 of
`--from` becomes colour 0 of `--to`. The two must be the same length, because a colour
map with no target for a source colour is a map that drops it silently, and the budget
guard's job in task 5.4 is to refuse the paid call this answers, not to let this one lie.

Like `tool pixelart`, this needs no workspace: it works on a directory of loose PNGs, and
the colour map is given per call. It is the free path; `tool style` is the project-locked
path.
"""

from __future__ import annotations

from pathlib import Path

import click
import numpy as np

from ssc.cli.args import parse_hex
from ssc.cli.errors import UsageError
from ssc.cli.frames import Frame, read_frames, write_frames
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.recolour import recolour_frames


def _palette(text: str) -> tuple[tuple[int, int, int], ...]:
    """Comma-separated hex colours into a tuple of RGB triples."""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    return tuple(parse_hex(part) for part in parts)


@ssc_command(
    "recolour",
    help="Map a frame set from one palette onto another, position by position.",
)
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames already quantized against --from.",
)
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--from",
    "from_palette",
    required=True,
    help="Comma-separated hex colours the frames already use, e.g. ff0000,00ff00.",
)
@click.option(
    "--to",
    "to_palette",
    required=True,
    help="Comma-separated hex colours to map onto, same length and order as --from.",
)
def recolour(
    source: Path,
    out: Path,
    from_palette: str,
    to_palette: str,
    *,
    dry_run: bool,
) -> Result:
    src = _palette(from_palette)
    dst = _palette(to_palette)
    if not src or not dst:
        raise UsageError(
            "empty-palette",
            "--from and --to must each name at least one colour",
            fix="write them as comma-separated hex, e.g. --from ff0000,00ff00 --to 0000ff,ffff00",
        )
    if len(src) != len(dst):
        raise UsageError(
            "palette-length",
            f"--from has {len(src)} colour(s) but --to has {len(dst)}",
            fix="a colour map needs a target for every source colour; align them by position",
        )

    frames = read_frames(source)
    outcome = recolour_frames(
        [frame.image for frame in frames],
        np.array(src, dtype=np.uint8),
        np.array(dst, dtype=np.uint8),
    )
    converted = [
        Frame(frame.name, image) for frame, image in zip(frames, outcome.frames, strict=True)
    ]
    written = write_frames(source, out, converted, dry_run=dry_run)
    return Result(
        "tool recolour",
        f"{len(converted)} frame{'' if len(converted) == 1 else 's'} recoloured "
        f"across {len(src)} colour map{'' if len(src) == 1 else 's'}",
        {**outcome.measurement, "written": [str(path) for path in written]},
        dry_run=dry_run,
    )
