"""The `tool` commands that need no workspace: `snap`, `pixelart`, `bgremove`, `board`,
`tile`, `normal`, `layers`, `ninepatch` and `states`.

They find a workspace if they are standing in one — `snap` caches there — but none requires
it, because a caller with a directory of loose PNGs and no `ssc init` is exactly who these
are for.

They share a module because they share a shape: `--in`/`--out`, the frame-set reading, the
refusal to overwrite, and a ceiling on every dial whose cost scales with its own value. This
docstring used to say a fifth command was the point to split it up; there are nine now and
the shape has held, so what would justify splitting is a command that breaks it rather than
the count reaching some number.
"""

from __future__ import annotations

from pathlib import Path

import click

from ssc.cli import workspace as ws
from ssc.cli.args import parse_guides
from ssc.cli.cache import Cache
from ssc.cli.errors import UsageError
from ssc.cli.frames import Frame, read_frames, write_frames, write_one
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.snap import SnapParams, snap_frames
from ssc.cli.snapper import Snapper
from ssc.core import ninepatch
from ssc.core.assemble import pack
from ssc.core.bgremove import PRESETS, BgRemoveParams, remove
from ssc.core.board import checkerboard, pose_board
from ssc.core.normal import MAX_STRENGTH, MIN_STRENGTH
from ssc.core.normal import derive as derive_normal
from ssc.core.pixelart import (
    PaletteParams,
    build_palette,
    clean_clusters,
    map_to_palette,
    outline,
)
from ssc.core.tile import MODES as TILE_MODES
from ssc.core.tile import close as close_wrap

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

#: The distance from black to white in RGB. A tolerance at it keys every pixel of every
#: frame, which is not a background removal but an erasure, so it is the ceiling.
MAX_TOLERANCE = 442

#: `cv2.erode` costs one pass per iteration *regardless of image size*, so this is the one
#: dial whose cost an attacker sets independently of the input: a 1x1 PNG and a large enough
#: number runs for hours. That is what separates it from `--despeckle` and `--min-cluster`,
#: which take a number but cost one pass over the image whatever it is, and so need no
#: ceiling. A trim wider than the largest sprite anyone packs has removed the whole
#: silhouette long before it gets here.
MAX_TRIM = 512


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


def parse_key(value: str) -> tuple[int, int, int]:
    """A preset name or a hex colour (R1.1, R1.4).

    Presets are named rather than remembered: nobody should have to recall that green
    screen is `00b140` in order to take a background out.
    """
    if value.lower() in PRESETS:
        return PRESETS[value.lower()]
    try:
        return parse_hex(value)
    except UsageError as refused:
        raise UsageError(
            "invalid-chroma",
            f"{value!r} is neither a preset nor a 6-digit hex colour",
            fix=f"use one of {', '.join(sorted(PRESETS))}, or write it as rrggbb",
        ) from refused


