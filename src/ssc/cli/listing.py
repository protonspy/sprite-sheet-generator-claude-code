"""Reading the workspace back.

`workspace-foundation` recorded a stage, a class and a lineage for every file it wrote.
This is the other half: walking those records, classifying each file by medium, resolving
an asset from what a caller typed, and following a file back to the thing it came from.

Nothing here is a command. That is deliberate — stage resolution and the lineage walk are
the two parts worth testing against a hand-built `AssetMeta` rather than through a CLI
invocation and a temporary directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ssc.cli import meta
from ssc.cli.errors import SscError, UsageError
from ssc.cli.meta import AssetMeta, FileRecord, prefix_of
from ssc.cli.workspace import Workspace

Media = Literal["image", "video"]

#: `.gif` is an image here, and the call is deliberate: every GIF `ssc` writes is a
#: rendered preview of something the index already describes, not a clip a model returned.
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"})
VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mov", ".mkv", ".m4v"})


def media_of(path: str) -> Media | None:
    """Which medium a recorded file is, from its extension alone (R1.1).

    `None` is a real answer, not a failure: a record whose path carries no extension this
    knows — a directory of frames, a sidecar — belongs to neither listing, and R1.2 is
    what stops that from making it invisible.
    """
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return None


@dataclass(frozen=True)
class Entry:
    """One recorded file, with the asset it belongs to attached.

    A `FileRecord` alone cannot answer "which asset is this" — the record is stored under
    the asset and does not repeat it — and every listing has to.
    """

    kind: str
    key: str
    directory: Path
    record: FileRecord

    @property
    def media(self) -> Media | None:
        return media_of(self.record.path)

    @property
    def file(self) -> Path:
        """The file on disk, re-resolved and refused if it leaves the asset (R4.2)."""
        return inside(self.directory, self.record.path)

    def as_dict(self) -> dict[str, Any]:
        """`derived_from` travels raw as well as resolved: a parent path naming no record
        is a corrupt lineage, and it can only be seen if the paths themselves are here."""
        return {
            "kind": self.kind,
            "key": self.key,
            "stage": self.record.stage,
            "class": self.record.file_class,
            "path": self.record.path,
            "media": self.media,
            "sha256": self.record.sha256,
            "derived_from": list(self.record.derived_from),
            "produced_by": {
                "command": self.record.produced_by.command,
                "params": dict(self.record.produced_by.params),
                "cache_key": self.record.produced_by.cache_key,
            },
        }


def inside(directory: Path, relative: str) -> Path:
    """Resolve `relative` against `directory` and refuse anything that leaves it.

    `meta.py` already rejects an escaping path when the record is built or loaded, but it
    validates a *string*: it cannot see that a segment is a symlink pointing somewhere
    else on disk. So every command that reaches a recorded path re-resolves it here first
    — `clean` before deleting, and `show` before opening. One validation gap should not be
    all that stands between a hand-edited `meta.json` and either `shutil.rmtree` on a home
    directory or a `doctor` report on a file outside the workspace.
    """
    target = (directory / relative).resolve()
    root = directory.resolve()
    if target != root and root not in target.parents:
        raise SscError(
            "path-escapes-asset",
            f"{relative!r} resolves to {target}, which is outside {root}",
            fix=f"remove that record from {meta.META_NAME}",
        )
    if target == root:
        raise SscError(
            "path-escapes-asset",
            f"{relative!r} is the asset directory itself, which is not a file in it",
            fix=f"remove that record from {meta.META_NAME}",
        )
    return target


def asset_dirs(workspace: Workspace) -> list[Path]:
    """Every directory holding a `meta.json`, ordered by kind then key (R2.6).

    The glob is two levels deep and not recursive, because `assets/<kind>/<key>/` is the
    layout — see `adr:0007-group-assets-by-kind-then-key`. A `meta.json` deeper than that
    is not an asset and is not treated as one.

    Each hit is checked for having stayed under `assets/` (R4.1). `inside` guards a path
    recorded in a file; this guards the directory the glob walked into, which is the other
    half: a symlinked `<kind>/` or `<key>/` would otherwise put another tree's assets in
    this workspace's listing without anything saying so. `assets/` itself being a symlink
    is fine and deliberately allowed — it is the root both sides resolve against, so a
    workspace whose art lives on another disk keeps working.
    """
    if not workspace.assets.is_dir():
        return []
    root = workspace.assets.resolve()
    found = sorted(path.parent for path in workspace.assets.glob(f"*/*/{meta.META_NAME}"))
    for directory in found:
        if root not in directory.resolve().parents:
            raise SscError(
                "asset-escapes-workspace",
                f"{directory} resolves to {directory.resolve()}, which is outside {root}",
                fix=f"remove it from {workspace.assets}, or move the asset in for real",
            )
    return found


def chain_order(record: FileRecord) -> tuple[bool, int, str]:
    """The numbered prefix orders the chain for a reader (R2.6), and a file without one
    sorts after everything that has one rather than colliding at zero."""
    prefix = prefix_of(record.path)
    return (prefix is None, prefix or 0, record.path)


def entries(workspace: Workspace) -> list[Entry]:
    """Every recorded file in the workspace, in listing order."""
    found: list[Entry] = []
    for directory in asset_dirs(workspace):
        record = meta.load(directory)
        for file_record in sorted(record.files, key=chain_order):
            found.append(Entry(record.kind, record.key, directory, file_record))
    return found


def resolve(workspace: Workspace, address: str) -> tuple[Path, AssetMeta]:
    """Find an asset from `<kind>/<key>` or from a bare `<key>` (R3.2).

    Keys are unique per kind rather than globally, so a bare key can genuinely name two
    assets. Guessing between them would be worse than either answer: the refusal names
    the kinds it matched so the caller can retype one (R3.3).
    """
    parts = address.split("/")
    if len(parts) == 2:
        directory = workspace.asset_dir(parts[0], parts[1])
        if not meta.path_of(directory).is_file():
            raise UsageError(
                "no-asset",
                f"no asset {address} in this workspace",
                fix=f"ssc asset new {parts[1]} --kind {parts[0]}",
            )
        return directory, meta.load(directory)

    if len(parts) != 1:
        raise UsageError(
            "invalid-address",
            f"{address!r} is not an asset; write it as <key> or as <kind>/<key>",
        )

    matches = [directory for directory in asset_dirs(workspace) if directory.name == address]
    if not matches:
        raise UsageError(
            "no-asset",
            f"no asset {address!r} in this workspace",
            fix=f"ssc asset new {address} --kind <kind>",
        )
    if len(matches) > 1:
        kinds = ", ".join(sorted(directory.parent.name for directory in matches))
        raise UsageError(
            "ambiguous-key",
            f"{address!r} is an asset of more than one kind: {kinds}",
            fix=f"name the kind, for example {sorted(matches)[0].parent.name}/{address}",
        )
    return matches[0], meta.load(matches[0])


def lineage(record: AssetMeta, entry: FileRecord) -> list[FileRecord]:
    """Every file `entry` came from, transitively, roots first (R3.6).

    Iterative rather than recursive, and cycle-refusing, because `derived_from` is
    validated for escape and not for acyclicity: `a → b → a` survives being loaded from a
    hand-edited `meta.json` and would otherwise spin here forever (R3.7).

    An ancestor path naming no record is skipped rather than refused — `show` reports the
    raw `derived_from` alongside this, so a dangling reference stays visible without
    turning a listing into a failure.
    """
    by_path = {candidate.path: candidate for candidate in record.files}
    ordered: list[FileRecord] = []
    #: `False` while a file's ancestors are still being walked, `True` once they are done.
    #: Meeting a file that is still `False` means it is reachable from itself.
    settled: dict[str, bool] = {}
    stack: list[tuple[FileRecord, bool]] = [(entry, False)]

    while stack:
        current, expanded = stack.pop()
        if expanded:
            settled[current.path] = True
            if current.path != entry.path:
                ordered.append(current)
            continue
        if settled.get(current.path) is True:
            continue
        if current.path in settled:
            raise SscError(
                "lineage-cycle",
                f"{record.kind}/{record.key} records {current.path} among its own ancestors",
                fix=f"break the cycle in {record.kind}/{record.key}/{meta.META_NAME}",
            )
        settled[current.path] = False
        stack.append((current, True))
        for parent_path in reversed(current.derived_from):
            parent = by_path.get(parent_path)
            if parent is not None:
                stack.append((parent, False))

    return ordered
