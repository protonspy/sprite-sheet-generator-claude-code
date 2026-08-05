"""`recipe.yaml` — the inherited recipe a derived asset is generated from.

A derived asset (`ssc asset new <key> --extends <parent>`) carries none of its
parent's pixels: it carries the *recipe* that made the parent, so a fresh
generation reproduces a variant against the same kind, pixel grid, palette, cell,
frame count and frame rate. Authored intent stays in `asset.yaml`
(`adr:0009-authored-intent-lives-in-a-sidecar`); the recipe is *derived*, a
snapshot of the parent taken the moment the child is created, and lives beside
`meta.json` in its own file rather than among the authored keys.

The recipe is also the chain: `extends` names the immediate parent, and walking
those names from the child reaches the root — which is how a cyclic or missing
parent is detected (`plans/ssc-completion.md` 6.3) without resolving a half-built
recipe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from ssc.cli.atomic import Directory
from ssc.cli.config import StrictLoader
from ssc.cli.errors import SscError
from ssc.cli.sidecar import MAX_FPS

RECIPE_NAME = "recipe.yaml"

#: A recipe is a few dozen lines, like `asset.yaml` and `ssc.yaml`; the ceiling is on
#: the read for the same reason `config.py` gives.
MAX_RECIPE_BYTES = 1 << 16

#: What the file may hold. Anything else is refused rather than ignored, the same
#: rule `asset.yaml` uses — a key ssc silently drops is a value a reader believes is
#: in effect, and a derived asset that silently dropped its `palette` is one nobody
#: can explain.
TOP_LEVEL = ("extends", "anchor", "kind", "pixel_size", "palette", "cell", "frames", "fps")


@dataclass(frozen=True)
class AnchorRef:
    """Where a derived asset's generation starts from: the parent's **anchor image**
    (see `docs/glossary.md` — the one image a character's directions and animations
    derive from, not the registration point). Carried in the recipe so a later
    generation has a reference to re-derive against, rather than re-discovering it
    by walking the chain.

    `asset` is the root of the chain — the asset that actually holds the anchor
    image — not the immediate parent. A grandchild inherits its parent's recipe
    verbatim, so the anchor stays pointed at the root while `extends` walks one
    hop at a time.
    """

    asset: str
    stage: str

    def as_document(self) -> dict[str, Any]:
        return {"asset": self.asset, "stage": self.stage}


@dataclass(frozen=True)
class Recipe:
    """The snapshot a child inherits. `extends` is the immediate parent, not the
    root — the chain is walkable through these files, and the inherited values are
    carried forward verbatim so a grandchild reads the same recipe its parent did."""

    extends: str
    anchor: AnchorRef
    kind: str
    pixel_size: int
    palette: str | None
    cell: tuple[int, int]
    frames: int
    fps: int

    def as_document(self) -> dict[str, Any]:
        """The YAML shape, in the order a person reads it: parent and the anchor
        image to generate from, then the recipe."""
        return {
            "extends": self.extends,
            "anchor": self.anchor.as_document(),
            "kind": self.kind,
            "pixel_size": self.pixel_size,
            "palette": self.palette,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "frames": self.frames,
            "fps": self.fps,
        }

    def as_dict(self) -> dict[str, Any]:
        """The report shape, `cell` as a map the way the kind profile and the index
        report it — so `--dry-run` and a later reader agree about what a cell is."""
        return dict(self.as_document())

    def reanchored(self, parent: str) -> Recipe:
        """The same recipe pointing at an immediate parent.

        A grandchild inherits its parent's recipe verbatim but rewrites `extends` to
        its own parent, so the chain stays walkable one hop at a time while the
        inherited values are the root's, copied without reinterpretation. The
        anchor is *not* rewritten: it names the root's anchor image, which a
        grandchild generates from just as its parent did.
        """
        return Recipe(
            extends=parent,
            anchor=self.anchor,
            kind=self.kind,
            pixel_size=self.pixel_size,
            palette=self.palette,
            cell=self.cell,
            frames=self.frames,
            fps=self.fps,
        )


def refuse(where: str, what: str, fix: str) -> SscError:
    """Every refusal from this module names the file and the key at fault."""
    return SscError("invalid-recipe", f"{where}: {what}", fix=fix)


def _int(given: Any, label: str, where: str, *, minimum: int, maximum: int) -> int:
    """A whole number in range. `bool` is an `int` in Python, so `pixel_size: true`
    is a mistake, not a grid of one — the same trap `sidecar._fps` guards."""
    if isinstance(given, bool) or not isinstance(given, int):
        raise refuse(
            where, f"{label} is {given!r}, not a whole number", f"write {label} as a number"
        )
    if given < minimum or given > maximum:
        raise refuse(
            where,
            f"{label} is {given}, outside {minimum} to {maximum}",
            f"write {label} as a number from {minimum} to {maximum}",
        )
    return given


def _anchor(given: Any, where: str) -> AnchorRef:
    """The anchor image reference: a map `{asset, stage}`, both names.

    `asset` is `<kind>/<key>` of the chain's root and `stage` is the anchor image's
    stage there — found by stage, never by filename, the same rule the skill hands
    the anchor on. Both are required: a recipe that omits the anchor carries no
    generation reference, and one that names the asset but not the stage sends a
    reader looking for a stage it cannot address.
    """
    if not isinstance(given, dict):
        raise refuse(where, f"anchor is {given!r}, not a map", "write anchor: {asset, stage}")
    if set(given) != {"asset", "stage"}:
        raise refuse(
            where, "anchor has keys other than asset and stage", "write anchor: {asset, stage}"
        )
    asset = given["asset"]
    stage = given["stage"]
    if not isinstance(asset, str) or not asset:
        raise refuse(where, "anchor.asset is not a name", "write the root as <kind>/<key>")
    if not isinstance(stage, str) or not stage:
        raise refuse(where, "anchor.stage is not a name", "write the anchor image's stage")
    return AnchorRef(asset=asset, stage=stage)


def _cell(given: Any, where: str) -> tuple[int, int]:
    """A cell as a map `width`/`height` or a pair `[width, height]`, both positive.

    Both shapes are accepted because both are readable: the kind profile and the
    index report a map, and a person hand-editing a recipe reaches for a pair. One
    is not a shortcut for the other.
    """
    if isinstance(given, dict):
        width = given.get("width")
        height = given.get("height")
        if set(given) != {"width", "height"}:
            raise refuse(
                where, "cell has keys other than width and height", "write cell: {width, height}"
            )
    elif isinstance(given, list) and len(given) == 2:
        width, height = given
    else:
        raise refuse(
            where,
            f"cell is {given!r}, not a size",
            "write cell: {width, height} or [width, height]",
        )
    width = _int(width, "cell.width", where, minimum=1, maximum=1 << 14)
    height = _int(height, "cell.height", where, minimum=1, maximum=1 << 14)
    return width, height


def parse(raw: bytes, where: str) -> Recipe:
    """One recipe, or a refusal naming what is wrong with it.

    A missing file is not parsed here — `load` turns `FileNotFoundError` into the
    answer "no recipe", since a parent that is a source rather than a derivation
    has none and is measured instead.
    """
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=StrictLoader)
    except (yaml.YAMLError, RecursionError, UnicodeDecodeError) as broken:
        raise refuse(where, f"not valid YAML: {broken}", "fix it by hand") from broken

    if not isinstance(document, dict):
        raise refuse(
            where,
            f"is a {type(document).__name__}, not a map",
            f"a recipe holds: {', '.join(TOP_LEVEL)}",
        )

    unknown = [key for key in document if key not in TOP_LEVEL]
    if unknown:
        raise refuse(
            where,
            f"declares {', '.join(str(key) for key in sorted(map(str, unknown)))}",
            f"a recipe holds: {', '.join(TOP_LEVEL)}",
        )

    for required in ("extends", "anchor", "kind", "pixel_size", "cell", "frames", "fps"):
        if required not in document:
            raise refuse(
                where, f"is missing {required!r}", f"a recipe holds: {', '.join(TOP_LEVEL)}"
            )

    extends = document["extends"]
    kind = document["kind"]
    if not isinstance(extends, str) or not extends:
        raise refuse(where, "extends is not a name", "write the parent as <kind>/<key>")
    if not isinstance(kind, str) or not kind:
        raise refuse(where, "kind is not a name", "write the parent's kind")

    palette = document.get("palette")
    if palette is not None and not isinstance(palette, str):
        raise refuse(
            where,
            f"palette is {palette!r}, not a name or null",
            "write the preset name, or leave it out",
        )

    return Recipe(
        extends=extends,
        anchor=_anchor(document["anchor"], where),
        kind=kind,
        pixel_size=_int(document["pixel_size"], "pixel_size", where, minimum=1, maximum=1 << 14),
        palette=palette,
        cell=_cell(document["cell"], where),
        frames=_int(document["frames"], "frames", where, minimum=0, maximum=1 << 24),
        fps=_int(document["fps"], "fps", where, minimum=1, maximum=MAX_FPS),
    )


def write(asset_dir: Directory, recipe: Recipe) -> str:
    """Write `recipe.yaml` into a freshly created asset, refusing if one is there.

    Through the held directory for the same reason `meta.save` is: the directory was
    checked when the asset was created, and a recipe written by path after that check
    is a recipe that could have landed outside the workspace. `write_new` makes
    "the child carries a recipe" a property of the write rather than a check a caller
    could forget — a second `--extends` against an asset that already has one is a
    no-op a caller could mistake for success.
    """
    payload = yaml.safe_dump(recipe.as_document(), sort_keys=False, default_flow_style=False)
    asset_dir.write_new(RECIPE_NAME, payload.encode("utf-8"))
    return RECIPE_NAME


def load(asset_dir: Directory) -> Recipe | None:
    """An asset's recipe, read through the held directory, or `None` where it has none.

    `None` rather than an error because the distinction is load-bearing: a parent
    that is a *source* has no recipe and is measured from its pixels, while a parent
    that is a *derivation* has one and is inherited verbatim. A missing file is the
    first case, and a refusal here would force every `--extends` to re-measure a chain
    that already recorded the answer.
    """
    where = str(asset_dir.path / RECIPE_NAME)
    try:
        raw = asset_dir.read(RECIPE_NAME, max_bytes=MAX_RECIPE_BYTES)
    except FileNotFoundError:
        return None
    return parse(raw, where)


def walk(workspace: Any, start: str, walked: tuple[str, ...] = ()) -> list[str]:
    """Walk the `extends` chain from `start` to its root, returning every asset in
    it, in order. Refuse — naming the chain walked so far — if a link is missing or
    the chain is cyclic, rather than handing back a partial recipe a caller would
    resolve as if it were whole.

    The chain is the `extends` field of each asset's recipe; an asset with no recipe
    is the root, and the walk stops there. `walked` is the chain already traversed
    before `start` — the immediate parent, when `asset new --extends` validates the
    chain above an extension — kept so a loop closing back on it is caught and the
    refusal names the whole chain, not just the loop.

    `listing` is imported lazily so this chain module does not pull the whole CLI
    surface in at import time; the walk is the one place the recipe needs to resolve
    an address, and the rest of the module is pure data.
    """
    from ssc.cli.listing import resolve

    chain = list(walked)
    current = start
    while True:
        if current in chain:
            raise SscError(
                "chain-cyclic",
                f"recipe chain is cyclic: {' -> '.join([*chain, current])}",
                fix="break the loop in the recipes' extends fields by hand",
            )
        try:
            held, _record = resolve(workspace, current)
        except SscError as missing:
            if missing.code != "no-asset":
                raise
            raise SscError(
                "chain-missing",
                f"recipe chain is broken at {current}: {' -> '.join([*chain, current])}",
                fix=f"restore {current}, or extend a parent whose chain still resolves",
            ) from missing
        with held:
            own = load(held)
        chain.append(current)
        if own is None:
            return chain
        current = own.extends