@ssc_command("bgremove", help="Take the background out by chroma key.")
@click.option("--despeckle", type=int, default=0, help="Drop opaque groups below this many px.")
@click.option("--edge-trim", type=int, default=0, help="Shrink the opaque region by this many px.")
@click.option("--edge-pass", is_flag=True, help="Take the key's cast out of the border pixels.")
@click.option(
    "--mode",
    type=click.Choice(["flood", "global"]),
    default="flood",
    help="flood keys only what the border reaches; global keys every match.",
)
@click.option("--tol", type=int, default=60, help="How far from the key still counts as key.")
@click.option("--chroma", default="green", help="Key colour: a preset, or rrggbb.")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def bgremove(
    source: Path,
    out: Path,
    chroma: str,
    tol: int,
    mode: str,
    edge_pass: bool,
    edge_trim: int,
    despeckle: int,
    *,
    dry_run: bool,
) -> Result:
    if not 0 <= tol <= MAX_TOLERANCE:
        raise UsageError(
            "invalid-tolerance",
            f"--tol {tol} is outside 0..{MAX_TOLERANCE}",
            fix=f"{MAX_TOLERANCE} is the distance between black and white; anything at it "
            "keys the whole frame",
        )
    for name, value in (("--edge-trim", edge_trim), ("--despeckle", despeckle)):
        if value < 0:
            raise UsageError(
                "invalid-amount", f"{name} {value} is negative", fix=f"pass {name} 0 or more"
            )
    if edge_trim > MAX_TRIM:
        raise UsageError(
            "invalid-amount",
            f"--edge-trim {edge_trim} is past {MAX_TRIM}",
            fix=f"pass {MAX_TRIM} or less; a trim that wide has removed the silhouette "
            "long before it gets there",
        )

    params = BgRemoveParams(
        key=parse_key(chroma),
        tolerance=tol,
        mode=mode,  # type: ignore[arg-type]
        edge_pass=edge_pass,
        edge_trim=edge_trim,
        despeckle=despeckle,
    )

    frames = read_frames(source)
    keyed: list[Frame] = []
    transparent = opaque = 0
    for frame in frames:
        image, measured = remove(frame.image, params)
        transparent += measured["transparent_px"]
        opaque += measured["opaque_px"]
        keyed.append(Frame(frame.name, image))

    written = write_frames(source, out, keyed, dry_run=dry_run)
    return Result(
        "tool bgremove",
        f"{len(keyed)} frame{'' if len(keyed) == 1 else 's'}: "
        f"{transparent:,} px transparent, {opaque:,} px kept",
        {
            "frames": len(keyed),
            "transparent_px": transparent,
            "opaque_px": opaque,
            "mode": mode,
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


@ssc_command("tile", help="Close a tile's wrap so it meets itself on every side.")
@click.option(
    "--mode",
    type=click.Choice(list(TILE_MODES)),
    default="edge",
    help="edge copies the opposite edge; mirror makes the tile symmetric.",
)
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of tiles.",
)
def tile_wrap(source: Path, out: Path, mode: str, *, dry_run: bool) -> Result:
    """R1.1, R1.3, R1.5 — one new file per input, and never a blend."""
    frames = read_frames(source)
    closed: list[Frame] = []
    moved = 0
    for frame in frames:
        try:
            image, report = close_wrap(frame.image, mode=mode)
        except ValueError as refused:
            raise UsageError(
                "not-tileable",
                f"{frame.name}: {refused}",
                fix="a tile needs at least two pixels on each side",
            ) from refused
        moved += int(report["pixels_changed"])
        closed.append(Frame(frame.name, image))

    written = write_frames(source, out, closed, dry_run=dry_run)
    return Result(
        "tool tile",
        f"{len(closed)} tile{'' if len(closed) == 1 else 's'} closed by {mode}",
        {
            "mode": mode,
            "edges": ["right", "bottom"],
            "tiles": len(closed),
            # What actually moved, not what was written: a tile that already wrapped is
            # reported as the no-op it was, which is the honest answer to "did this do
            # anything" and what makes re-running visibly idempotent.
            "pixels_changed": moved,
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


@ssc_command("normal", help="Derive a normal map so a 2D engine can light the art.")
@click.option("--flip-y", is_flag=True, help="Encode +Y down, for engines that expect it.")
@click.option("--strength", type=float, default=1.0, help="How far the surface tilts.")
@click.option("--out", required=True, type=click.Path(path_type=Path), help="File or directory.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="An image, or a directory of frames.",
)
def normal_map(source: Path, out: Path, strength: float, flip_y: bool, *, dry_run: bool) -> Result:
    """R1.1, R1.3, R1.5, R2.1 — one map per input, and the convention it used."""
    frames = read_frames(source)
    maps: list[Frame] = []
    for frame in frames:
        try:
            maps.append(
                Frame(frame.name, derive_normal(frame.image, strength=strength, flip_y=flip_y))
            )
        except ValueError as refused:
            raise UsageError(
                "invalid-strength",
                str(refused),
                fix=f"pass --strength between {MIN_STRENGTH} and {MAX_STRENGTH}",
            ) from refused

    written = write_frames(source, out, maps, dry_run=dry_run)
    return Result(
        "tool normal",
        f"{len(maps)} normal map{'' if len(maps) == 1 else 's'} at strength {strength}",
        {
            "strength": strength,
            # An engine that assumes the other convention lights every surface backwards, and
            # the map looks correct either way — so the answer travels with the file rather
            # than living in whoever ran the command's memory.
            "convention": "+y-down" if flip_y else "+y-up",
            "maps": len(maps),
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


#: A layer never scrolls faster than the camera, and one that never moves at all is a sky.
#: Both ends are legal, which is why an omitted `--scroll` derives the whole ladder rather
#: than defaulting a layer to zero: zero and "nobody said" would otherwise be one value.
MIN_SCROLL = 0.0
MAX_SCROLL = 1.0


def parse_scroll(value: str | None, layers: int) -> list[float]:
    """One factor per layer, given or derived (R2.2, R2.3, R2.4, R2.6).

    Derived linearly from position: the far layer at `1/n`, the near one at `1`, evenly
    spaced. That is a starting point rather than a claim — real parallax is a ratio of
    distances nobody knows, so the number a caller tunes by eye is the real answer and this
    is what they tune from.
    """
    if layers < 1:
        # Unreachable through `tool layers`, whose `read_frames` refuses an empty directory
        # first — but this function divides by the count, and the next caller may not.
        raise UsageError(
            "no-layers",
            "a stack needs at least one layer",
            fix="point --in at a directory of images",
        )
    if value is None:
        return [(index + 1) / layers for index in range(layers)]

    parts = [part.strip() for part in value.split(",") if part.strip()]
    try:
        factors = [float(part) for part in parts]
    except ValueError as refused:
        raise UsageError(
            "invalid-scroll",
            f"{value!r} is not a list of numbers",
            fix="write it as 0.2,0.5,1.0 — one per layer, far to near",
        ) from refused

    if len(factors) != layers:
        raise UsageError(
            "scroll-count",
            f"{len(factors)} scroll factor{'' if len(factors) == 1 else 's'} for {layers} layers",
            fix=f"give {layers}, or omit --scroll and let them be derived",
        )
    for factor in factors:
        if not MIN_SCROLL <= factor <= MAX_SCROLL:
            raise UsageError(
                "invalid-scroll",
                f"a scroll factor of {factor} is outside {MIN_SCROLL}..{MAX_SCROLL}",
                fix="0 is infinitely far away and 1 moves with the camera",
            )
    return factors


@ssc_command("layers", help="Read a stack of background layers and their scroll factors.")
@click.option("--scroll", default=None, help="Comma-separated factors, far to near.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="A directory of layers ordered by filename, far to near — or one image.",
)
def layers(source: Path, scroll: str | None, *, dry_run: bool) -> Result:
    """R2.1, R2.5 — the stack, and the refusal that keeps it one.

    No `--out`: nothing here transforms a pixel. The layers stay the files they were, and
    what this command produces is the stack — which is a fact about the set, not a new image.
    """
    frames = read_frames(source)
    sizes = {(frame.image.shape[1], frame.image.shape[0]) for frame in frames}
    if len(sizes) > 1:
        found = ", ".join(f"{width}x{height}" for width, height in sorted(sizes))
        raise UsageError(
            "layers-differ",
            f"a background scrolls every layer across one viewport, and these are {found}",
            fix="ssc tool expand them to a common size",
        )

    factors = parse_scroll(scroll, len(frames))
    width, height = next(iter(sizes))
    return Result(
        "tool layers",
        f"{len(frames)} layer{'' if len(frames) == 1 else 's'} at {width}x{height}",
        {
            "layered": True,
            "size": {"width": width, "height": height},
            "derived": scroll is None,
            "layers": [
                {"index": index, "file": frame.name, "scroll": factor}
                for index, (frame, factor) in enumerate(zip(frames, factors, strict=True))
            ],
        },
        dry_run=dry_run,
    )


#: The four a control has, in the order an engine expects them laid out. A closed set, which
#: is unusual in this project and right here: an engine looks up `hover`, so a file named
#: `hovver` that packed silently would produce a control whose hover state nothing queries —
#: and the failure reads as "the button doesn't light up", with no error to explain it.
STATES = ("normal", "hover", "pressed", "disabled")


@ssc_command("ninepatch", help="Report the guides an engine stretches a panel by.")
@click.option("--guides", default=None, help="left,right,top,bottom. Omit to derive them.")
@click.option(
    "--in", "source", required=True, type=click.Path(path_type=Path), help="A panel image."
)
def ninepatch_guides(source: Path, guides: str | None, *, dry_run: bool) -> Result:
    """R1.1, R1.4, R1.5 — the four numbers, and the nine regions they make.

    No `--out`, for `doctor`'s reason: the guides are a fact about the art, not a new image.
    """
    frames = read_frames(source)
    if len(frames) != 1:
        raise UsageError(
            "not-one-panel",
            f"a nine-patch is one image and {source} holds {len(frames)}",
            fix="point --in at the panel itself",
        )
    image = frames[0].image
    resolved = ninepatch.guides_for(image, parse_guides(guides))
    try:
        described = ninepatch.describe(image, resolved)
    except ValueError as refused:
        raise UsageError(
            "invalid-guides",
            str(refused),
            fix="leave a centre: left + right must be less than the width, and likewise down",
        ) from refused

    left, right, top, bottom = resolved
    return Result(
        "tool ninepatch",
        f"guides {left},{right},{top},{bottom} on {image.shape[1]}x{image.shape[0]}",
        {
            **described,
            "derived": guides is None,
            "size": {"width": int(image.shape[1]), "height": int(image.shape[0])},
        },
        dry_run=dry_run,
    )


@ssc_command("states", help="Pack a control's states into one sheet.")
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="A directory whose filenames are state names.",
)
def control_states(source: Path, out: Path, *, dry_run: bool) -> Result:
    """R3.1, R3.2, R3.3 — one sheet, in the order the engine expects."""
    frames = read_frames(source)
    named: dict[str, Frame] = {}
    for frame in frames:
        # Lower-cased, so `Hover.png` is the hover state — and that is exactly why the
        # collision has to be refused rather than resolved: `Hover.png` beside `hover.PNG`
        # would otherwise drop one of them from the sheet with nothing said.
        state = Path(frame.name).stem.lower()
        if state in named:
            raise UsageError(
                "duplicate-state",
                f"{named[state].name} and {frame.name} are both the {state!r} state",
                fix="one file per state; rename or remove one of them",
            )
        named[state] = frame

    unknown = sorted(set(named) - set(STATES))
    if unknown:
        raise UsageError(
            "unknown-state",
            f"{', '.join(unknown)} {'is' if len(unknown) == 1 else 'are'} not a control state",
            fix=f"name the files after {', '.join(STATES)}",
        )

    sizes = {(frame.image.shape[1], frame.image.shape[0]) for frame in frames}
    if len(sizes) > 1:
        found = ", ".join(f"{width}x{height}" for width, height in sorted(sizes))
        raise UsageError(
            "states-differ",
            f"a control's states are one size and these are {found}",
            fix="ssc tool expand them to a common size",
        )

    # Canonical order, not filename order: an engine indexes by position, and `disabled`
    # sorting before `normal` alphabetically would put them in the wrong cells.
    present = [state for state in STATES if state in named]
    width, height = next(iter(sizes))
    sheet, layout = pack([named[state].image for state in present], columns=len(present))
    written = write_one(out, sheet, dry_run=dry_run)
    return Result(
        "tool states",
        f"{len(present)} state{'' if len(present) == 1 else 's'} as one sheet",
        {
            **layout.as_dict(),
            "states": [
                {
                    "name": state,
                    "rect": {"x": index * width, "y": 0, "width": width, "height": height},
                }
                for index, state in enumerate(present)
            ],
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )
