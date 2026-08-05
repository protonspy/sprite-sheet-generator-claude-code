"""The index model — what an engine is told about a workspace.

`ssc index` reads `assets/`, packs what each kind's profile says it packs, and writes
`dist/`. This module is the model that sits between those two: it knows about assets, kinds
and sidecars, and nothing about any particular engine. `cli/formats.py` renames its fields
for Pixi, Phaser and Godot without reading a workspace or an image.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ssc.cli import kinds, meta
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError
from ssc.cli.kinds import Profile
from ssc.cli.listing import asset_dirs, bound, chain_order, frames_of, media_of
from ssc.cli.meta import AssetMeta, FileRecord
from ssc.cli.sidecar import AuthoredFrame, Box, Playback, Section, frame_rate
from ssc.cli.sidecar import load as load_sidecar
from ssc.cli.workspace import Workspace
from ssc.core.assemble import pack
from ssc.core.atlas import Entry, Rect, anchors_of, draw, place
from ssc.core.contact import grid_for
from ssc.core.ninepatch import guides_for

#: The three things an engine loads. Which one a kind produces is read off its profile and
#: never off its name — see `adr:0008-a-kind-is-a-profile-not-an-enum`.
Artefact = Literal["sheet", "atlas", "tileset"]


def artefact_of(profile: Profile) -> Artefact:
    """What this kind gives an engine (R1.2).

    An animating kind is a sheet of equal cells per asset, because an animation is addressed
    by frame number. Everything else is one file per *kind* rather than per asset: `bin`
    packs by size and gives a rect per entry, `grid` gives equal cells with an id per entry,
    which is a tileset.
    """
    if profile.animates:
        return "sheet"
    return "atlas" if profile.atlas_layout == "bin" else "tileset"


def publishable(record: FileRecord) -> bool:
    """Whether a recorded file is something an engine could be handed.

    An image by its extension, or a frame set — which is recorded as a directory and so has
    no extension at all. `media_of` answers `None` for both a frame set and a sidecar, which
    is why this is a question of its own rather than a call to it.
    """
    return media_of(record.path) == "image" or Path(record.path).suffix == ""


@dataclass(frozen=True)
class Skipped:
    """An asset the index could not carry, and why (R1.5).

    Reported rather than dropped, and rather than failing the run: a workspace mid-pipeline
    legitimately holds assets with nothing to publish yet, and an index that silently omits
    them is one where a missing sprite has no explanation anywhere.
    """

    kind: str
    key: str
    why: str

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "key": self.key, "why": self.why}


@dataclass(frozen=True)
class Published:
    """One asset's pixels, and what was authored about them."""

    kind: str
    key: str
    stage: str
    frames: list[np.ndarray]
    playback: Playback = field(default_factory=Playback)
    #: The sidecar's `frames:` block — `None` where the author wrote none.
    authored: tuple[AuthoredFrame, ...] | None = None


@dataclass(frozen=True)
class Group:
    """Every asset of one kind, and what that kind produces."""

    kind: str
    profile: Profile
    artefact: Artefact
    assets: list[Published]


