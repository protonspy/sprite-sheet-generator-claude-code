"""`ssc tool pose` — track a pose through an animation cycle, reported per frame.

The model-backed half of the M6 motion-consistency leaf (plan task 10.1). A read-only
report like `doctor` — no `--out`, because pose is measured, not authored — that names the
model it ran, the provider it ran on, and one row per frame carrying each landmark's pixel
position and score.

Under the `[cv]` extra, like `bgremove --model`; without it, the same refusal carrying the
install command, never a traceback.
"""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli import devices
from ssc.cli.commands.convert import cache_for
from ssc.cli.frames import read_frames
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.pose import per_frame, pose_frames
from ssc.core.posetrack import MIN_SCORE, POSE_MODELS


@ssc_command("pose", help="Track a pose through an animation cycle, reported per frame.")
@click.option(
    "--device",
    type=click.Choice(devices.DEVICES),
    default="auto",
    help="Where the model runs. auto takes the best provider usable; a named one never falls back.",
)
@click.option(
    "--model",
    type=click.Choice(sorted(POSE_MODELS)),
    default="movenet",
    help="The pose model, under the [cv] extra.",
)
@click.option(
    "--min-score",
    type=float,
    default=MIN_SCORE,
    help="Landmark score at or above which a keypoint counts as present.",
)
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames ordered by filename.",
)
def pose(source: Path, model: str, device: str, min_score: float, *, dry_run: bool) -> Result:
    """Plan task 10.1 — one row per frame, the provider it ran on, and what was reused."""
    frames = read_frames(source)
    if not 0.0 <= min_score <= 1.0:
        from ssc.cli.errors import UsageError

        raise UsageError(
            "invalid-score",
            f"--min-score {min_score} is outside 0..1",
            fix="pass a threshold between 0 and 1; 0.3 is MoveNet's default for present",
        )

    tracked = pose_frames(
        frames,
        model=model,
        device=device,
        cache=cache_for(source),
        min_score=min_score,
    )
    measurement = tracked.measurement
    frames_reported = int(measurement["frames"])
    visible_mean = measurement.get("visible_mean")

    summary = (
        f"{frames_reported} frame{'' if frames_reported == 1 else 's'} tracked on "
        f"{measurement['device']} ({measurement['model']})"
    )
    if visible_mean is not None:
        summary += f", {visible_mean} visible landmarks mean per frame"

    return Result(
        "tool pose",
        summary,
        {
            "poses": per_frame(tracked.track),
            **measurement,
        },
        dry_run=dry_run,
    )
