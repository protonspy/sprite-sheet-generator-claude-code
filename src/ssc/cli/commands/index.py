"""`ssc index` — turn a workspace into the `dist/` an engine loads.

The model is `cli/index.py` and the shapes are `cli/formats.py`. What is here is the command:
the flags, the writing, and the one report a caller reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import numpy as np

from ssc.cli import formats, kinds
from ssc.cli import index as model
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError, UsageError
from ssc.cli.frames import MAX_FILE_BYTES, decode_image, encode
from ssc.cli.main import ssc_command
from ssc.cli.names import check_name, check_relative_path
from ssc.cli.output import Result
from ssc.cli.preview import render
from ssc.cli.workspace import Workspace
from ssc.core import preview as core_preview

INDEX_NAME = "index.json"

#: An index of a large workspace is a few hundred kilobytes of rects. The ceiling is here for
#: the reason every other read in this project has one: the file survives hand-editing, and
#: `ssc preview` reads it back.
MAX_INDEX_BYTES = 1 << 24


def rendered(payload: dict[str, Any]) -> bytes:
    """The index as bytes, in the one spelling that makes a second run identical (R1.8).

    `sort_keys` and a fixed indent, and no trailing state of any kind — no timestamp, no
    version of `ssc`, no path from the machine it ran on. A field like that is what turns a
    reproducible build into a diff on every run.
    """
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def bound_dist(root: Path, relative: str) -> Directory:
    """Hold the directory a `dist/` path names, having proved it is where its name says.

    The same open-then-check-then-confirm as `listing.bound`, and here for the same reason:
    `check_relative_path` validates a *string* and cannot see that `dist/sheets/character`
    is a symlink — or, on Windows, a junction, which an unprivileged user can create. A
    directory planted under `dist/` ahead of time would otherwise redirect a write out of
    the workspace, or point a read at a file nobody meant to publish.

    `dist/` itself being a link is fine and deliberately allowed: it is the root both sides
    resolve against, so a workspace whose build output lives on another disk keeps working.
    """
    check_relative_path(relative, "a dist path")
    target = (root / relative).parent
    handle = Directory.open(target)
    try:
        if not handle.bindable:
            raise SscError(
                "no-file-identity",
                f"{target} is on a volume that reports no file identity, so ssc cannot "
                f"prove the directory it checked is the one it writes to",
                fix="keep the workspace on NTFS, or on any POSIX filesystem",
            )
        # Built from the unresolved path, because that is the address ssc composed. What it
        # resolves to is the question.
        expected = (root.resolve() / relative).parent
        resolved = target.resolve()
        if resolved != expected:
            raise SscError(
                "dist-displaced",
                f"{target} resolves to {resolved}, which is not {expected}",
                fix=f"remove the link at {target}, or delete {root} and run ssc index again",
            )
        handle.confirm(target)
    except BaseException:
        handle.close()
        raise
    return handle


def make_dist_dirs(root: Path, relative: str) -> None:
    """Create the directory chain a dist path needs, one segment at a time.

    `mkdir(parents=True)` was the first shape and it was the hole `bound_dist` could not
    cover, in two ways. It ran *before* the path was validated at all, so a `..` segment
    escaped as a directory that was really created before the refusal arrived — and on
    Windows it escapes even through a segment that does not exist, because `CreateDirectory`
    collapses `..` lexically rather than walking. And it created the whole chain inside a
    junction at, say, `dist/preview` before anything looked at where that resolved.

    So: validate the string first, then create one segment and check where it went before
    creating the next. A displaced segment is caught before anything is made inside it.
    """
    check_relative_path(relative, "a dist path")
    walked, expected = root, root.resolve()
    for name in Path(relative).parent.parts:
        walked, expected = walked / name, expected / name
        walked.mkdir(exist_ok=True)
        if walked.resolve() != expected:
            raise SscError(
                "dist-displaced",
                f"{walked} resolves to {walked.resolve()}, which is not {expected}",
                fix=f"remove the link at {walked}, or delete {root} and run ssc index again",
            )


def write_into(root: Path, relative: str, data: bytes) -> Path:
    """Write one file under `root`, replacing what is there.

    `replace` rather than `write_new`: `dist/` is rebuilt, and a build that refuses because
    its own last output is still there would need a `clean` before every run.
    """
    make_dist_dirs(root, relative)
    with bound_dist(root, relative) as held:
        return held.replace(Path(relative).name, data)


def write_dist(
    workspace: Workspace, built: model.Built, payload: dict[str, Any], *, dry_run: bool
) -> list[str]:
    """Every image, then the index that names them (R1.6, R1.7, R1.9).

    The images first and the index last, so a run interrupted half way leaves an index that
    still describes the last complete build rather than one naming files nobody wrote.
    """
    written = [*sorted(built.images), INDEX_NAME]
    if dry_run:
        return written

    workspace.dist.mkdir(parents=True, exist_ok=True)
    for relative in sorted(built.images):
        write_into(workspace.dist, relative, encode(built.images[relative]))
    write_into(workspace.dist, INDEX_NAME, rendered(payload))
    return written


def read_index(workspace: Workspace) -> dict[str, Any]:
    """The index on disk, or the refusal that names the command which writes one (R6.5)."""
    where = workspace.dist / INDEX_NAME
    if not where.is_file():
        raise UsageError(
            "no-index",
            f"there is no {where}",
            fix="ssc index",
        )
    with bound_dist(workspace.dist, INDEX_NAME) as held:
        raw = held.read(INDEX_NAME, max_bytes=MAX_INDEX_BYTES)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as broken:
        raise SscError(
            "index-invalid", f"{where} is not valid JSON: {broken}", fix="ssc index"
        ) from broken
    if not isinstance(payload, dict):
        raise SscError("index-invalid", f"{where} is not an index", fix="ssc index")
    if payload.get("format") != formats.DEFAULT_FORMAT:
        # The engine formats are for engines: they carry rects an engine needs and drop the
        # measurements ssc uses to cut a sheet back up. Rebuilding in `generic` is one
        # command, and guessing at a shape ssc did not write is not.
        raise UsageError(
            "index-not-generic",
            f"{where} is in the {payload.get('format')!r} format, which ssc cannot read back",
            fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
        )
    return payload


def whole(entry: dict[str, Any], *path: str, minimum: int = 1) -> int:
    """One number out of the index, proved to be a positive whole one.

    `index.json` is written by `ssc index` and read back by `ssc preview`, which makes it a
    file on disk between two processes — and every other such file in this project is
    validated on read rather than trusted. A missing key, a string, a float or a zero all
    reach arithmetic otherwise: `columns: 0` is a `ZeroDivisionError` and `frames:
    100000000000` is a list nobody can allocate.
    """
    node: Any = entry
    for name in path:
        if not isinstance(node, dict) or name not in node:
            raise SscError(
                "index-invalid",
                f"an index entry has no {'.'.join(path)}",
                fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
            )
        node = node[name]
    if isinstance(node, bool) or not isinstance(node, int) or node < minimum:
        raise SscError(
            "index-invalid",
            f"an index entry gives {'.'.join(path)} as {node!r}, "
            f"not a whole number of at least {minimum}",
            fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
        )
    return node


def cut_sheet(image: np.ndarray, entry: dict[str, Any]) -> list[np.ndarray]:
    """A sheet back into its frames, using the grid the index declares.

    Reading the picture rather than the asset is deliberate: `ssc preview` exists to show
    what an engine will load, so it looks at the same file and believes the same numbers. A
    preview built from `assets/` instead would still be right when the index was wrong.

    "Believes" is the part that needs a guard. The grid is checked against the image before
    a single frame is cut, which bounds every number at once: a frame count no picture could
    hold cannot survive a grid that has to fit inside the pixels that are actually there.
    """
    width, height = whole(entry, "cell", "width"), whole(entry, "cell", "height")
    columns, rows, frames = whole(entry, "columns"), whole(entry, "rows"), whole(entry, "frames")

    tall, wide = image.shape[:2]
    if columns * width > wide or rows * height > tall:
        raise SscError(
            "index-invalid",
            f"the index declares a {columns}x{rows} grid of {width}x{height} cells, "
            f"which does not fit the {wide}x{tall} image beside it",
            fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
        )
    if frames > columns * rows:
        raise SscError(
            "index-invalid",
            f"the index declares {frames} frames in a {columns}x{rows} grid",
            fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
        )

    cut = []
    for number in range(frames):
        row, column = divmod(number, columns)
        top, left = row * height, column * width
        cut.append(image[top : top + height, left : left + width])
    return cut


def crop(image: np.ndarray, rect: dict[str, Any]) -> np.ndarray:
    """One entry out of an atlas or a tileset, refusing a rect the image does not hold.

    A slice past the end of an array does not raise in numpy — it silently returns fewer
    pixels, or none — so an out-of-range rect would preview an empty image rather than say
    anything. The check is what turns that into an answer.
    """
    width, height = whole(rect, "width"), whole(rect, "height")
    top, left = whole(rect, "y", minimum=0), whole(rect, "x", minimum=0)
    tall, wide = image.shape[:2]
    if top + height > tall or left + width > wide:
        raise SscError(
            "index-invalid",
            f"the index places a {width}x{height} entry at {left},{top} on a {wide}x{tall} image",
            fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
        )
    return image[top : top + height, left : left + width]


@dataclass(frozen=True)
class Subject:
    """What `ssc preview` found in the index, and what it can do with it."""

    kind: str
    key: str
    frames: list[np.ndarray]
    fps: int
    mode: str
    sections: dict[str, tuple[int, int]]


def playback_mode(playback: dict[str, Any]) -> str:
    """The mode an index entry declares, held to the three `core.preview` knows.

    `order` raises a plain `ValueError` for anything else, which `cli/main.py` would report
    as an internal error — a bug in ssc rather than what it is, a file saying something ssc
    did not write.
    """
    mode = playback.get("mode")
    if mode not in core_preview.MODES:
        raise SscError(
            "index-invalid",
            f"the index gives a playback mode of {mode!r}",
            fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
        )
    return str(mode)


def read_sections(playback: dict[str, Any]) -> dict[str, tuple[int, int]]:
    """The sections an index entry declares, each proved to be a name and a pair of numbers.

    **The name especially.** `--section windup` becomes part of the filename `ssc preview`
    writes, so a name out of the index is a path segment out of the index — and `check_name`
    is what already refuses a separator or a `..` in every other name this project turns into
    one. The ends are checked here for the reason every other number out of this file is:
    `order` compares them, and a string compared to an int is a traceback rather than an
    answer about a file.
    """
    read: dict[str, tuple[int, int]] = {}
    for section in playback.get("sections", []):
        if not isinstance(section, dict) or "name" not in section:
            raise SscError(
                "index-invalid",
                "an index entry declares a section with no name",
                fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
            )
        try:
            name = check_name(str(section["name"]), "a section")
        except UsageError as refused:
            raise SscError(
                "index-invalid",
                f"the index declares a section named {section['name']!r}: {refused.message}",
                fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
            ) from refused
        first, last = whole(section, "first", minimum=0), whole(section, "last", minimum=0)
        if last < first:
            # Each end being a number is not the same as the pair being a range. Left
            # unchecked, this reached `order`'s own `ValueError` and came back as
            # `internal-error` — "this is a bug in ssc" for a file somebody edited by hand.
            raise SscError(
                "index-invalid",
                f"the index declares section {name!r} running from {first} to {last}",
                fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
            )
        read[name] = (first, last)
    return read


def selects(wanted: str, kind: str) -> bool:
    """Whether the kind part of an address picks out this kind.

    A function rather than `wanted in ("", kind)` at three call sites, because that spelling
    is indistinguishable — to a reader and to `adr:0008`'s grep alike — from branching on a
    particular kind's name. Nothing here knows what any kind is called; the empty string is
    the caller having typed a bare key.
    """
    return not wanted or wanted == kind


def find(workspace: Workspace, payload: dict[str, Any], address: str) -> Subject:
    """The asset the caller named, wherever in the index it landed.

    A key alone is accepted, like `image show`, and an ambiguous one is refused with the
    kinds it matched rather than resolved by guessing.
    """
    wanted_kind, _, wanted_key = address.rpartition("/")
    found: list[Subject] = []

    for entry in payload.get("sheets", []):
        if entry["key"] == wanted_key and selects(wanted_kind, entry["kind"]):
            image = read_image(workspace.dist, entry["image"])
            found.append(
                Subject(
                    kind=entry["kind"],
                    key=entry["key"],
                    frames=cut_sheet(image, entry),
                    fps=whole(entry["playback"], "fps"),
                    mode=playback_mode(entry["playback"]),
                    sections=read_sections(entry["playback"]),
                )
            )

    for atlas in payload.get("atlases", []):
        if not selects(wanted_kind, atlas["kind"]):
            continue
        for item in atlas["entries"]:
            if item["id"] == wanted_key:
                image = read_image(workspace.dist, atlas["image"])
                found.append(
                    Subject(atlas["kind"], item["id"], [crop(image, item["rect"])], 1, "loop", {})
                )

    for tileset in payload.get("tilesets", []):
        if not selects(wanted_kind, tileset["kind"]):
            continue
        for tile in tileset["tiles"]:
            if tile["id"] == wanted_key:
                image = read_image(workspace.dist, tileset["image"])
                width, height = whole(tileset, "tile", "width"), whole(tileset, "tile", "height")
                rect = {
                    "x": whole(tile, "column", minimum=0) * width,
                    "y": whole(tile, "row", minimum=0) * height,
                    "width": width,
                    "height": height,
                }
                found.append(
                    Subject(tileset["kind"], tile["id"], [crop(image, rect)], 1, "loop", {})
                )

    if not found:
        raise UsageError(
            "not-indexed",
            f"the index carries nothing called {address!r}",
            fix="ssc index, or check the key with ssc image list",
        )
    if len(found) > 1:
        kinds_found = ", ".join(sorted(one.kind for one in found))
        raise UsageError(
            "ambiguous-key",
            f"{address!r} is indexed under more than one kind: {kinds_found}",
            fix=f"name the kind, for example {sorted(one.kind for one in found)[0]}/{wanted_key}",
        )
    return found[0]


def read_image(root: Path, relative: str) -> np.ndarray:
    """One image out of `dist/`, through a binding and under the same ceiling as any other.

    The path comes out of `index.json`, which is a file on disk that survives hand-editing,
    so it is treated as input: bound like every other read of a file this project did not
    just write, and bounded by `MAX_FILE_BYTES` like every other decode.
    """
    with bound_dist(root, relative) as held:
        return decode_image(held.read(Path(relative).name, max_bytes=MAX_FILE_BYTES), relative)


@ssc_command(
    "preview",
    help="Render what the index declares — a GIF, a contact sheet, or a tile 2x2.",
    needs_workspace=True,
)
@click.option("--section", default=None, help="Render only this named section.")
@click.option("--contact", "as_contact", is_flag=True, help="A labelled contact sheet instead.")
@click.argument("address")
def preview(
    address: str,
    as_contact: bool,
    section: str | None,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """R6.

    The three outputs are not three flags: a tile is previewed tiled because seeing its seams
    is the only question a single tile raises, and that is read off the kind's profile rather
    than off its name.
    """
    subject = find(workspace, read_index(workspace), address)
    profile = kinds.resolve(subject.kind, workspace).profile

    span: tuple[int, int] | None = None
    if section is not None:
        if section not in subject.sections:
            known = ", ".join(sorted(subject.sections)) or "none"
            raise UsageError(
                "unknown-section",
                f"{subject.kind}/{subject.key} declares no section {section!r}; it has: {known}",
                fix="add it under playback.sections in that asset's asset.yaml",
            )
        span = subject.sections[section]
        if span[1] >= len(subject.frames):
            # `cli/index.py` refuses this when the index is *written*, against the frames it
            # measured. Refused again here, against the frames the sheet actually holds,
            # because between the two there is a file somebody may have edited.
            raise SscError(
                "index-invalid",
                f"the index declares section {section!r} running to frame {span[1]}, "
                f"and the sheet holds {len(subject.frames)}",
                fix=f"ssc index --format {formats.DEFAULT_FORMAT}",
            )

    named = f"{subject.key}{'-' + section if section else ''}"
    if "seam" in profile.checks:
        data, suffix = encode(core_preview.tiled(subject.frames[0])), "png"
    else:
        # The index path renders through the same renderer `tool preview` uses: one GIF or
        # contact encoder, shared, so the index path grows no second one (engine-index R6.7).
        data, suffix = render(
            subject.frames,
            fps=subject.fps,
            mode=subject.mode,
            section=span,
            contact=as_contact,
        )

    relative = f"preview/{subject.kind}/{named}.{suffix}"
    if not dry_run:
        write_into(workspace.dist, relative, data)

    return Result(
        "preview",
        f"{subject.kind}/{subject.key} as {relative}",
        {
            "asset": f"{subject.kind}/{subject.key}",
            "frames": len(subject.frames),
            "fps": subject.fps,
            "mode": subject.mode,
            "section": section,
            "written": [relative],
        },
        dry_run=dry_run,
    )


@ssc_command(
    "index",
    help="Build dist/ — the sheets, atlases and tilesets an engine loads.",
    needs_workspace=True,
)
@click.option("--extrude", type=int, default=0, help="Repeat each atlas entry's border outwards.")
@click.option(
    "--padding", type=int, default=0, help="Pixels between atlas entries and at the edge."
)
@click.option("--stage", default=None, help="Publish this stage. Defaults to the last recorded.")
@click.option(
    "--format",
    "name",
    default=formats.DEFAULT_FORMAT,
    help=f"One of: {', '.join(formats.FORMATS)}.",
)
def index(
    name: str,
    stage: str | None,
    padding: int,
    extrude: int,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """R1, R3, R5.

    The whole index does not travel in the result: it is on disk, it is the point of the
    command, and a caller that wants it reads the file. What comes back is what was written
    and what was left out, which is what a caller has to act on.
    """
    # Refused before any packing: a format nobody emits should cost a typo's worth of time,
    # not a whole build's (R5.6).
    formats.emit(model.Built(), name=name)

    groups, skipped = model.gather(workspace, stage=stage)
    built = model.build(groups, skipped, padding=padding, extrude=extrude)
    payload = formats.emit(built, name=name)
    written = write_dist(workspace, built, payload, dry_run=dry_run)

    covered = len(built.sheets) + len(built.atlases) + len(built.tilesets)
    return Result(
        "index",
        f"{covered} artefact{'' if covered == 1 else 's'} in {name}"
        + (f", {len(built.skipped)} asset skipped" if len(built.skipped) == 1 else "")
        + (f", {len(built.skipped)} assets skipped" if len(built.skipped) > 1 else ""),
        {
            "format": name,
            "sheets": [sheet.id for sheet in built.sheets],
            "atlases": [atlas.id for atlas in built.atlases],
            "tilesets": [tileset.id for tileset in built.tilesets],
            "skipped": [one.as_dict() for one in built.skipped],
            "written": written,
        },
        dry_run=dry_run,
    )