def gather(workspace: Workspace, *, stage: str | None = None) -> tuple[list[Group], list[Skipped]]:
    """Every asset in the workspace, grouped by kind (R1.1, R1.2, R1.3, R1.4, R1.5).

    The frames are read here and held: packing needs them, and the alternative — reading
    each asset twice, once to measure and once to draw — costs two passes over every file to
    save memory that `MAX_SET_PIXELS` already bounds per asset.

    Order comes from `asset_dirs`, which sorts by kind then key, and the groups are sorted by
    kind. Nothing downstream re-sorts, so this is where R1.8's byte-identical second run is
    decided.
    """
    # Resolved once, and deliberately outside the per-asset guard below: a malformed
    # `kinds:` in `ssc.yaml` is a broken workspace, not forty broken assets, and reporting it
    # as forty identical skips would bury the one thing that needs fixing.
    available = kinds.every(workspace)

    by_kind: dict[str, list[Published]] = {}
    profiles: dict[str, Profile] = {}
    skipped: list[Skipped] = []

    for directory in asset_dirs(workspace):
        with bound(workspace, directory) as held:
            record = meta.load(held)
            try:
                published = _publish(held, record, stage)
            except SscError as refused:
                # One asset that cannot be read does not cost the other forty their index.
                skipped.append(Skipped(record.kind, record.key, refused.message))
                continue
            if published is None:
                asked = f" at stage {stage!r}" if stage else ""
                skipped.append(Skipped(record.kind, record.key, f"records no image{asked}"))
                continue
        resolved = available.get(record.kind)
        if resolved is None:
            # An asset directory named after a kind nobody declared — made by hand, or left
            # behind by a `kinds:` entry somebody removed.
            skipped.append(
                Skipped(record.kind, record.key, f"no kind {record.kind!r} in this workspace")
            )
            continue
        if published.authored is not None and not resolved.profile.animates:
            # Only a sheet carries per-frame data. Skipped rather than dropped: a frames
            # block ssc silently ignored is a hitbox the author believes is in effect.
            skipped.append(
                Skipped(
                    record.kind,
                    record.key,
                    f"authors a frames block, and {record.kind} does not animate",
                )
            )
            continue
        profiles[record.kind] = resolved.profile
        by_kind.setdefault(record.kind, []).append(published)

    groups = [
        Group(
            kind=kind,
            profile=profiles[kind],
            artefact=artefact_of(profiles[kind]),
            assets=assets,
        )
        for kind, assets in sorted(by_kind.items())
    ]
    return groups, skipped


def _publish(held: Directory, record: AssetMeta, stage: str | None) -> Published | None:
    """The one stage of this asset an engine gets, with its frames and its sidecar."""
    candidates = [entry for entry in sorted(record.files, key=chain_order) if publishable(entry)]
    if stage is None:
        # The last of the chain, which is the same rule `image show` uses with no `--stage`:
        # the end of the chain is what the work was heading towards.
        chosen = candidates[-1] if candidates else None
    else:
        chosen = next((entry for entry in candidates if entry.stage == stage), None)
    if chosen is None:
        return None
    authored = load_sidecar(held)
    return Published(
        kind=record.kind,
        key=record.key,
        stage=chosen.stage,
        frames=frames_of(held, record, chosen.stage),
        playback=authored.playback,
        authored=authored.frames,
    )


@dataclass(frozen=True)
class FrameDetail:
    """One frame's per-frame data: measured bounds, and what a person authored.

    `bounds` is derived from the pixels and present with no authoring at all; the boxes and
    markers are carried from the sidecar and never invented — `ssc` moves damage, it does
    not deal any.
    """

    bounds: Box | None = None
    authored: AuthoredFrame = field(default_factory=AuthoredFrame)

    def as_dict(self) -> dict[str, Any]:
        return {
            "bounds": None if self.bounds is None else self.bounds.as_dict(),
            **self.authored.as_dict(),
        }


@dataclass(frozen=True)
class SheetEntry:
    """One animation, as an engine addresses it: equal cells, by frame number (R2.1, R2.3)."""

    kind: str
    key: str
    image: str
    cell: tuple[int, int]
    columns: int
    rows: int
    frames: int
    anchor: tuple[int, int]
    aligned: bool
    fps: int
    mode: str
    sections: tuple[Section, ...] = ()
    #: One entry per frame: derived bounds, and the sidecar's count-checked authored block.
    per_frame: tuple[FrameDetail, ...] = ()

    @property
    def id(self) -> str:
        return f"{self.kind}/{self.key}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "image": self.image,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "columns": self.columns,
            "rows": self.rows,
            "frames": self.frames,
            # In pixels within the cell, not as a fraction: the fraction is what Pixi and
            # Phaser want and it is derived at that boundary, because a rounded fraction
            # cannot be turned back into the pixel it came from.
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
            "aligned": self.aligned,
            "playback": {
                "fps": self.fps,
                "mode": self.mode,
                "sections": [section.as_dict() for section in self.sections],
            },
            # Additive under adr:0010 — a loader that predates it ignores the key, so
            # `schema` stays where it is.
            "per_frame": [detail.as_dict() for detail in self.per_frame],
        }


