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

from ssc.cli import config
from ssc.cli.errors import SscError, UsageError
from ssc.cli.names import check_name
from ssc.cli.sidecar import DEFAULT_FPS, MAX_FPS
from ssc.cli.workspace import Workspace
from ssc.core.assemble import ANCHOR_MODES

BUILT_IN = "built-in"
DECLARED = "ssc.yaml"

#: Imported rather than retyped. It was a fourth hand-written copy of a list that already
#: appears twice in `recover.py`'s `click.Choice` and is implied by `assemble.py`'s if/elif —
#: a value that must match between places, which is the defect class this project keeps
#: hitting. One definition, in the module that implements it.
ANCHORS = ANCHOR_MODES

#: What `atlas-packing` will know how to do. Declared here because the field is declared
#: here; a layout nobody implements is a promise to a caller that nothing keeps.
LAYOUTS = ("grid", "bin")


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
    #: The frame rate an animation of this kind plays at where its own `asset.yaml` does not
    #: say — `specs/engine-index/` R4.2. On the profile rather than in `ssc.yaml` at large
    #: because a project's icons and its characters do not animate at one speed.
    fps: int = DEFAULT_FPS
    atlas_layout: str = "grid"
    checks: tuple[str, ...] = ()
    template: str = "generic"
    normal_map: bool = False
    layered: bool = False
    image_model: str = ""
    video_model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cell": {"width": self.cell[0], "height": self.cell[1]},
            "anchor": self.anchor,
            "animates": self.animates,
            "fps": self.fps,
            "atlas_layout": self.atlas_layout,
            "checks": list(self.checks),
            "template": self.template,
            "normal_map": self.normal_map,
            "layered": self.layered,
            "image_model": self.image_model,
            "video_model": self.video_model,
        }


