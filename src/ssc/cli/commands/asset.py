"""`ssc asset new` — create an asset directory and its record (R2.2, R2.3).

With `--extends <parent>`, the new asset carries no pixels: it carries a `recipe.yaml`
inheriting the parent's recipe — kind, pixel_size, palette, cell, frame counts, fps — so
a fresh generation reproduces a variant against the same settings. See
`cli/recipe.py` for the file and the chain.
"""

from __future__ import annotations

from typing import Any

import click

from ssc.cli import kinds, listing, meta, palettes, recipe, sidecar
from ssc.cli.atomic import Directory
from ssc.cli.errors import UsageError
from ssc.cli.listing import bound, placed
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace
from ssc.core.doctor.checks import detect_pixel_size


@click.group("asset", help="Create and inspect assets.")
def asset() -> None:
    """Grouped under a noun because `ssc asset new` reads as what it does, and because
    later leaves add verbs here rather than at the top level."""


def _publishable_stages(record: meta.AssetMeta) -> list[meta.FileRecord]:
    """The parent's chain an engine gets, in chain order, keeping only what
    `ssc index` and `ssc image show` would publish — so a derived asset measures
    its recipe from the same stages a later publish would surface, and not from an
    intermediate one the parent grew past.
    """
    from ssc.cli.index import publishable
    from ssc.cli.listing import chain_order

    candidates = [entry for entry in sorted(record.files, key=chain_order) if publishable(entry)]
    if not candidates:
        raise UsageError(
            "no-recipe",
            f"{record.kind}/{record.key} records no image to derive a recipe from",
            fix="generate or style the parent, then derive from it",
        )
    return candidates


def _published_stage(record: meta.AssetMeta) -> str:
    """The last of the parent's publishable stages — the end the work was heading
    towards. Measurement reads frames here so the recipe's `frames` and `pixel_size`
    describe what a later `ssc index` would publish."""
    return _publishable_stages(record)[-1].stage


def _anchor_stage(record: meta.AssetMeta) -> str:
    """The parent's **anchor image** stage — the one image every direction and
    animation derives from (see `docs/glossary.md`), not the registration point.

    The first `source`-class stage in chain order: the original generation a
    character's poses and cycles are seeded from. A parent whose source was
    cleaned away falls back to its first publishable stage, so a derivation still
    carries a reference when only a derived stage remains. Carried into the
    recipe as the generation reference, distinct from the published stage the
    recipe measures its counts from.
    """
    candidates = _publishable_stages(record)
    sources = [entry for entry in candidates if entry.file_class == "source"]
    return (sources[0] if sources else candidates[0]).stage


def _measure(
    parent: str, held: Directory, record: meta.AssetMeta, workspace: Workspace
) -> recipe.Recipe:
    """Build a recipe from a parent that is a *source* — measured from its pixels,
    its kind's profile and the workspace's locked palette, rather than inherited from
    a recipe of its own.

    `never the pixels` is the rule the child honours: the parent's frames are read to
    measure `pixel_size` and `frame count`, and nothing of them is written into the
    child. The measurement is a snapshot; the child is generated from the recipe, not
    from the parent's bytes.
    """
    profile = kinds.resolve(record.kind, workspace).profile
    playback = sidecar.load(held).playback
    fps = sidecar.frame_rate(playback, profile.fps)
    stage = _published_stage(record)
    frames = listing.frames_of(held, record, stage)
    pixel_size = detect_pixel_size(frames[0]) if frames else 1
    palette_path = workspace.root / palettes.PALETTE_FILE
    palette = palettes.read_locked(palette_path).preset if palette_path.is_file() else None
    return recipe.Recipe(
        extends=parent,
        anchor=recipe.AnchorRef(asset=parent, stage=_anchor_stage(record)),
        kind=record.kind,
        pixel_size=pixel_size,
        palette=palette,
        cell=profile.cell,
        frames=len(frames),
        fps=fps,
    )