def build_sheet(published: Published, profile: Profile) -> tuple[SheetEntry, np.ndarray]:
    """Pack one animation and describe it (R2.1, R2.2, R2.3, R2.4).

    Near-square rather than one row: the grid shape means nothing to an engine addressing by
    frame number, and a sixty-frame animation in one row is a canvas four times wider than
    `MAX_CANVAS` allows before it is anything else.

    The cell comes from the kind's profile, which is where a project decides it. A frame
    larger than the cell is a disagreement between the art and the profile, and it is raised
    rather than papered over by widening the cell: an engine reading a cell size that is not
    the one the project declared cuts every sprite in the wrong place.
    """
    frames = published.frames
    # Only the columns are ours to choose: `pack` derives the rows from them and reports
    # both, and taking its answer is what keeps the index and the pixels agreeing.
    columns, _ = grid_for(len(frames), 0)
    widest = max(frame.shape[1] for frame in frames)
    tallest = max(frame.shape[0] for frame in frames)
    if widest > profile.cell[0] or tallest > profile.cell[1]:
        raise SscError(
            "frame-larger-than-cell",
            f"{published.kind}/{published.key} has a {widest}x{tallest} frame and "
            f"{profile.name} declares a {profile.cell[0]}x{profile.cell[1]} cell",
            fix=f"ssc tool expand, or declare a larger cell for {profile.name} in ssc.yaml",
        )

    pixels, layout = pack(frames, columns=columns, cell=profile.cell, mode=profile.anchor)
    entry = SheetEntry(
        kind=published.kind,
        key=published.key,
        image=f"sheets/{published.kind}/{published.key}.png",
        cell=layout.cell,
        columns=layout.columns,
        rows=layout.rows,
        frames=len(frames),
        anchor=layout.anchor,
        # R2.2 — reported, never omitted. A sheet whose frames were never aligned still has
        # an anchor; what it does not have is one that every frame agrees on, and an engine
        # told nothing would re-centre the sprite and undo what `align` exists to do.
        aligned=layout.aligned,
        fps=frame_rate(published.playback, profile.fps),
        mode=published.playback.mode,
        sections=resolve_sections(
            published.playback.sections,
            frames=len(frames),
            where=f"{published.kind}/{published.key}",
        ),
        per_frame=per_frame_of(published),
    )
    return entry, pixels


def per_frame_of(published: Published) -> tuple[FrameDetail, ...]:
    """Every frame's detail: measured bounds always, authored values where they exist."""
    authored = resolve_authored(
        published.authored,
        frames=len(published.frames),
        where=f"{published.kind}/{published.key}",
    )
    return tuple(
        FrameDetail(
            bounds=bounds_of(frame),
            authored=authored[number] if authored is not None else AuthoredFrame(),
        )
        for number, frame in enumerate(published.frames)
    )


def entry_ids(published: Published) -> list[str]:
    """What each of an asset's images is called inside an atlas or a tileset.

    A single-image asset is its key, which is what somebody typing `potion` expects to find.
    An asset publishing a set gets one id per frame, numbered, because two entries cannot
    share an id and dropping all but the first would silently lose art.
    """
    if len(published.frames) == 1:
        return [published.key]
    return [f"{published.key}_{number:04d}" for number in range(len(published.frames))]


def borders_for(profile: Profile, image: np.ndarray) -> tuple[int, int, int, int] | None:
    """The four stretch borders, for a kind that declares the `nineslice` check (R3.3).

    Derived rather than authored: `core.ninepatch` returns one pixel-art pixel a side, which
    is the smallest guide that can be right and the one a caller adjusts from. Read off the
    profile's `checks` rather than off the kind's name, like everything else.
    """
    if "nineslice" not in profile.checks:
        return None
    return guides_for(image)


@dataclass(frozen=True)
class AtlasItem:
    """One image inside an atlas: where it is, and where its anchor is within it."""

    id: str
    rect: Rect
    anchor: tuple[int, int]
    borders: tuple[int, int, int, int] | None = None

    def as_dict(self) -> dict[str, Any]:
        emitted: dict[str, Any] = {
            "id": self.id,
            "rect": self.rect.as_dict(),
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
        }
        if self.borders is not None:
            left, right, top, bottom = self.borders
            emitted["borders"] = {"left": left, "right": right, "top": top, "bottom": bottom}
        return emitted


@dataclass(frozen=True)
class AtlasEntry:
    """Every asset of one `bin` kind, packed by size (R3.1)."""

    kind: str
    image: str
    width: int
    height: int
    padding: int
    extrude: int
    items: tuple[AtlasItem, ...]

    @property
    def id(self) -> str:
        return self.kind

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "image": self.image,
            "width": self.width,
            "height": self.height,
            "padding": self.padding,
            "extrude": self.extrude,
            "entries": [item.as_dict() for item in self.items],
        }


