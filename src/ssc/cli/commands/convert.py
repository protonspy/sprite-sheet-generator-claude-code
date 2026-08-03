"""`ssc tool snap`, `ssc tool pixelart` and `ssc tool board`.

The three commands that need no workspace (R1.1). They find one if they are standing in
it — `snap` caches there — but none of them requires it, because a caller with a directory
of loose PNGs and no `ssc init` is exactly who these are for.
"""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli import workspace as ws
from ssc.cli.cache import Cache
from ssc.cli.errors import UsageError
from ssc.cli.frames import Frame, read_frames, write_frames, write_one
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.snap import SnapParams, snap_frames
from ssc.cli.snapper import Snapper
from ssc.core.board import checkerboard, pose_board
from ssc.core.pixelart import (
    PaletteParams,
    build_palette,
    clean_clusters,
    map_to_palette,
    outline,
)

#: A colour budget outside this is not a budget. The floor is 2 because one colour is not
#: an image, and the ceiling is the largest indexed palette a PNG can carry.
MIN_COLORS, MAX_COLORS = 2, 256

#: A grid larger than this against any realistic frame leaves nothing to snap onto, and
#: the module stops returning square output well before it.
MAX_PIXEL_SIZE = 256.0

#: A board is generated, so nothing bounds it but this. The ceiling is the same order as
#: `frames.MAX_PIXELS` for the same reason: `--cell 100000 --grid 9x9` is one argument away
#: from allocating everything the machine has.
MAX_BOARD_SIDE = 8192


