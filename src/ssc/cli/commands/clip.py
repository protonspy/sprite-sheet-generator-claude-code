"""`ssc tool clip` — a generated clip becomes a frame set.

The step between `gen video` and everything downstream of it. A walk cycle arrives as four
seconds and a hundred frames; a sheet needs eight to twelve spanning exactly one cycle, and
until this existed that was done by hand or not at all.
"""

from __future__ import annotations

import math
from functools import partial
from pathlib import Path
from typing import Any

import click

from ssc.cli.clip import read_clip
from ssc.cli.commands.recover import destination, transform_into_asset
from ssc.cli.errors import UsageError
from ssc.cli.frames import Frame, write_frames
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.assemble import trim_box
from ssc.core.clip import closes_at, positions

#: What the frames are called when they are written loose. A clip is one file, so there are
#: no names to keep — unlike every other `tool` command, whose input is already a set.
FRAME_NAME = "{index:03d}.png"


def seconds_range(
    frames: int, fps: float, start: float | None, end: float | None
) -> tuple[int, int]:
    """The frame indices a range in seconds names (R3.3).

    Seconds rather than frames on the command line, because that is what somebody reading a
    clip has: they watched it and the cycle starts a second in. Converting here means the
    frame rate is read from the container rather than assumed.
    """
    for given, flag in ((start, "--from"), (end, "--to")):
        if given is not None and not math.isfinite(given):
            # `nan` walks through every `<=` check below, because comparing against it is
            # always False, and then `int(nan)` raises far from here. The same trap
            # `check_wait` closes for `--timeout`, and click's FLOAT accepts both literals.
            raise UsageError(
                "invalid-range",
                f"{flag} {given} is not a number of seconds",
                fix="give a second inside the clip, or leave it out",
            )
    if start is None and end is None:
        return 0, frames
    if fps <= 0:
        raise UsageError(
            "no-frame-rate",
            "this clip reports no frame rate, so a range in seconds cannot be converted",
            fix="sample the whole clip, or give the range in frames with --from-frame",
        )
    first = 0 if start is None else int(start * fps)
    last = frames if end is None else int(end * fps)
    if not 0 <= first < last <= frames:
        raise UsageError(
            "invalid-range",
            f"{start}s to {end}s is not inside a clip of {frames / fps:.2f}s",
            fix=f"give a range inside 0 to {frames / fps:.2f}",
        )
    return first, last


@ssc_command("clip", help="Sample a generated clip into a frame set. Free and local.")
@click.option(
    "--whole",
    is_flag=True,
    help="Sample the whole clip instead of looking for where the cycle closes.",
)
@click.option("--to", "end", type=float, default=None, help="Sample up to this second.")
@click.option("--from", "start", type=float, default=None, help="Sample from this second.")
@click.option("--frames", "count", type=int, default=8, help="How many frames to write.")
@click.option("--asset", default=None, help="Record into this <kind>/<key>.")
@click.option("--out", default=None, type=click.Path(path_type=Path), help="Or here.")
@click.option("--in", "source", required=True, type=click.Path(path_type=Path))
def clip_command(
    source: Path,
    out: Path | None,
    asset: str | None,
    count: int,
    start: float | None,
    end: float | None,
    whole: bool,
    *,
    dry_run: bool,
) -> Result:
    destination(asset, out)
    read = read_clip(source)
    first, last = seconds_range(len(read.frames), read.fps, start, end)

    # The cycle is looked for inside the range, not across the clip: a caller who named a
    # range has already said where the motion they mean is.
    inside = read.frames[first:last]
    cycle = None if whole else closes_at(inside)
    over = cycle if cycle is not None else len(inside)

    try:
        taken = positions(count, over)
    except ValueError as refused:
        raise UsageError(
            "too-many-frames",
            str(refused),
            fix="ask for fewer frames, or widen the range",
        ) from refused

    sampled = [
        Frame(FRAME_NAME.format(index=at + 1), inside[index]) for at, index in enumerate(taken)
    ]

    sidecar_path: str | None = None
    if asset is not None:
        written, sidecar_path = transform_into_asset(
            asset,
            [frame.image for frame in sampled],
            command="tool clip",
            stage="clip",
            params={
                "frames": count,
                "cycle": cycle,
                "sampled": taken,
                "range": [first, last],
            },
            source=source,
            total=len(sampled),
            # A clip is one file and an asset's authored boxes are per frame of a set that
            # did not exist until now, so there is nothing to move: the identity keeps every
            # box where it is, and `transform_into_asset` still refuses a sidecar it cannot
            # line up rather than silently disagreeing about the frame count.
            move=partial(trim_box, kept=(0, 0, inside[0].shape[1], inside[0].shape[0])),
            dry_run=dry_run,
        )
    else:
        assert out is not None
        written = [str(path) for path in write_frames(source, out, sampled, dry_run=dry_run)]

    payload: dict[str, Any] = {
        "frames": len(sampled),
        "clip": {"frames": len(read.frames), "fps": round(read.fps, 3)},
        "cycle": cycle,
        "sampled": taken,
        "range": {"first": first, "last": last},
        "written": written,
    }
    if asset is not None:
        payload["sidecar"] = sidecar_path
    return Result(
        "tool clip",
        f"{len(sampled)} frame{'' if len(sampled) == 1 else 's'} from "
        + (f"a cycle of {cycle}" if cycle is not None else f"{len(inside)} frames, no cycle found"),
        payload,
        dry_run=dry_run,
    )