def build_atlas(
    group: Group, *, padding: int = 0, extrude: int = 0
) -> tuple[AtlasEntry, np.ndarray]:
    """Pack a whole kind into one atlas and describe it (R3.1).

    One file per kind rather than per asset, because that is what an atlas is for: forty
    icons in one texture is one bind instead of forty. The rects come from `core.atlas`,
    which is also what `tool pack --atlas` calls — two callers of one packer.
    """
    images: dict[str, np.ndarray] = {}
    for published in group.assets:
        for name, image in zip(entry_ids(published), published.frames, strict=True):
            images[name] = image

    placement = place(
        [Entry(id=name, size=(image.shape[1], image.shape[0])) for name, image in images.items()],
        padding=padding,
        extrude=extrude,
        anchors=anchors_of(images, group.profile.anchor),
    )
    entry = AtlasEntry(
        kind=group.kind,
        image=f"atlases/{group.kind}.png",
        width=placement.width,
        height=placement.height,
        padding=placement.padding,
        extrude=placement.extrude,
        items=tuple(
            AtlasItem(
                id=placed.id,
                rect=placed.rect,
                anchor=placed.anchor,
                borders=borders_for(group.profile, images[placed.id]),
            )
            for placed in placement.entries
        ),
    )
    return entry, draw(placement, images)


@dataclass(frozen=True)
class TileItem:
    """One tile, addressed by id and found by column and row."""

    id: str
    column: int
    row: int

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "column": self.column, "row": self.row}


@dataclass(frozen=True)
class TilesetEntry:
    """Every asset of one `grid` kind, in equal cells (R3.2)."""

    kind: str
    image: str
    tile: tuple[int, int]
    columns: int
    rows: int
    tiles: tuple[TileItem, ...]

    @property
    def id(self) -> str:
        return self.kind

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "image": self.image,
            "tile": {"width": self.tile[0], "height": self.tile[1]},
            "columns": self.columns,
            "rows": self.rows,
            "tiles": [tile.as_dict() for tile in self.tiles],
        }


