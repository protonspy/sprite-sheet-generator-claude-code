"""`ssc tool bounds` — where the sprite is in each frame.

The one measurement the normaliser, the `scale` check and the per-frame box read: the
alpha bounding box, the visible height and width, the baseline row and the centre column.
Reporting it on its own is what lets a person see the number a gate is acted on, before
any requirement is written against it. No `--out`: like `doctor`, it opens files
read-only and writes nothing.
"""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli.frames import read_frames
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.doctor.masks import bounds_of, summarise_bounds


@ssc_command(
    "bounds",
    help="Report each frame's alpha box, visible size, baseline and centre.",
)
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def bounds(source: Path, *, dry_run: bool) -> Result:
    frames = read_frames(source)
    boxes = [bounds_of(frame.image) for frame in frames]
    measured = [
        {"name": frame.name, "bounds": box.as_dict() if box is not None else None}
        for frame, box in zip(frames, boxes, strict=True)
    ]
    summary = f"{len(frames)} frame{'' if len(frames) == 1 else 's'}"
    return Result(
        "tool bounds",
        summary,
        {"frames": measured, "set": summarise_bounds(boxes)},
        dry_run=dry_run,
    )
