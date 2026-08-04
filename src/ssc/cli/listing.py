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

import numpy as np

from ssc.cli import meta
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError, UsageError
from ssc.cli.frames import IMAGE_SUFFIXES as FRAME_SUFFIXES
from ssc.cli.frames import MAX_FILE_BYTES, MAX_SET_PIXELS, decode_image
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
    record: FileRecord

    @property
    def media(self) -> Media | None:
        return media_of(self.record.path)

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
    else on disk. One validation gap should not be all that stands between a hand-edited
    `meta.json` and `shutil.rmtree` on a home directory.

    `clean`'s pre-flight is the caller left, and it is a *report* rather than the guard:
    it names every file a sweep would remove before removing any, so a refusal comes with
    the whole list. The guard is `Directory.delete`, which descends through the binding and
    refuses the same escape at the moment it acts. `show` used to resolve here too, and no
    longer does — reading through `Directory.read` makes the containment part of the read
    instead of a check standing next to one (workspace-foundation R3.7).
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


def placed(workspace: Workspace, directory: Path) -> Path:
    """Refuse an asset directory that is not where its own address says it is (R4.1).

    `inside` guards a path recorded *in* a file; this guards the directory that file was
    found in, which is the other half. A linked `<kind>/` or `<key>/` — a symlink, or a
    junction, which Windows lets an unprivileged user create — would otherwise put another
    tree's assets in this workspace under this workspace's name, and `inside` could not
    tell: it only knows the file stayed inside the directory it was given.

    Every route to an asset directory passes through here, because there are several and
    guarding some of them is the same as guarding none.

    **Two properties, because refusing the escape alone left the alias.** The first draft
    proved only that the directory resolved somewhere *under* `assets/`, which is what its
    old name said. That admits `assets/character/hero` being a link to `assets/icon/coin`:
    it never leaves the workspace, so every check there was passed, and the command went on
    to report `icon/coin`'s record as `character/hero`. The address is the caller's whole
    statement of which asset it means, so the check is that the directory resolves to
    exactly the `<kind>/<key>` place naming it — which subsumes the escape and costs
    nothing legitimate, since a `<kind>/` link pointing off the disk already failed the
    weaker test.

    `assets/` itself being a link is still fine and deliberately allowed — it is the root
    both sides resolve against, so a workspace whose art lives on another disk keeps
    working.
    """
    root = workspace.assets.resolve()
    resolved = directory.resolve()
    if root not in resolved.parents:
        raise SscError(
            "asset-escapes-workspace",
            f"{directory} resolves to {resolved}, which is outside {root}",
            fix=f"remove it from {workspace.assets}, or move the asset in for real",
        )
    # Built from the unresolved path, because that is the address: the two components a
    # caller typed, or the two the scan walked. Comparing it against what those components
    # actually resolve to is the whole check.
    expected = root / directory.parent.name / directory.name
    if resolved != expected:
        raise SscError(
            "asset-displaced",
            f"{directory} resolves to {resolved}, which is not {expected}",
            fix=f"remove the link at {directory}, or address the asset that is really there",
        )
    return directory


def bound(workspace: Workspace, directory: Path) -> Directory:
    """`placed`, for a caller about to read or write it — held, then checked (R3.7).

    The order is the whole content of this function, and it is the reverse of the obvious
    one. Checking a path and then opening it leaves the window the check was for: a
    component swapped in between is followed by the open, and `placed` never sees it. So:
    open first, which pins a directory; then run the check, which resolves the path; then
    confirm the path that passed names the directory being held. A swap before the open
    fails the check, a swap after it cannot reach the work, and a swap in between fails the
    confirmation.

    **Reads go through here too, and did not at first.** The writes were bound a task
    earlier and the reads left by path, on the reasoning that a lost race under a read
    costs less than one under a write. It does cost less and it is not nothing: what a
    swapped read produces is a foreign `meta.json` reported as the asset that was asked
    for, which nothing downstream can tell from the real one.

    The escape gate and not `addressed`, for the reason `addressed` gives itself: `clean`
    writes a record back for every asset in the workspace, so refusing here over one
    asset's stray directory would abort a clean half way through — the blast radius that
    keeps the layout check on the asset somebody named. The caller that named one adds it.

    This opens what is there and does not create it. The creating routes `mkdir` first,
    because what they do about a directory that already exists differs between them.
    """
    handle = Directory.open(directory)
    try:
        if not handle.bindable:
            # Measured per volume, not assumed per platform — see `Directory.bindable`. A
            # guard that cannot tell whether it is working is not one to write under.
            raise SscError(
                "no-file-identity",
                f"{directory} is on a volume that reports no file identity, so ssc cannot "
                f"prove the directory it checked is the one it acts on",
                fix="keep the workspace on NTFS, or on any POSIX filesystem",
            )
        placed(workspace, directory)
        handle.confirm(directory)
    except BaseException:
        handle.close()
        raise
    return handle


def addressed(workspace: Workspace, directory: Path) -> Directory:
    """The asset a caller named, checked as a whole and held (R4.1, R2.5, R3.7).

    Both checks belong to an asset somebody addressed by name and is about to read or
    write. The placement check is cheap and applies to every route; the layout check is not
    on `asset_dirs`' scan on purpose, because refusing to *list* a workspace over one
    asset's stray directory takes down `list`, `clean` and every other asset with it —
    the read paths in this module skip what they cannot use and report it, they do not
    abort. Enforcement lands where it changes an outcome: the asset being opened.
    """
    handle = bound(workspace, directory)
    try:
        meta.check_layout(handle)
    except BaseException:
        handle.close()
        raise
    return handle