def build_tileset(group: Group) -> tuple[TilesetEntry, np.ndarray]:
    """Lay a whole kind out as equal cells and describe it (R3.2).

    Every tile is exactly the kind's cell, and one that is not is refused rather than padded
    into place. Padding a smaller tile produces a set of ids that all resolve but whose art
    sits at a different offset inside each cell — which is `tool pack`'s `tiles-differ`
    argument, arrived at from the other direction.
    """
    named: list[tuple[str, np.ndarray]] = []
    for published in group.assets:
        named += list(zip(entry_ids(published), published.frames, strict=True))

    cell = group.profile.cell
    wrong = [
        f"{name} is {image.shape[1]}x{image.shape[0]}"
        for name, image in named
        if (image.shape[1], image.shape[0]) != cell
    ]
    if wrong:
        raise SscError(
            "tile-not-the-cell",
            f"{group.kind} declares a {cell[0]}x{cell[1]} tile; {', '.join(wrong)}",
            fix=f"ssc tool expand to {cell[0]}x{cell[1]}, or declare another cell for "
            f"{group.kind} in ssc.yaml",
        )

    columns, _ = grid_for(len(named), 0)
    pixels, layout = pack(
        [image for _, image in named], columns=columns, cell=cell, mode=group.profile.anchor
    )
    entry = TilesetEntry(
        kind=group.kind,
        image=f"tilesets/{group.kind}.png",
        tile=layout.cell,
        columns=layout.columns,
        rows=layout.rows,
        tiles=tuple(
            TileItem(id=name, column=number % layout.columns, row=number // layout.columns)
            for number, (name, _) in enumerate(named)
        ),
    )
    return entry, pixels


@dataclass(frozen=True)
class Built:
    """Everything one `ssc index` run has to say, and every file it has to write.

    The pixels travel beside the entries rather than inside them so that a format emitter
    cannot reach an image: `cli/formats.py` renames fields, and a renderer in it would be a
    second place where the bytes and the numbers can disagree.
    """

    sheets: list[SheetEntry] = field(default_factory=list)
    atlases: list[AtlasEntry] = field(default_factory=list)
    tilesets: list[TilesetEntry] = field(default_factory=list)
    images: dict[str, np.ndarray] = field(default_factory=dict)
    skipped: list[Skipped] = field(default_factory=list)


def build(
    groups: list[Group], skipped: list[Skipped], *, padding: int = 0, extrude: int = 0
) -> Built:
    """Pack every group, keeping what fails out of the way of what does not.

    A sheet that cannot be built costs its own asset; an atlas or a tileset that cannot be
    built costs its whole kind, because it is one file for all of them. Both are reported as
    skips rather than raised: an index missing one kind and saying why beats no index.
    """
    built = Built(skipped=list(skipped))

    for group in groups:
        if group.artefact == "sheet":
            for published in group.assets:
                try:
                    entry, pixels = build_sheet(published, group.profile)
                except SscError as refused:
                    built.skipped.append(Skipped(published.kind, published.key, refused.message))
                    continue
                built.sheets.append(entry)
                built.images[entry.image] = pixels
            continue

        try:
            if group.artefact == "atlas":
                atlas, pixels = build_atlas(group, padding=padding, extrude=extrude)
                built.atlases.append(atlas)
                built.images[atlas.image] = pixels
            else:
                tileset, pixels = build_tileset(group)
                built.tilesets.append(tileset)
                built.images[tileset.image] = pixels
        except (SscError, ValueError) as refused:
            # `ValueError` too: `core.atlas` and `core.assemble` raise it for a canvas that
            # is too large or an entry that does not fit, and those are the same kind of
            # answer — this kind cannot be packed as asked.
            message = refused.message if isinstance(refused, SscError) else str(refused)
            built.skipped.extend(
                Skipped(published.kind, published.key, message) for published in group.assets
            )

    return built


def bounds_of(frame: np.ndarray) -> Box | None:
    """The tight box around a frame's opaque pixels — derived, with no authoring at all.

    Geometry, not meaning: where the art is, which is measurable, as opposed to what deals
    or receives, which never is. `None` for a fully transparent frame, because a zero-size
    box has a position and an empty frame does not have one of those either.
    """
    alpha = frame[..., 3]
    rows = np.flatnonzero(alpha.any(axis=1))
    columns = np.flatnonzero(alpha.any(axis=0))
    if rows.size == 0:
        return None
    return Box(
        x=int(columns[0]),
        y=int(rows[0]),
        width=int(columns[-1] - columns[0] + 1),
        height=int(rows[-1] - rows[0] + 1),
    )


def resolve_authored(
    authored: tuple[AuthoredFrame, ...] | None, *, frames: int, where: str
) -> tuple[AuthoredFrame, ...] | None:
    """The sidecar's `frames:` block, checked against the set that actually exists.

    The block is one entry per frame, so its length is its claim about the set. A mismatch
    is refused rather than padded or truncated: an entry that silently lands on the wrong
    frame is a hitbox that deals on the wrong pose, which nobody notices until something
    takes damage it should not have.
    """
    if authored is None:
        return None
    if len(authored) != frames:
        raise SscError(
            "frames-block-mismatch",
            f"{where}: the sidecar authors {len(authored)} frame "
            f"entr{'y' if len(authored) == 1 else 'ies'}, and the set has {frames}",
            fix="one entry per frame, ~ for a frame with nothing; "
            "re-run tool curate with --drop to carry entries past a drop",
        )
    return authored


def resolve_sections(
    sections: tuple[Section, ...], *, frames: int, where: str
) -> tuple[Section, ...]:
    """The authored sections, checked against the set that actually exists (R2.4, R2.5).

    Both ends are inclusive, so the last frame of an eight-frame set is 7. That is the whole
    of this function and it is why it is worth one: an engine handed `[3, 8]` over eight
    frames does not complain, it plays a frame that is not there or stops one short, and
    nobody notices until they watch it.

    The refusal names the first section that is wrong rather than collecting them all: the
    author fixes one line, reruns, and the next is found. Listing every fault of a file
    somebody is halfway through writing is noise.
    """
    for section in sections:
        if frames < 1 or section.first >= frames or section.last >= frames:
            raise SscError(
                "section-out-of-range",
                f"{where}: section {section.name!r} covers frames "
                f"{section.first} to {section.last}, and the set has {frames}",
                fix=f"the last frame of this set is {frames - 1}"
                if frames
                else "this set has no frames to divide into sections",
            )
    return sections