#: The seven the package ships. Defaults, not a frozen table — a project may override any of
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
    "background": Profile(
        name="background",
        cell=(320, 180),
        anchor="centre",
        atlas_layout="bin",
        checks=("palette",),
        template="background",
        layered=True,
    ),
    "map": Profile(
        name="map",
        cell=(128, 128),
        anchor="centre",
        atlas_layout="bin",
        checks=("palette",),
        template="map",
    ),
    # The one kind that is not a game asset. Box art is the roster and character-select
    # illustration: painterly, on its own background, at a size no cell ever is. It is here
    # because a character's art is generated somewhere, and the alternative was a second
    # command that bills — which is the shape `gen image` exists to avoid.
    #
    # `checks` is empty because none of them apply: every check `doctor` ships measures a
    # property of a pixel-art sprite — `pixel_grid` wants real pixels, `palette` a bounded
    # set of colours, `halo` and `bleed` a cut-out on chroma — and a rendered illustration
    # is deliberately none of those.
    #
    # **Stating what that does and does not buy today.** `doctor` reads this field to decide
    # whether `seam` and `nineslice` run, and nothing else: the other seven run whatever the
    # kind says. So an empty tuple opts out of two checks and does not stop `pixel_grid`
    # reporting a painterly portrait as off-grid. That is a gap between what
    # `specs/asset-kinds/` R1.1 says this field means — "the checks that apply to it" — and
    # what `doctor` does with it, and it is not this kind's to close: every kind has it, and
    # `banner`'s `checks=("palette",)` does not suppress `pixel_grid` either.
    #
    # It is never packed, so `atlas_layout` keeps the default rather than claiming one.
    "box-art": Profile(
        name="box-art",
        cell=(1024, 1536),
        checks=(),
        template="box-art",
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
    """The `kinds:` map from `ssc.yaml`, or nothing outside a workspace.

    The read itself is `config.document`. It moved there when `models:` became the second
    setting read from this file: two readers would mean two ceilings, two loaders and two
    answers to what a malformed config does, which is the divergence this project has
    already paid for once elsewhere. What stays here is the part that is about kinds.
    """
    if workspace is None:
        # `config.document` answers the same for `None`; this is here so the refusals below
        # can name the file they are about, which outside a workspace does not exist.
        return {}

    found = config.document(workspace).get("kinds")
    if found is None:
        return {}
    # Not `or {}`: that short-circuits on every falsy wrong type — `kinds: 0`, `kinds: ""`,
    # `kinds: []` — and reports "no kinds declared" for a file that plainly declares
    # something. A validate-on-read promise silently not kept is worse than no promise.
    if not isinstance(found, dict):
        raise SscError(
            "invalid-config",
            f"{workspace.config_path} declares `kinds` as {type(found).__name__}, not a map",
            fix="write it as a map of name to profile",
        )

    # YAML keys are not necessarily strings — `123:` and `true:` are both valid — and a
    # non-string key blew up later at `sorted(...)` and at `", ".join(...)`, past the point
    # where `check_name` would have refused it. Both levels are checked here, once.
    for key, value in found.items():
        if not isinstance(key, str):
            raise SscError(
                "invalid-config",
                f"{workspace.config_path} declares a kind named {key!r}, which is not a name",
                fix="quote it, or use letters, digits, dot, dash or underscore",
            )
        if isinstance(value, dict):
            for item in value:
                if not isinstance(item, str):
                    raise SscError(
                        "invalid-kind",
                        f"kind {key!r} declares a field named {item!r}, which is not a name",
                        fix=f"a profile has: {', '.join(sorted(FIELDS))}",
                    )
    return found


def merge(name: str, stated: dict[str, Any]) -> Resolved:
    """One kind's profile, field by field, with where each field came from (R1.3, R1.4).

    A declaration naming a built-in overrides it field by field rather than replacing it: a
    project that sets `character`'s cell and nothing else keeps the anchor, the checks and
    the template it did not mention.
    """
    check_name(name, "a kind")
    if not isinstance(stated, dict):
        # A kind whose declaration is a scalar or a list. Guarded before `set(stated)`,
        # which raises a bare TypeError on both — and `cli/main.py` catches only SscError,
        # so that left the command as a traceback rather than as the refusal R1.5 promises.
        raise SscError(
            "invalid-kind",
            f"kind {name!r} is declared as {type(stated).__name__}, not a map of fields",
            fix=f"write kinds.{name} as a map, or remove it",
        )
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
        elif item == "fps":
            values[item] = check_fps(value, name)
        elif item in {"animates", "normal_map", "layered"}:
            if not isinstance(value, bool):
                raise SscError(
                    "invalid-kind",
                    f"kind {name!r} declares {item} as {value!r}, which is not true or false",
                    fix=f"write true or false under kinds.{name}.{item}",
                )
            values[item] = value
        else:
            values[item] = check_text(item, value, name)
        source[item] = DECLARED

    return Resolved(profile=Profile(name=name, **{**_asdict(base), **values}), source=source)


def check_fps(value: Any, name: str) -> int:
    """A frame rate on a profile, held to the same range the sidecar holds one to.

    `bool` is an `int` in Python, so `fps: true` would otherwise resolve to one frame per
    second — the same trap `sidecar._fps` guards, and the reason both take the range from one
    definition rather than from two.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise SscError(
            "invalid-kind",
            f"kind {name!r} declares fps {value!r}, which is not a whole number",
            fix=f"write a number of frames per second under kinds.{name}.fps",
        )
    if value < 1 or value > MAX_FPS:
        raise SscError(
            "invalid-kind",
            f"kind {name!r} declares fps {value}, outside 1 to {MAX_FPS}",
            fix=f"write a number of frames per second under kinds.{name}.fps",
        )
    return value


def check_text(item: str, value: Any, name: str) -> str:
    """A field that is a name: a string, and one of the set where there is a set.

    Coercing with `str()` accepted a nested map, a null and a boolean alike — and an
    `anchor: cetnre` accepted here falls through to centre behaviour in whichever leaf reads
    it, which is the failure this whole validate-on-read design claims to prevent.
    """
    if not isinstance(value, str):
        raise SscError(
            "invalid-kind",
            f"kind {name!r} declares {item} as {type(value).__name__}, not a name",
            fix=f"write a name under kinds.{name}.{item}",
        )
    allowed = {"anchor": ANCHORS, "atlas_layout": LAYOUTS}.get(item)
    if allowed is not None and value not in allowed:
        raise SscError(
            "invalid-kind",
            f"kind {name!r} declares {item} {value!r}; it is one of {', '.join(allowed)}",
            fix=f"use one of {', '.join(allowed)} under kinds.{name}.{item}",
        )
    return value


def _asdict(profile: Profile) -> dict[str, Any]:
    return {item: getattr(profile, item) for item in FIELDS}


def every(workspace: Workspace | None) -> dict[str, Resolved]:
    """Every kind available here, built-in and declared (R2.1)."""
    stated = declared(workspace)
    names = sorted(set(BUILT_INS) | set(stated))
    # `.get(name, {})`, not `.get(name) or {}` — the identical short-circuit was removed
    # from `declared` in the same commit that left it here, one function away. A falsy
    # wrong type (`character: 0`) became `{}` and resolved silently to the built-in
    # defaults, so `merge`'s own isinstance guard never fired.
    return {name: merge(name, stated.get(name, {})) for name in names}


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
