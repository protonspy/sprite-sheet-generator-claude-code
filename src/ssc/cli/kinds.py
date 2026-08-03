"""What a kind means.

`workspace-foundation` records the name and deliberately gives it none. This is the profile
behind it — and it is a **profile rather than a closed enum**, which is the hard-to-reverse
part and has its own record: `adr:0008-a-kind-is-a-profile-not-an-enum`.

The consequence to hold on to while reading the rest of this codebase: the set of kinds is
data, so every consumer reads a profile. An `if kind == "character"` anywhere is the defect
this exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

import yaml

from ssc.cli.errors import SscError, UsageError
from ssc.cli.names import check_name
from ssc.cli.workspace import Workspace

BUILT_IN = "built-in"
DECLARED = "ssc.yaml"


@dataclass(frozen=True)
class Profile:
    """Everything a command may need to know about an asset of this kind.

    Fields nobody consumes yet are still declared, because the leaves that will consume them
    must not each invent a name for the same thing — `atlas_layout` is `atlas-packing`'s,
    `checks` is `tile-assets`' and `ui-assets`', `template` is `gen-fal`'s.
    """

    name: str
    cell: tuple[int, int] = (64, 64)
    anchor: str = "centre"
    animates: bool = False
    atlas_layout: str = "grid"
    checks: tuple[str, ...] = ()
    template: str = "generic"
    normal_map: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "anchor": self.anchor,
            "animates": self.animates,
            "atlas_layout": self.atlas_layout,
            "checks": list(self.checks),
            "template": self.template,
            "normal_map": self.normal_map,
        }


#: The six the package ships. Defaults, not a frozen table — a project may override any of
#: them, and `kind show` reports which fields it did.
BUILT_INS: dict[str, Profile] = {
    "character": Profile(
        name="character",
        cell=(64, 64),
        anchor="feet",
        animates=True,
        checks=("pixel_grid", "bleed", "drift", "halo", "palette", "flicker", "silhouette"),
        template="character",
    ),
    "icon": Profile(
        name="icon",
        cell=(32, 32),
        anchor="centre",
        atlas_layout="bin",
        checks=("pixel_grid", "halo", "palette", "silhouette"),
        template="icon",
    ),
    "tile": Profile(
        name="tile",
        cell=(32, 32),
        anchor="centre",
        atlas_layout="grid",
        checks=("pixel_grid", "palette", "seam"),
        template="tile",
    ),
    "ui": Profile(
        name="ui",
        cell=(64, 64),
        anchor="centre",
        atlas_layout="bin",
        checks=("pixel_grid", "halo", "palette", "nineslice"),
        template="ui",
    ),
    "banner": Profile(
        name="banner",
        cell=(256, 64),
        anchor="centre",
        atlas_layout="bin",
        checks=("palette",),
        template="banner",
    ),
    "map": Profile(
        name="map",
        cell=(128, 128),
        anchor="centre",
        atlas_layout="bin",
        checks=("palette",),
        template="map",
    ),
}

FIELDS = {item.name for item in fields(Profile)} - {"name"}


@dataclass(frozen=True)
class Resolved:
    """A profile, and where each of its fields came from (R2.3).

    The provenance is the part worth building rather than assuming: a project overriding one
    field and inheriting five is the ordinary case, and "why is my cell 32" is the question
    somebody actually asks.
    """

    profile: Profile
    source: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {**self.profile.as_dict(), "source": dict(self.source)}


def parse_cell(value: Any, name: str) -> tuple[int, int]:
    text = str(value).lower().split("x")
    if len(text) != 2 or not all(part.strip().isdigit() for part in text):
        raise SscError(
            "invalid-kind",
            f"kind {name!r} declares cell {value!r}, which is not a size like 64x64",
            fix=f"write it as WxH under kinds.{name}.cell in ssc.yaml",
        )
    return int(text[0]), int(text[1])


def declared(workspace: Workspace | None) -> dict[str, dict[str, Any]]:
    """The `kinds:` map from `ssc.yaml`, or nothing outside a workspace."""
    if workspace is None or not workspace.config_path.is_file():
        return {}
    try:
        document = yaml.safe_load(workspace.config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as broken:
        raise SscError(
            "invalid-config",
            f"{workspace.config_path} is not valid YAML: {broken}",
            fix="fix it by hand, or restore it from git",
        ) from broken
    found = document.get("kinds") or {}
    if not isinstance(found, dict):
        raise SscError(
            "invalid-config",
            f"{workspace.config_path} declares `kinds` as {type(found).__name__}, not a map",
            fix="write it as a map of name to profile",
        )
    return found


def merge(name: str, stated: dict[str, Any]) -> Resolved:
    """One kind's profile, field by field, with where each field came from (R1.3, R1.4).

    A declaration naming a built-in overrides it field by field rather than replacing it: a
    project that sets `character`'s cell and nothing else keeps the anchor, the checks and
    the template it did not mention.
    """
    check_name(name, "a kind")
    base = BUILT_INS.get(name, Profile(name=name))
    source = {item: (BUILT_IN if name in BUILT_INS else "default") for item in FIELDS}

    unknown = sorted(set(stated) - FIELDS)
    if unknown:
        raise SscError(
            "invalid-kind",
            f"kind {name!r} declares {', '.join(unknown)}, which is not a profile field",
            fix=f"a profile has: {', '.join(sorted(FIELDS))}",
        )

    values: dict[str, Any] = {}
    for item, value in stated.items():
        if item == "cell":
            values[item] = parse_cell(value, name)
        elif item == "checks":
            if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
                raise SscError(
                    "invalid-kind",
                    f"kind {name!r} declares checks {value!r}, which is not a list of names",
                    fix=f"write it as a list under kinds.{name}.checks",
                )
            values[item] = tuple(value)
        elif item in {"animates", "normal_map"}:
            if not isinstance(value, bool):
                raise SscError(
                    "invalid-kind",
                    f"kind {name!r} declares {item} as {value!r}, which is not true or false",
                    fix=f"write true or false under kinds.{name}.{item}",
                )
            values[item] = value
        else:
            values[item] = str(value)
        source[item] = DECLARED

    return Resolved(profile=Profile(name=name, **{**_asdict(base), **values}), source=source)


def _asdict(profile: Profile) -> dict[str, Any]:
    return {item: getattr(profile, item) for item in FIELDS}


def every(workspace: Workspace | None) -> dict[str, Resolved]:
    """Every kind available here, built-in and declared (R2.1)."""
    stated = declared(workspace)
    names = sorted(set(BUILT_INS) | set(stated))
    return {name: merge(name, stated.get(name) or {}) for name in names}


def resolve(name: str, workspace: Workspace | None) -> Resolved:
    """One kind, or a refusal naming the kinds there are (R2.4).

    The name is checked before it is looked up, so that `../../../escaped` stays the
    `invalid-name` it has always been rather than becoming an `unknown-kind`. Both refuse,
    but a caller reading the code should be told which of the two things went wrong — and
    `workspace-foundation`'s own escape tests assert the first one.
    """
    check_name(name, "kind")
    available = every(workspace)
    if name not in available:
        raise UsageError(
            "unknown-kind",
            f"no kind {name!r} here; there is: {', '.join(sorted(available))}",
            fix="ssc kind list, or declare it under kinds: in ssc.yaml",
        )
    return available[name]