def parse_hex(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise UsageError(
            "invalid-colour",
            f"{value!r} is not a 6-digit hex colour",
            fix="write it as rrggbb, for example 0d2b45",
        )
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def parse_size(value: str, what: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise UsageError("invalid-size", f"{value!r} is not a {what} like 3x2", fix="use WxH")
    width, height = int(parts[0]), int(parts[1])
    if not all(0 < side <= MAX_BOARD_SIDE for side in (width, height)):
        raise UsageError(
            "invalid-size",
            f"{value!r} is outside 1..{MAX_BOARD_SIDE} on a side",
            fix=f"use a size up to {MAX_BOARD_SIDE}x{MAX_BOARD_SIDE}",
        )
    return width, height


def cache_for(where: Path) -> Cache | None:
    """The workspace cache, when the command is standing in a workspace (R2.7).

    `None` outside one, rather than inventing a cache directory somewhere in the user's
    home: `cache/` belongs to a workspace by `workspace-foundation`'s design, and choosing
    a second home for it is not this leaf's decision to make.
    """
    found = ws.find(where)
    return Cache(found.cache) if found is not None else None


@ssc_command("snap", help="Recover the real pixel grid from art that only looks like pixel art.")
@click.option("--grid", is_flag=True, help="Emit at the recovered grid size, not the original.")
@click.option("--palette", default="", help="Comma-separated hex colours to snap onto.")
@click.option("--pixel-size", type=float, default=None, help="Force the grid instead of detecting.")
@click.option("--colors", type=int, default=16, help="Colour budget for the recovered image.")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def snap(
    source: Path,
    out: Path,
    colors: int,
    pixel_size: float | None,
    palette: str,
    grid: bool,
    *,
    dry_run: bool,
) -> Result:
    if not MIN_COLORS <= colors <= MAX_COLORS:
        raise UsageError(
            "invalid-colors",
            f"--colors {colors} is outside {MIN_COLORS}..{MAX_COLORS}",
            fix=f"pass a budget between {MIN_COLORS} and {MAX_COLORS}",
        )
    if pixel_size is not None and not 0 < pixel_size <= MAX_PIXEL_SIZE:
        raise UsageError(
            "invalid-pixel-size",
            f"--pixel-size {pixel_size} is outside 0..{MAX_PIXEL_SIZE}",
            fix="pass the width of one intended pixel, in pixels of the input",
        )

    frames = read_frames(source)
    params = SnapParams(colors=colors, pixel_size=pixel_size, palette=palette, grid=grid)
    # The grid is computed even under --dry-run: it is the number a caller runs this
    # command to find out, and reporting the targets without it would answer the less
    # interesting half of the question. Nothing is written either way.
    snapped, measured = snap_frames(frames, params, Snapper(), cache_for(source))
    written = write_frames(source, out, snapped, dry_run=dry_run)

    size = measured["grid"]
    return Result(
        "tool snap",
        f"{len(snapped)} frame{'' if len(snapped) == 1 else 's'} on a "
        f"{size['width']}x{size['height']} grid",  # type: ignore[index]
        {**measured, "written": [str(path) for path in written]},
        dry_run=dry_run,
        cached=bool(measured["reused"]),
    )


@ssc_command("pixelart", help="Convert art of any origin into true pixel art.")
@click.option("--outline", "outline_colour", default=None, help="Hex colour for a 1px outline.")
@click.option("--min-cluster", type=int, default=0, help="Absorb colour groups smaller than this.")
@click.option(
    "--dither",
    type=click.Choice(["none", "ordered", "floyd-steinberg"]),
    default="none",
    help="Dithering mode. None unless asked for.",
)
@click.option("--palette", default="", help="Comma-separated hex colours to use exactly.")
@click.option("--colors", type=int, default=16, help="How many colours to compute.")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def pixelart(
    source: Path,
    out: Path,
    colors: int,
    palette: str,
    dither: str,
    min_cluster: int,
    outline_colour: str | None,
    *,
    dry_run: bool,
) -> Result:
    if not MIN_COLORS <= colors <= MAX_COLORS:
        raise UsageError(
            "invalid-colors",
            f"--colors {colors} is outside {MIN_COLORS}..{MAX_COLORS}",
            fix=f"pass a budget between {MIN_COLORS} and {MAX_COLORS}",
        )
    if min_cluster < 0:
        raise UsageError(
            "invalid-min-cluster",
            f"--min-cluster {min_cluster} is negative",
            fix="pass the smallest number of pixels a colour group may keep",
        )

    fixed = tuple(parse_hex(part) for part in palette.split(",")) if palette else ()
    ring = parse_hex(outline_colour) if outline_colour else None

    frames = read_frames(source)
    # One palette, from every frame at once. This is the whole reason the command takes a
    # set rather than a file: quantizing frame by frame is what produces `flicker`.
    computed = build_palette([frame.image for frame in frames], PaletteParams(colors, fixed))

    converted: list[Frame] = []
    for frame in frames:
        image = map_to_palette(frame.image, computed, dither)  # type: ignore[arg-type]
        if min_cluster > 1:
            image = clean_clusters(image, min_cluster)
        if ring is not None:
            image = outline(image, ring)
        converted.append(Frame(frame.name, image))

    written = write_frames(source, out, converted, dry_run=dry_run)
    return Result(
        "tool pixelart",
        f"{len(converted)} frame{'' if len(converted) == 1 else 's'} on "
        f"{len(computed)} colour{'' if len(computed) == 1 else 's'}",
        {
            "frames": len(converted),
            "palette": [f"{r:02x}{g:02x}{b:02x}" for r, g, b in computed],
            "dither": dither,
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


@click.group("board", help="Generate the reference images the generation step needs.")
def board() -> None:
    """Two subcommands rather than one command with a mode flag: a checkerboard and a pose
    board take different parameters, and a flag that changes which options are legal is a
    command wearing a disguise."""


@ssc_command("checker", help="A black-and-white checkerboard, to impose block discipline.")
@click.option("--size", default="1024x1024", help="Image size as WxH.")
@click.option("--square", type=int, default=8, help="Side of one square, in pixels.")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="Where to write it.")
def board_checker(out: Path, square: int, size: str, *, dry_run: bool) -> Result:
    width, height = parse_size(size, "size")
    if not 0 < square <= min(width, height):
        raise UsageError(
            "invalid-square",
            f"--square {square} does not fit in {width}x{height}",
            fix="use a square smaller than the shorter side",
        )

    image, layout = checkerboard(square, width, height)
    written = write_one(out, image, dry_run=dry_run)
    return Result(
        "tool board checker",
        f"a {layout.width}x{layout.height} checkerboard of {square}px squares",
        {"layout": layout.as_dict(), "written": [str(path) for path in written]},
        dry_run=dry_run,
    )


@ssc_command("poses", help="A grid of empty cells, to declare the frame layout.")
@click.option("--cell", type=int, default=256, help="Side of one cell, in pixels.")
@click.option("--grid", "shape", default="3x2", help="Cells as COLSxROWS.")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="Where to write it.")
def board_poses(out: Path, shape: str, cell: int, *, dry_run: bool) -> Result:
    columns, rows = parse_size(shape, "grid")
    if (
        not 0 < cell <= MAX_BOARD_SIDE
        or columns * cell > MAX_BOARD_SIDE
        or rows * cell > MAX_BOARD_SIDE
    ):
        raise UsageError(
            "invalid-cell",
            f"--cell {cell} over {columns}x{rows} is past {MAX_BOARD_SIDE} on a side",
            fix=f"use a smaller cell, or fewer cells: {columns}x{rows} allows "
            f"{MAX_BOARD_SIDE // max(columns, rows)}",
        )

    image, layout = pose_board(columns, rows, cell)
    written = write_one(out, image, dry_run=dry_run)
    return Result(
        "tool board poses",
        f"{columns}x{rows} cells of {cell}px, {layout.width}x{layout.height} in all",
        {"layout": layout.as_dict(), "written": [str(path) for path in written]},
        dry_run=dry_run,
    )


board.add_command(board_checker)
board.add_command(board_poses)