@ssc_command("new", help="Create an asset, or extend a parent.", needs_workspace=True)
@click.option(
    "--kind",
    default=None,
    help="The asset's kind. Inherited from the parent with --extends.",
)
@click.option(
    "--extends",
    "parent",
    default=None,
    help="A <kind>/<key> to derive a recipe from, carrying no pixels.",
)
@click.argument("key")
def asset_new(
    key: str,
    kind: str | None,
    parent: str | None,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    # Without a parent, the kind has to resolve to a profile (R3.2). A typo here would
    # otherwise create an asset of a kind nothing knows anything about, and surface
    # commands later as a cell size nobody chose. With a parent, the kind is inherited
    # and `--kind` is only a check that the caller did not disagree with the parent.
    if parent is None and kind is None:
        raise UsageError(
            "no-kind",
            "asset new needs a kind",
            fix="give --kind <name>, or --extends <parent> to inherit one",
        )

    inherited: recipe.Recipe | None = None
    if parent is not None:
        held, parent_record = listing.resolve(workspace, parent)
        with held:
            if kind is not None and kind != parent_record.kind:
                raise UsageError(
                    "kind-mismatch",
                    f"{parent} is a {parent_record.kind}, not a {kind}",
                    fix="drop --kind to inherit the parent's kind, or extend a parent of that kind",
                )
            kind = parent_record.kind
            # A parent that is itself a derivation has a recipe: inherit it verbatim,
            # re-anchored to the immediate parent, so the chain walks one hop at a time
            # and the inherited values are the root's. A parent that is a source has
            # none, and is measured from its pixels.
            own = recipe.load(held)
        if own is not None:
            # The parent's recipe was inherited from a chain sound when it was built.
            # Walk that chain now to refuse a hand-edited cycle or a deleted link
            # before the child joins it — naming the chain walked so far rather than
            # resolving a partial recipe. `walked` carries the immediate parent so a
            # loop closing back on it is caught, and the refusal names the whole chain.
            recipe.walk(workspace, own.extends, walked=(parent,))
            inherited = own.reanchored(parent)
        if inherited is None:
            held, parent_record = listing.resolve(workspace, parent)
            with held:
                inherited = _measure(parent, held, parent_record, workspace)

    assert kind is not None  # narrowed by the two branches above
    kinds.resolve(kind, workspace)
    # `asset_dir` validates the two names as strings; it cannot see that `assets/<kind>/`
    # is a link pointing somewhere else on disk. This is a route that *creates* an asset,
    # so without the check a linked kind directory makes `mkdir` and `meta.json` land
    # outside the workspace — and every later command then reads an asset the workspace
    # does not own.
    directory = placed(workspace, workspace.asset_dir(kind, key))

    # Uniqueness is per kind, not global — see adr:0007-group-assets-by-kind-then-key for
    # why two kinds are allowed to share a key.
    if meta.path_of(directory).exists():
        raise UsageError(
            "asset-exists",
            f"{kind}/{key} already exists at {directory}",
            fix="choose another key, or work with the one that is there",
        )

    data: dict[str, Any] = {"key": key, "kind": kind, "path": str(directory)}
    if parent is not None:
        data["extends"] = parent
        data["recipe"] = inherited.as_dict() if inherited is not None else None
    if dry_run:
        message = f"would create {kind}/{key}"
        if parent is not None:
            message += f" extending {parent}"
        return Result("asset new", message, data, dry_run=True)

    directory.mkdir(parents=True, exist_ok=True)
    # Held and checked again, now that the path exists. The first check ran against a
    # `<kind>/` that may not have existed yet, and `resolve()` reads a missing component
    # literally — so a link planted between the check and `mkdir` would have been invisible
    # to it and followed by `mkdir(parents=True)`. `bound` re-checks *and* keeps the
    # directory it checked, which is what the write below goes through: re-checking alone
    # left the swap open for the statements between the check and the write.
    with bound(workspace, directory) as held:
        meta.save(held, meta.AssetMeta(key=key, kind=kind, derived_from=parent))
        if parent is not None and inherited is not None:
            recipe.write(held, inherited)
    message = f"created {kind}/{key}"
    if parent is not None:
        message += f" extending {parent}"
    return Result("asset new", message, data)


asset.add_command(asset_new)
