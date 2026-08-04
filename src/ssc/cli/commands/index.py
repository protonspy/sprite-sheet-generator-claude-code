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
from ssc.cli.names import check_relative_path
from ssc.cli.output import Result
from ssc.cli.preview import animated_gif
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


def write_into(root: Path, relative: str, data: bytes) -> Path:
    """Write one file under `root`, replacing what is there.

    `replace` rather than `write_new`: `dist/` is rebuilt, and a build that refuses because
    its own last output is still there would need a `clean` before every run. The path is
    checked for escape even though every one of them is composed from names `check_name`
    already accepted — the composition is the part that could go wrong later.
    """
    check_relative_path(relative, "a dist path")
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with Directory.open(target.parent) as held:
        return held.replace(target.name, data)


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
    with Directory.open(where.parent) as held:
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


def cut_sheet(image: np.ndarray, entry: dict[str, Any]) -> list[np.ndarray]:
    """A sheet back into its frames, using the grid the index declares.

    Reading the picture rather than the asset is deliberate: `ssc preview` exists to show
    what an engine will load, so it looks at the same file and believes the same numbers. A
    preview built from `assets/` instead would still be right when the index was wrong.
    """
    width, height = entry["cell"]["width"], entry["cell"]["height"]
    frames = []
    for number in range(entry["frames"]):
        row, column = divmod(number, entry["columns"])
        top, left = row * height, column * width
        frames.append(image[top : top + height, left : left + width])
    return frames


def crop(image: np.ndarray, rect: dict[str, int]) -> np.ndarray:
    return image[rect["y"] : rect["y"] + rect["height"], rect["x"] : rect["x"] + rect["width"]]


@dataclass(frozen=True)
class Subject:
    """What `ssc preview` found in the index, and what it can do with it."""

    kind: str
    key: str
    frames: list[np.ndarray]
    fps: int
    mode: str
    sections: dict[str, tuple[int, int]]


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
                    fps=entry["playback"]["fps"],
                    mode=entry["playback"]["mode"],
                    sections={
                        section["name"]: (section["first"], section["last"])
                        for section in entry["playback"]["sections"]
                    },
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
                rect = {
                    "x": tile["column"] * tileset["tile"]["width"],
                    "y": tile["row"] * tileset["tile"]["height"],
                    "width": tileset["tile"]["width"],
                    "height": tileset["tile"]["height"],
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
    """One image out of `dist/`, through a binding and under the same ceiling as any other."""
    check_relative_path(relative, "a dist path")
    target = root / relative
    with Directory.open(target.parent) as held:
        return decode_image(held.read(target.name, max_bytes=MAX_FILE_BYTES), relative)


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

    named = f"{subject.key}{'-' + section if section else ''}"
    if "seam" in profile.checks:
        data, suffix = encode(core_preview.tiled(subject.frames[0])), "png"
    elif as_contact:
        ordered = [
            subject.frames[number]
            for number in core_preview.order(len(subject.frames), subject.mode, span)
        ]
        data, suffix = encode(core_preview.contact(ordered)), "png"
    else:
        ordered = [
            subject.frames[number]
            for number in core_preview.order(len(subject.frames), subject.mode, span)
        ]
        data, suffix = animated_gif(ordered, subject.fps), "gif"

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
