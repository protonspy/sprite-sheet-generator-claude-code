"""`tool style` — quantize a frame set against the project's one locked palette.

The sibling of `tool pixelart`: `pixelart` computes a palette from the set or takes one
ad-hoc, `style` reads the workspace's locked ``palette.json`` and applies it. The palette
is a *project* decision — locked once from a preset, then never re-picked per call — which
is what makes two assets generated a week apart agree. Dither is the same kind of
decision, recorded under ``style:`` in ``ssc.yaml`` and read here, never a flag on the
call. See ``docs/wiki/pages/agent-workflow.md`` for the palette-lock gate.

This command requires a workspace: the palette is the workspace's, and a caller with a
directory of loose PNGs and no ``ssc init`` is ``tool pixelart``'s, not this one's.
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
from ssc.cli.palettes import (
    PALETTE_FILE,
    LockedPalette,
    lock,
    preset_colours,
    preset_names,
    read_locked,
    workspace_dither,
)
from ssc.cli.workspace import Workspace
from ssc.core.style import style_frames


@ssc_command(
    "style",
    help="Quantize frames against the project's locked palette.json.",
    needs_workspace=True,
)
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--preset",
    default=None,
    help=f"Lock this preset into palette.json: {', '.join(preset_names())}. "
    "Required when no palette is locked yet; refused once one is.",
)
def style(
    source: Path,
    out: Path,
    preset: str | None,
    *,
    workspace: Workspace,
    dry_run: bool,
) -> Result:
    palette_path = workspace.root / PALETTE_FILE

    if palette_path.is_file():
        if preset is not None:
            raise UsageError(
                "palette-locked",
                f"{palette_path} is already locked",
                fix="the palette is a project decision, not per-call; "
                "delete palette.json to lock a different one",
            )
        locked = read_locked(palette_path)
    elif preset is not None:
        colours_hex = preset_colours(preset)
        if not dry_run:
            lock(palette_path, preset)
        locked = _palette_from_hex(colours_hex, preset)
    else:
        raise UsageError(
            "no-palette",
            f"no {PALETTE_FILE} in this workspace",
            fix=f"lock one first: ssc tool style --preset <{'|'.join(preset_names())}> "
            "--in <src> --out <out>",
        )

    dither = workspace_dither(workspace)
    frames = read_frames(source)
    outcome = style_frames([frame.image for frame in frames], locked.colours, dither)
    converted = [
        Frame(frame.name, image) for frame, image in zip(frames, outcome.frames, strict=True)
    ]
    written = write_frames(source, out, converted, dry_run=dry_run)
    summary = (
        f"{len(converted)} frame{'' if len(converted) == 1 else 's'} styled "
        f"against {len(outcome.measurement['palette'])} locked colour"
        f"{'' if len(outcome.measurement['palette']) == 1 else 's'}"
    )
    if preset is not None and not palette_path.is_file():
        # Dry-run lock: report what would have been written.
        summary = f"[would lock preset {preset}] {summary}"
    return Result(
        "tool style",
        summary,
        {
            **outcome.measurement,
            "preset": locked.preset,
            "locked": palette_path.is_file() or dry_run,
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


def _palette_from_hex(colours_hex: list[str], preset: str) -> LockedPalette:
    """Build an in-memory locked palette from preset hex, for dry-run or first lock."""
    return LockedPalette(
        colours=np.array([parse_hex(part) for part in colours_hex], dtype=np.uint8),
        preset=preset,
    )
