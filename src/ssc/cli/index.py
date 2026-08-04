"""The index model — what an engine is told about a workspace.

`ssc index` reads `assets/`, packs what each kind's profile says it packs, and writes
`dist/`. This module is the model that sits between those two: it knows about assets, kinds
and sidecars, and nothing about any particular engine. `cli/formats.py` renames its fields
for Pixi, Phaser and Godot without reading a workspace or an image.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np

from ssc.cli import kinds, meta
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError
from ssc.cli.kinds import Profile
from ssc.cli.listing import asset_dirs, bound, chain_order, frames_of, media_of
from ssc.cli.meta import AssetMeta, FileRecord
from ssc.cli.sidecar import Playback, Section
from ssc.cli.sidecar import load as load_sidecar
from ssc.cli.workspace import Workspace

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
    return Published(
        kind=record.kind,
        key=record.key,
        stage=chosen.stage,
        frames=frames_of(held, record, chosen.stage),
        playback=load_sidecar(held),
    )


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
