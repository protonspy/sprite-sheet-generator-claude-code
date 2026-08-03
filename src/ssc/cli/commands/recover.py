"""`ssc tool cut`, `ssc tool slice` and `ssc tool curate`.

A module of their own rather than three more commands in `convert.py`: these write **into a
workspace** when told to, which is a different shape from the four that only ever take
`--in`/`--out`, and that is the boundary `convert.py`'s own docstring says to split on.

`cut` and `slice` are the same detector with different output bindings. Keeping them
together keeps the three detection modes in one place; splitting them by binding would have
produced the same detector twice, and the second copy is the one that drifts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import numpy as np

from ssc.cli import meta
from ssc.cli import workspace as ws
from ssc.cli.commands.convert import MAX_BOARD_SIDE, parse_hex, parse_key, parse_size
from ssc.cli.errors import SscError, UsageError
from ssc.cli.frames import Frame, encode, load_image, read_frames, write_frames, write_one
from ssc.cli.listing import under_assets
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.assemble import expand, flip, onion, pack, plan_alignment
from ssc.core.curate import differences
from ssc.core.recover import (
    Rect,
    chroma_rects,
    crop,
    detect_grid,
    grid_rects,
    in_reading_order,
    island_rects,
    keep,
    rects_from,
)

FRAMES_STAGE = "frames"


#: A sheet is not a million cells. `--grid` is typed rather than read off the image, but an
#: agent may well derive it from something the image suggested — and `columns * rows` is a
#: file each. Same ceiling as the detector's, for the same reason.
MAX_CELLS = 4096

#: `--by` becomes padding on every side, so it is a dial whose cost is its own value.
MAX_MARGIN = MAX_BOARD_SIDE


def parse_grid(value: str) -> tuple[int, int]:
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise UsageError("invalid-grid", f"{value!r} is not a grid like 4x2", fix="use COLSxROWS")
    columns, rows = int(parts[0]), int(parts[1])
    if columns < 1 or rows < 1:
        raise UsageError("invalid-grid", f"{value!r} has no cells", fix="use COLSxROWS, both ≥ 1")
    if columns * rows > MAX_CELLS:
        raise UsageError(
            "invalid-grid",
            f"{value!r} is {columns * rows} cells, past {MAX_CELLS}",
            fix=f"a sheet is not that many pieces; cut it in batches under {MAX_CELLS}",
        )
    return columns, rows


def find_pieces(
    image: np.ndarray,
    *,
    grid: str | None,
    mode: str | None,
    chroma: str,
    tol: int,
    min_size: int,
    max_aspect: float,
) -> tuple[list[Rect], dict[str, Any]]:
    """The rectangles, and what was decided to get them.

    The order of the branches is the precedence: a stated grid wins over a detected one,
    because a caller who typed the layout knows something the image does not say.
    """
    height, width = image.shape[:2]

    if mode is None and (min_size or max_aspect):
        raise UsageError(
            "filter-without-mode",
            "--min-size and --max-aspect filter found pieces, and a grid's cells are given",
            fix="use them with --mode chroma or --mode islands",
        )

    if grid is not None:
        columns, rows = parse_grid(grid)
        try:
            rects = grid_rects(width, height, columns, rows)
        except ValueError as refused:
            raise UsageError("invalid-grid", str(refused), fix="use a grid that fits") from refused
        return rects, {"mode": "grid", "grid": {"columns": columns, "rows": rows}}

    if mode is None:
        # R1.2 — nobody said, so read it off the sheet.
        found = detect_grid(image)
        if found is None:
            raise SscError(
                "no-grid",
                "no regular layout could be read from this image",
                fix="give the layout with --grid COLSxROWS, or pick --mode chroma|islands",
            )
        # The measured cell, not one re-derived by dividing the width — see `rects_from`.
        return rects_from(found), {"mode": "detected", "grid": found.as_dict()}

    try:
        rects = (
            chroma_rects(image, parse_key(chroma), tol) if mode == "chroma" else island_rects(image)
        )
    except ValueError as refused:
        # The detector's own ceiling, which is about the image rather than about a flag —
        # a mask with a component per pixel is what any dithered alpha produces.
        raise SscError(
            "too-many-pieces",
            str(refused),
            fix="give the layout with --grid COLSxROWS, or clean the alpha up first",
        ) from refused

    return keep(rects, min_size=min_size, max_aspect=max_aspect), {"mode": mode}


def destination(asset: str | None, out: Path | None) -> None:
    """Exactly one of the two (R3.6).

    Naming the destination is what says whether this is recorded work or loose files. The
    first draft discovered it from whether a workspace was found, which answers only half
    the question — a command standing in a workspace still has to be told *which* asset.
    """
    if (asset is None) == (out is None):
        raise UsageError(
            "no-destination",
            "give exactly one of --asset <kind>/<key> and --out <path>",
            fix="--asset records into the workspace; --out writes plain files",
        )


def asset_dir_for(address: str) -> tuple[Path, meta.AssetMeta]:
    """The asset named by `<kind>/<key>`, which has to exist already."""
    parts = address.split("/")
    if len(parts) != 2:
        raise UsageError(
            "invalid-address", f"{address!r} is not an asset", fix="write it as <kind>/<key>"
        )
    workspace = ws.require()
    # The third route to an asset directory, and the first that resolves an address to an
    # asset that already exists *and then writes into it*. `listing` states the invariant
    # this would otherwise break: every route passes through here, because guarding one of
    # several is the same as guarding none.
    directory = under_assets(workspace, workspace.asset_dir(parts[0], parts[1]))
    if not meta.path_of(directory).is_file():
        raise UsageError(
            "no-asset",
            f"no asset {address} in this workspace",
            fix=f"ssc asset new {parts[1]} --kind {parts[0]}",
        )
    return directory, meta.load(directory)


def record_frames(
    directory: Path,
    record: meta.AssetMeta,
    pieces: list[np.ndarray],
    *,
    source: Path,
    params: dict[str, Any],
    dry_run: bool,
) -> list[str]:
    """Write the pieces into the asset's `frames/`, as one recorded stage (R3.1, R3.3).

    One record, not N: a stage is unique per asset, and N frames are one stage. `frames/` is
    also the only subdirectory an asset may have, which is `workspace-foundation`'s R2.5.
    """
    target = directory / FRAMES_STAGE
    written = [f"{FRAMES_STAGE}/{index + 1:03d}.png" for index in range(len(pieces))]
    if dry_run:
        return written

    if target.exists():
        raise SscError(
            "file-exists",
            f"{target} already exists, and nothing in ssc overwrites",
            fix=f"ssc clean, or remove {target} by hand",
        )
    for name, piece in zip(written, pieces, strict=True):
        write_one(directory / name, piece)

    meta.record(
        record,
        path=FRAMES_STAGE,
        stage=FRAMES_STAGE,
        file_class="derived",
        data=b"".join(encode(piece) for piece in pieces),
        produced_by=meta.Provenance(command="tool cut", params=params),
        derived_from=[source.name] if (directory / source.name).exists() else [],
    )
    meta.save(directory, record)
    return written


#: Shared by `cut` and `slice`, because they differ only in what they write.
def detection_options(command: Any) -> Any:
    for option in reversed(
        [
            click.option("--max-aspect", type=float, default=0.0, help="Drop pieces longer than."),
            click.option("--min-size", type=int, default=0, help="Drop pieces smaller than."),
            click.option("--tol", type=int, default=60, help="Chroma tolerance."),
            click.option("--chroma", default="green", help="Key colour for --mode chroma."),
            click.option(
                "--mode",
                type=click.Choice(["chroma", "islands"]),
                default=None,
                help="How to find the pieces. Omit to detect the grid.",
            ),
            click.option("--grid", default=None, help="State the layout as COLSxROWS."),
            click.option("--asset", default=None, help="Record into this <kind>/<key>."),
            click.option("--out", default=None, type=click.Path(path_type=Path), help="Or here."),
            click.option(
                "--in",
                "source",
                required=True,
                type=click.Path(path_type=Path),
                help="The sheet to take apart.",
            ),
        ]
    ):
        command = option(command)
    return command


@ssc_command("cut", help="Take a sheet apart into the frames of one animation.")
@detection_options
def cut(
    source: Path,
    out: Path | None,
    asset: str | None,
    grid: str | None,
    mode: str | None,
    chroma: str,
    tol: int,
    min_size: int,
    max_aspect: float,
    *,
    dry_run: bool,
) -> Result:
    destination(asset, out)
    image = load_image(source)
    rects, decided = find_pieces(
        image,
        grid=grid,
        mode=mode,
        chroma=chroma,
        tol=tol,
        min_size=min_size,
        max_aspect=max_aspect,
    )
    ordered = in_reading_order(rects)
    pieces = [crop(image, rect) for rect in ordered]

    if asset is not None:
        directory, record = asset_dir_for(asset)
        written = record_frames(
            directory,
            record,
            pieces,
            source=source,
            params={**decided, "from": source.name},
            dry_run=dry_run,
        )
    else:
        assert out is not None
        frames = [Frame(f"{index + 1:03d}.png", piece) for index, piece in enumerate(pieces)]
        written = [str(path) for path in write_frames(source, out, frames, dry_run=dry_run)]

    return Result(
        "tool cut",
        f"{len(pieces)} frame{'' if len(pieces) == 1 else 's'} from {source.name}",
        {
            **decided,
            "frames": len(pieces),
            "written": written,
            "pieces": [rect.as_dict() for rect in ordered],
        },
        dry_run=dry_run,
    )


@ssc_command("slice", help="Take a sheet apart into one asset per piece.")
@click.option("--kind", default=None, help="Kind for the assets --key names.")
@click.option("--key", default=None, help="Key prefix; each piece becomes <key>-NN.")
@detection_options
def slice_sheet(
    source: Path,
    out: Path | None,
    asset: str | None,
    grid: str | None,
    mode: str | None,
    chroma: str,
    tol: int,
    min_size: int,
    max_aspect: float,
    key: str | None,
    kind: str | None,
    *,
    dry_run: bool,
) -> Result:
    """N assets rather than N frames (R3.2). The same detector, bound differently."""
    if asset is not None:
        raise UsageError(
            "invalid-destination",
            "slice writes N assets, so it takes --kind and --key rather than --asset",
            fix="ssc tool slice --kind icon --key coin, or --out <path>",
        )
    if out is None and not (kind and key):
        raise UsageError(
            "no-destination",
            "give --kind and --key to record, or --out to write plain files",
            fix="--kind icon --key coin",
        )

    image = load_image(source)
    rects, decided = find_pieces(
        image,
        grid=grid,
        mode=mode,
        chroma=chroma,
        tol=tol,
        min_size=min_size,
        max_aspect=max_aspect,
    )
    ordered = in_reading_order(rects)
    pieces = [crop(image, rect) for rect in ordered]
    names = [f"{key or source.stem}-{index + 1:02d}" for index in range(len(pieces))]

    written: list[str] = []
    if out is not None:
        frames = [Frame(f"{name}.png", piece) for name, piece in zip(names, pieces, strict=True)]
        written = [str(path) for path in write_frames(source, out, frames, dry_run=dry_run)]
    else:
        assert kind is not None
        workspace = ws.require()
        for name, piece in zip(names, pieces, strict=True):
            directory = workspace.asset_dir(kind, name)
            if meta.path_of(directory).exists():
                raise UsageError(
                    "asset-exists",
                    f"{kind}/{name} already exists at {directory}",
                    fix="choose another --key, or work with the assets that are there",
                )
            written.append(f"{kind}/{name}")
            if dry_run:
                continue
            directory.mkdir(parents=True, exist_ok=True)
            record = meta.AssetMeta(key=name, kind=kind)
            data = encode(piece)
            filename = meta.filename(1, name, [], "png")
            write_one(directory / filename, piece)
            meta.record(
                record,
                path=filename,
                stage="cut",
                file_class="derived",
                data=data,
                produced_by=meta.Provenance(
                    command="tool slice", params={**decided, "from": source.name}
                ),
            )
            meta.save(directory, record)

    return Result(
        "tool slice",
        f"{len(pieces)} asset{'' if len(pieces) == 1 else 's'} from {source.name}",
        {**decided, "assets": len(pieces), "written": written},
        dry_run=dry_run,
    )


@ssc_command("curate", help="Report which frames say nothing new, and drop them when asked.")
@click.option("--drop", is_flag=True, help="Write only the frames that were kept.")
@click.option("--threshold", type=float, default=0.02, help="How different is different enough.")
@click.option("--out", default=None, type=click.Path(path_type=Path), help="Where --drop writes.")
@click.option(
    "--in",
    "source",
    required=True,
    type=click.Path(path_type=Path),
    help="A directory of frames.",
)
def curate(
    source: Path, out: Path | None, threshold: float, drop: bool, *, dry_run: bool
) -> Result:
    if not 0.0 <= threshold <= 1.0:
        raise UsageError(
            "invalid-threshold",
            f"--threshold {threshold} is outside 0..1",
            fix="it is a share of the frame's pixels, so 0.02 is two percent",
        )
    if drop and out is None:
        raise UsageError(
            "no-destination", "--drop needs somewhere to write", fix="add --out <directory>"
        )

    frames = read_frames(source)
    measured = differences([frame.image for frame in frames], threshold)
    redundant = [item.index for item in measured if item.redundant]

    written: list[str] = []
    if drop:
        assert out is not None
        surviving = [frames[item.index] for item in measured if not item.redundant]
        written = [str(path) for path in write_frames(source, out, surviving, dry_run=dry_run)]

    return Result(
        "tool curate",
        f"{len(frames)} frame{'' if len(frames) == 1 else 's'}, "
        f"{len(redundant)} redundant at {threshold}",
        {
            "frames": len(frames),
            "redundant": redundant,
            "kept": [item.index for item in measured if not item.redundant],
            "differences": [item.as_dict() for item in measured],
            "written": written,
        },
        dry_run=dry_run,
    )


@ssc_command("expand", help="Pad a canvas. Deterministic and free; gen expand invents.")
@click.option("--fill", default=None, help="Hex colour for the added area. Transparent if not.")
@click.option("--place", type=click.Choice(["centre", "bottom"]), default="centre")
@click.option("--by", type=int, default=0, help="Pixels to add on every side.")
@click.option("--to", "to_size", default=None, help="Target size as WxH.")
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--in", "source", required=True, type=click.Path(path_type=Path))
def expand_canvas(
    source: Path,
    out: Path,
    to_size: str | None,
    by: int,
    place: str,
    fill: str | None,
    *,
    dry_run: bool,
) -> Result:
    if (to_size is None) == (by == 0):
        raise UsageError(
            "no-target", "give exactly one of --to WxH and --by N", fix="--to 64x64, or --by 8"
        )
    if by < 0 or by > MAX_MARGIN:
        raise UsageError(
            "invalid-margin", f"--by {by} is outside 0..{MAX_MARGIN}", fix="pad by less"
        )
    target = parse_size(to_size, "size") if to_size else None

    frames = read_frames(source)
    try:
        grown = [
            Frame(
                frame.name,
                expand(
                    frame.image,
                    to=target,
                    by=by,
                    fill=parse_hex(fill) if fill else None,
                    place=place,
                ),
            )
            for frame in frames
        ]
    except ValueError as refused:
        raise UsageError("invalid-target", str(refused), fix="expand never crops") from refused

    written = write_frames(source, out, grown, dry_run=dry_run)
    height, width = grown[0].image.shape[:2]
    return Result(
        "tool expand",
        f"{len(grown)} frame{'' if len(grown) == 1 else 's'} on {width}x{height}",
        {
            "frames": len(grown),
            "size": {"width": width, "height": height},
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


@ssc_command("mirror", help="Flip horizontally — the free way to get East from West.")
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--in", "source", required=True, type=click.Path(path_type=Path))
def mirror(source: Path, out: Path, *, dry_run: bool) -> Result:
    frames = read_frames(source)
    flipped = [Frame(frame.name, flip(frame.image)) for frame in frames]
    written = write_frames(source, out, flipped, dry_run=dry_run)
    return Result(
        "tool mirror",
        f"{len(flipped)} frame{'' if len(flipped) == 1 else 's'} mirrored",
        {"frames": len(flipped), "mirrored": True, "written": [str(p) for p in written]},
        dry_run=dry_run,
    )


@ssc_command("align", help="Lock every frame of a set to one anchor.")
@click.option("--onion", "onion_out", default=None, type=click.Path(path_type=Path))
@click.option("--anchor", "mode", type=click.Choice(["feet", "bottom", "centre"]), default="feet")
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--in", "source", required=True, type=click.Path(path_type=Path))
def align(source: Path, out: Path, mode: str, onion_out: Path | None, *, dry_run: bool) -> Result:
    frames = read_frames(source)
    placed = plan_alignment([frame.image for frame in frames], mode)
    moved = [Frame(frame.name, image) for frame, image in zip(frames, placed.frames, strict=True)]
    written = write_frames(source, out, moved, dry_run=dry_run)
    if onion_out is not None:
        written += write_one(onion_out, onion(placed.frames), dry_run=dry_run)

    height, width = placed.frames[0].shape[:2]
    return Result(
        "tool align",
        f"{len(moved)} frame{'' if len(moved) == 1 else 's'} on {mode}, {width}x{height}",
        {
            "frames": len(moved),
            "anchor": {"x": placed.anchor[0], "y": placed.anchor[1]},
            "size": {"width": width, "height": height},
            "empty": placed.empty,
            "written": [str(path) for path in written],
        },
        dry_run=dry_run,
    )


@ssc_command("pack", help="Lay a set out as a sheet of equal cells.")
@click.option("--cell", default=None, help="Cell size as WxH. Defaults to the largest frame.")
@click.option("--cols", "columns", type=int, default=0, help="Columns. Defaults to one row.")
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--in", "source", required=True, type=click.Path(path_type=Path))
def pack_sheet(source: Path, out: Path, columns: int, cell: str | None, *, dry_run: bool) -> Result:
    frames = read_frames(source)
    if columns < 0 or columns > MAX_CELLS:
        raise UsageError("invalid-cols", f"--cols {columns} is out of range", fix="use 1 or more")
    try:
        sheet, layout = pack(
            [frame.image for frame in frames],
            columns=columns or len(frames),
            cell=parse_size(cell, "cell") if cell else None,
        )
    except ValueError as refused:
        raise UsageError("invalid-cell", str(refused), fix="use a cell that fits") from refused

    written = write_one(out, sheet, dry_run=dry_run)
    return Result(
        "tool pack",
        f"{len(frames)} frame{'' if len(frames) == 1 else 's'} as "
        f"{layout.columns}x{layout.rows} of {layout.cell[0]}x{layout.cell[1]}",
        {**layout.as_dict(), "frames": len(frames), "written": [str(p) for p in written]},
        dry_run=dry_run,
    )