def asset_dirs(workspace: Workspace) -> list[Path]:
    """Every directory holding a `meta.json`, ordered by kind then key (R2.6).

    The glob is two levels deep and not recursive, because `assets/<kind>/<key>/` is the
    layout — see `adr:0007-group-assets-by-kind-then-key`. A `meta.json` deeper than that
    is not an asset and is not treated as one.
    """
    if not workspace.assets.is_dir():
        return []
    found = sorted(path.parent for path in workspace.assets.glob(f"*/*/{meta.META_NAME}"))
    for directory in found:
        placed(workspace, directory)
    return found


def chain_order(record: FileRecord) -> tuple[bool, int, str]:
    """The numbered prefix orders the chain for a reader (R2.6), and a file without one
    sorts after everything that has one rather than colliding at zero."""
    prefix = prefix_of(record.path)
    return (prefix is None, prefix or 0, record.path)


def entries(workspace: Workspace) -> list[Entry]:
    """Every recorded file in the workspace, in listing order.

    One binding per asset, held only for the load (R3.7). The scan and the read are two
    acts, and the second is the one that decides what gets reported — so the directory the
    scan approved is the directory the record comes out of, rather than whatever that path
    names by the time the loop reaches it.
    """
    found: list[Entry] = []
    for directory in asset_dirs(workspace):
        with bound(workspace, directory) as held:
            record = meta.load(held)
        for file_record in sorted(record.files, key=chain_order):
            found.append(Entry(record.kind, record.key, file_record))
    return found


def resolve(workspace: Workspace, address: str) -> tuple[Directory, AssetMeta]:
    """Find an asset from `<kind>/<key>` or from a bare `<key>`, held open (R3.2, R3.7).

    Keys are unique per kind rather than globally, so a bare key can genuinely name two
    assets. Guessing between them would be worse than either answer: the refusal names
    the kinds it matched so the caller can retype one (R3.3).

    The caller closes what comes back. It is handed over rather than closed here because
    `show` reads the file the record names next, and a binding dropped between the record
    and the file it describes is a binding that covered the cheaper half.
    """
    parts = address.split("/")
    if len(parts) == 2:
        # `asset_dir` validates the two names as strings; `placed` is what checks where
        # they actually landed. This branch never touches `asset_dirs`, so skipping it here
        # would leave `show <kind>/<key>` reading an asset directory that left the
        # workspace while `list` and `show <key>` both refused it.
        directory = workspace.asset_dir(parts[0], parts[1])
        # Before `addressed`, because a key nobody has created yet is an ordinary mistake
        # with a command that fixes it, and `Directory.open` on a path that is not there is
        # a `FileNotFoundError` that says none of that.
        if not meta.path_of(directory).is_file():
            raise UsageError(
                "no-asset",
                f"no asset {address} in this workspace",
                fix=f"ssc asset new {parts[1]} --kind {parts[0]}",
            )
        held = addressed(workspace, directory)
        try:
            return held, meta.load(held)
        except BaseException:
            held.close()
            raise

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
    held = addressed(workspace, matches[0])
    try:
        return held, meta.load(held)
    except BaseException:
        held.close()
        raise


def frames_of(asset_dir: Directory, record: AssetMeta, stage: str) -> list[np.ndarray]:
    """The frames of a recorded stage, read **through the held directory**.

    It arrived with `specs/gates-and-resume/` and lived in `commands/run.py` until
    `specs/engine-index/` needed the same read for every asset at once. It is here rather
    than copied because of what it is: every read of a recorded asset file in this project
    goes through the binding rather than through a path — `commands/media.py` does it,
    `meta.load` does it — and `atomic.py` documents at length why. A component can be
    replaced by a link between the check and the read, and Windows lets an unprivileged user
    create one. A second copy of this function is a second place for that discipline to be
    dropped, quietly, by whoever edits only one of them.

    Names are listed by path; every byte is read through the binding. Listing outside it is
    harmless — a name is not content, and a swapped component makes the confined read refuse
    rather than making the listing lie in a way that reaches anything.
    """
    entry = record.stage(stage)
    where = asset_dir.path / entry.path
    if not where.exists():
        raise SscError(
            "stage-missing",
            f"{record.kind}/{record.key} records stage {stage!r} at {entry.path}, "
            "which is not there",
            fix="ssc clean removed it, or it was deleted by hand; rerun the step that made it",
        )

    if where.is_file():
        return [decode_image(asset_dir.read(entry.path, max_bytes=MAX_FILE_BYTES), entry.path)]

    names = sorted(
        child.name for child in where.iterdir() if child.suffix.lower() in FRAME_SUFFIXES
    )
    if not names:
        raise SscError(
            "stage-missing",
            f"{record.kind}/{record.key} records stage {stage!r} at {entry.path}, "
            "which holds no images",
            fix="rerun the step that made it",
        )
    images: list[np.ndarray] = []
    total = 0
    for name in names:
        relative = f"{entry.path}/{name}"
        image = decode_image(asset_dir.read(relative, max_bytes=MAX_FILE_BYTES), relative)
        total += image.shape[0] * image.shape[1]
        if total > MAX_SET_PIXELS:
            # The ceiling on the *set*, which bounding each file individually does not give:
            # a few hundred frames each comfortably under `MAX_PIXELS` is gigabytes resident
            # at once, reached by an ordinary run over a large earlier stage rather than by
            # anything hostile. Accumulated as they decode rather than measured from headers
            # first, so the bytes still arrive through the binding.
            raise SscError(
                "set-too-large",
                f"{record.kind}/{record.key} stage {stage!r} is over the "
                f"{MAX_SET_PIXELS:,}-pixel ceiling for one set",
                fix="split the animation, or work on fewer frames at a time",
            )
        images.append(image)
    return images


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
