"""The one pipeline behind every paid command.

`gen image`, `gen video`, `gen expand` and `gen bgremove` differ in which model they choose,
which core options they set and whether they carry an image. Everything after that is the
same seven steps — resolve the asset and its kind, choose the model, build the call, check it
against the schema, look in the cache, submit through `jobs.submit`, collect and file — and
they are here rather than four times over in `commands/gen.py`. The plan names the failure
that would be: building against the character case and generalising later, by which time the
template has hardened into the signature.
"""

from __future__ import annotations

import json
import math
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from ssc.cli import budget, config, fal, jobs, kinds, listing, meta, models
from ssc.cli.atomic import Directory
from ssc.cli.cache import Cache, cache_key
from ssc.cli.errors import SscError, UsageError
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace

#: How far a model's nearest shape may be from the one asked for before this refuses.
#:
#: A judgement rather than a measurement, and `specs/gen-fal/design.md` says so. What makes
#: the number defensible is the asymmetry: accepting a stretch costs money *and* produces art
#: that reads as wrong at 4x zoom, while refusing costs a caller one message they can act on
#: — lay the board out 3x2, or generate the cells one at a time.
MAX_STRETCH = 0.15

#: Aspect is what cannot be fixed after the fact; scale can, because `core.resize()` exists
#: and nearest neighbour is this project's only resampler. So a request larger than every
#: tier a model offers is reported rather than refused, and a shape it cannot make is refused.
TIER_SUFFIXES = ("k", "p")


@dataclass(frozen=True)
class Size:
    """What to put in the call, and what a caller needs to see about that choice (R3.1)."""

    fields: dict[str, Any]
    report: dict[str, Any]


def _stretch(wanted: float, offered: float) -> float:
    """How far one aspect ratio is from another, symmetrically.

    `max(a/b, b/a) - 1` rather than a difference: 2:1 against 1:1 and 1:1 against 2:1 are the
    same mistake, and a plain subtraction says they are not.
    """
    if wanted <= 0 or offered <= 0:
        return math.inf
    return max(wanted / offered, offered / wanted) - 1.0


def _parse_size(text: str) -> tuple[int, int] | None:
    parts = text.lower().split("x")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        return None
    width, height = int(parts[0]), int(parts[1])
    return (width, height) if width > 0 and height > 0 else None


def _parse_ratio(text: str) -> tuple[int, int] | None:
    parts = text.split(":")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        return None
    width, height = int(parts[0]), int(parts[1])
    return (width, height) if width > 0 and height > 0 else None


def _tier(name: str) -> tuple[float, str] | None:
    """A resolution tier as a number and the side it is about.

    `1K` is about the long side and `720p` is about the short one — the two families this
    project's models use, and they mean different sides. Reading both as "the size" is how a
    16:9 request at `720p` would come back at 720 wide.
    """
    text = name.strip().lower()
    if not text or text[-1] not in TIER_SUFFIXES:
        return None
    try:
        value = float(text[:-1])
    except ValueError:
        return None
    if value <= 0:
        return None
    return (value * 1024, "long") if text[-1] == "k" else (value, "short")


def _allowed_of(model: models.Model, field: str) -> list[Any]:
    option = model.options.get(field)
    if option is None:
        raise SscError(
            "size-unknown",
            f"{model.endpoint} is recorded as taking a size in {field!r} and has no such field",
            fix="the registry and the schema disagree; ssc model show reports the schema",
        )
    return [value for value in (option.allowed or []) if isinstance(value, str)]


def _nearest(
    endpoint: str,
    field: str,
    wanted: float,
    candidates: list[tuple[str, tuple[int, int]]],
) -> tuple[str, tuple[int, int], float]:
    """The offered shape closest to the one asked for, or a refusal naming what is offered.

    Ties break towards the earlier candidate, which is the order the model's own schema lists
    them in — an arbitrary rule applied consistently beats one that depends on dict order.
    """
    if not candidates:
        raise SscError(
            "size-unknown",
            f"{endpoint}.{field} enumerates no size this build can read",
            fix=f"ssc model show {endpoint}",
        )

    best_name, best_shape, best_stretch = min(
        ((name, shape, _stretch(wanted, shape[0] / shape[1])) for name, shape in candidates),
        key=lambda found: found[2],
    )
    if best_stretch > MAX_STRETCH:
        offered = ", ".join(name for name, _ in candidates)
        raise UsageError(
            "size-unrepresentable",
            f"{endpoint} cannot make that shape: the nearest it offers stretches it by "
            f"{best_stretch:.0%}",
            fix=f"it offers {offered} — lay the board out to one of those, or generate "
            "the cells one at a time",
        )
    return best_name, best_shape, best_stretch


def reconcile_size(
    registry: models.Registry, endpoint: str, requested: tuple[int, int] | None
) -> Size | None:
    """The size a layout needs, in the shape this model asks the question in (R3.1, R3.2).

    Three shapes, because the models disagree about the question and not merely the spelling:
    an enum of literal sizes on GPT Image 1.5, an aspect ratio plus a resolution tier on the
    other two, and nothing at all on BiRefNet. `docs/wiki/model-parameters.md` measured that,
    and `model-registry` records it as the shape rather than as a field name.

    `None` back means nothing to set: a caller who did not ask for a size gets the model's own
    default rather than this project's opinion of one.
    """
    if requested is None:
        return None

    width, height = requested
    if width <= 0 or height <= 0:
        raise UsageError(
            "invalid-size",
            f"{width}x{height} is not a size",
            fix="write it as WxH, in pixels — ssc tool board reports the one a layout needs",
        )

    shape = registry.size_of(endpoint)
    if shape is None:
        raise UsageError(
            "no-size",
            f"{endpoint} does not take a size",
            fix="drop --size; this model's output follows its input",
        )

    model = registry.get(endpoint)
    wanted = width / height
    asked = f"{width}x{height}"

    if isinstance(shape, str):
        # A model whose size is one plain field. None of the four are today; the registry
        # records a field name rather than a shape when one is, and refusing that here would
        # be this code deciding what the registry is allowed to say.
        return Size(
            fields={shape: asked},
            report={"requested": asked, "chosen": asked, "aspect_error": 0.0},
        )

    # `form`, not `kind`: an asset's kind is a different thing entirely, and the two words
    # meeting in one function is how the confusion starts.
    form = shape.get("kind") if isinstance(shape, dict) else None
    if form == "enum":
        field = str(shape["field"])
        candidates = [
            (name, parsed)
            for name in _allowed_of(model, field)
            if (parsed := _parse_size(name)) is not None
        ]
        name, _, stretch = _nearest(endpoint, field, wanted, candidates)
        return Size(
            fields={field: name},
            report={"requested": asked, "chosen": name, "aspect_error": round(stretch, 4)},
        )

    if form == "ratio":
        ratio_field = str(shape["ratio_field"])
        resolution_field = str(shape["resolution_field"])
        candidates = [
            (name, parsed)
            for name in _allowed_of(model, ratio_field)
            if (parsed := _parse_ratio(name)) is not None
        ]
        ratio, _, stretch = _nearest(endpoint, ratio_field, wanted, candidates)
        tier, below = _tier_for(model, resolution_field, requested)
        return Size(
            fields={ratio_field: ratio, resolution_field: tier},
            report={
                "requested": asked,
                "chosen": f"{ratio} at {tier}",
                "aspect_error": round(stretch, 4),
                # Named rather than implied: a caller who asked for 8000px and is getting 4K
                # has to be able to see that before they measure the result and wonder.
                "below_request": below,
            },
        )

    raise SscError(
        "size-unknown",
        f"the registry records a size shape for {endpoint} this build does not know: {shape!r}",
        fix="upgrade ssc, or drop --size",
    )


def _tier_for(model: models.Model, field: str, requested: tuple[int, int]) -> tuple[str, bool]:
    """The smallest tier that covers the request, or the largest there is.

    Below the request is a report and not a refusal — see `TIER_SUFFIXES` above for why scale
    and aspect are not the same kind of compromise.
    """
    width, height = requested
    tiers = [
        (name, parsed) for name in _allowed_of(model, field) if (parsed := _tier(name)) is not None
    ]
    if not tiers:
        raise SscError(
            "size-unknown",
            f"{model.endpoint}.{field} enumerates no resolution this build can read",
            fix=f"ssc model show {model.endpoint}",
        )

    covering = [
        (name, value)
        for name, (value, side) in tiers
        if value >= (max(width, height) if side == "long" else min(width, height))
    ]
    if covering:
        return min(covering, key=lambda found: found[1])[0], False
    return max(tiers, key=lambda found: found[1][0])[0], True


# ---------------------------------------------------------------- the prompt


#: The template `gen video` uses, whatever the asset's kind. A video is animation applied to
#: an image that already exists, so the kind has already had its say — and the plan is
#: explicit that `gen video` has one template and never passes a board.
VIDEO_TEMPLATE = "video"


def templates() -> dict[str, str]:
    document: dict[str, Any] = json.loads(
        resources.files("ssc.data").joinpath("templates.json").read_text(encoding="utf-8")
    )
    found = document.get("templates")
    if not isinstance(found, dict):
        raise SscError("templates-invalid", "the shipped templates.json declares no templates")
    return {str(name): str(text) for name, text in found.items()}


#: The named slots a template may carry, and the whole of them. A closed vocabulary rather
#: than free-form keys: these are the parameters that recur across the character templates
#: and are worth being structured about, and an open set would drift into a second prompt
#: language nobody documents. Anything else is prose, and prose goes in `--prompt`.
VARIABLES = (
    "name",
    "archetype",
    "costume",
    "prop",
    "silhouette",
    "setting",
    "direction",
    "remove",
)


#: Every token a template may carry, the eight named slots plus the three the pipeline fills
#: itself. One expression, because the substitution is one pass — see `prompt_for`.
SLOT = re.compile(r"\{(" + "|".join([*VARIABLES, "width", "height", "prompt"]) + r")\}")


def parse_variables(pairs: tuple[str, ...]) -> dict[str, str]:
    """`--var key=value`, repeatable, and always text (R2.8).

    Unlike `--opt`, these never reach a model's schema — they are substituted into a prompt,
    so a value is a string and nothing else. `--var name=7` is a character called 7.
    """
    found: dict[str, str] = {}
    for pair in pairs:
        name, separator, raw = pair.partition("=")
        name = name.strip()
        if not separator or not name:
            raise UsageError(
                "invalid-variable",
                f"{pair!r} is not key=value",
                fix="write it as --var name=value, once per variable",
            )
        if SLOT.search(raw):
            # A value that is itself a placeholder is a substitution that failed upstream —
            # a script that built `--var name={name}` out of a config it could not read. It
            # passes the empty check, because it is not empty, and one pass of `re.sub` will
            # not expand it either. So it is refused here: `{name}` in a billed prompt is the
            # exact outcome R2.8 exists to prevent, and arriving by this route makes it no
            # less expensive.
            raise UsageError(
                "invalid-variable",
                f"--var {name} was given a value that is itself a template slot: {raw!r}",
                fix="something upstream did not substitute it; pass the real text",
            )
        if name not in VARIABLES:
            raise UsageError(
                "unknown-variable",
                f"{name!r} is not a prompt variable",
                fix=f"the variables are: {', '.join(VARIABLES)} — anything else goes in --prompt",
            )
        if name in found:
            raise UsageError(
                "invalid-variable",
                f"--var {name} was given more than once",
                fix="pass each variable once",
            )
        found[name] = raw
    return found


def wanted_by(body: str) -> list[str]:
    """The variables a template names, in the order a caller would read them."""
    return [name for name in VARIABLES if "{" + name + "}" in body]


def prompt_for(
    template: str,
    text: str,
    cell: tuple[int, int],
    variables: dict[str, str] | None = None,
) -> str:
    """The caller's prompt, wrapped in the template the kind named (R2.1, R2.8).

    Substituted rather than `format`ted, deliberately: a caller's prompt is arbitrary text and
    routinely holds a brace, and `str.format` would read it as a field and raise — turning a
    perfectly good prompt into an error nobody could explain.

    What a template still needs is worked out from the template, before the caller's text is
    anywhere near it. Somebody who writes "a knight {holding a torch}" is describing a knight,
    not naming a variable, and a check run against the finished string would refuse them.

    **The substitution is one pass, and that is a correctness property rather than a tidiness
    one.** Replacing slot by slot means each replacement can rewrite text an earlier one just
    inserted: with `--var name={prop}` the value of `prop` lands where `name` belongs, because
    `prop` happens to be substituted second. `re.sub` walks the template once and never
    revisits what it wrote, so a value is inserted exactly as given no matter what it holds
    and no matter what order the slots were supplied in.
    """
    available = templates()
    if template not in available:
        raise UsageError(
            "unknown-template",
            f"this asset's kind names the prompt template {template!r}, which ssc does not ship",
            fix=f"the templates are: {', '.join(sorted(available))}",
        )

    body = available[template]
    given = dict(variables or {})
    missing = [name for name in wanted_by(body) if not given.get(name, "").strip()]
    if missing:
        # Before the call rather than after, because what this prevents is the literal text
        # `{name}` reaching the model inside a prompt that is then paid for.
        raise UsageError(
            "missing-variable",
            f"the {template!r} template needs {', '.join(missing)}, "
            f"which {'was' if len(missing) == 1 else 'were'} not given",
            fix=" ".join(f"--var {name}=…" for name in missing),
        )

    width, height = cell
    filled = {**given, "width": str(width), "height": str(height), "prompt": text}
    return SLOT.sub(lambda found: filled.get(found.group(1), found.group(0)), body)


# ------------------------------------------------------------- what is asked


@dataclass(frozen=True)
class Image:
    """A local file on its way to a model that only takes URLs."""

    path: Path
    data: bytes
    content_type: str

    @property
    def digest(self) -> str:
        return meta.digest(self.data)

    def elided(self) -> dict[str, Any]:
        """How the job records it: named, not carried.

        A data URL is megabytes of base64. Written into `jobs/<id>.json` it would duplicate a
        file that is already on disk and make `ssc job list` unreadable, so the record names
        the bytes by digest instead. `jobs.save` scrubs credentials on the way in; this is the
        same instinct applied to bulk.
        """
        return {"sha256": self.digest, "bytes": len(self.data), "from": self.path.name}


#: What a caller may put in an image, by extension. Anything else is refused rather than sent
#: with a guessed content type: the model reads the type, and a PNG announced as a JPEG is a
#: paid call that fails at the far end.
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

#: What a produced file is called, read from the bytes rather than from the URL that carried
#: them. A model's `output_format` is an option a caller can change, so a result named from
#: the endpoint or from a query string is a name that can be a lie — and a `.png` holding
#: WebP is a file every later command opens and misreads.
MAGIC: tuple[tuple[int, bytes, str], ...] = (
    (0, b"\x89PNG\r\n\x1a\n", "png"),
    (0, b"\xff\xd8\xff", "jpg"),
    (0, b"GIF8", "gif"),
    (8, b"WEBP", "webp"),
    (4, b"ftyp", "mp4"),
)


def _content_type(path: Path) -> str:
    content_type = CONTENT_TYPES.get(path.suffix.lower())
    if content_type is None:
        raise UsageError(
            "unsupported-image",
            f"{path.name} is not a kind of image ssc sends to a model",
            fix=f"use one of: {', '.join(sorted(CONTENT_TYPES))}",
        )
    return content_type


def image_at(path: Path) -> Image:
    """The image at a loose path, for `--in`.

    A path is the whole of the answer here: `--in` names a file that is nobody's asset, so
    there is no checked directory to bind the read to.
    """
    content_type = _content_type(path)
    try:
        data = path.read_bytes()
    except OSError as unreadable:
        raise UsageError(
            "no-input", f"{path} could not be read: {unreadable}", fix="check the path"
        ) from unreadable
    return Image(path=path, data=data, content_type=content_type)


def image_in(held: Directory, relative: str) -> Image:
    """The image a stage names, read through the directory that was checked (R3.7).

    The counterpart of `image_at` for a file inside an asset, and the same split
    `frames.decode_image` makes against `frames.load_image`: what is sent to a model that
    bills has to be what was read through the binding rather than whatever the path
    resolves to a statement later. `--from-stage` addresses a file the record names, so the
    asset directory is already held — re-opening it by path would drop the binding between
    resolving the address and paying for what it produced.
    """
    content_type = _content_type(Path(relative))
    try:
        data = held.read(relative)
    except OSError as unreadable:
        raise UsageError(
            "no-input",
            f"{relative} could not be read: {unreadable}",
            fix="check that the stage still names a file",
        ) from unreadable
    return Image(path=Path(relative), data=data, content_type=content_type)


@dataclass(frozen=True)
class Ask:
    """What a caller asked for, before any model is chosen.

    One shape for four verbs. What differs between them is which fields are set, which is the
    whole argument for a single pipeline: a verb is a set of defaults, not a separate program.
    """

    verb: str
    media: str
    stage: str
    prompt: str | None = None
    template: str | None = None
    image: Image | None = None
    seconds: int | None = None
    size: tuple[int, int] | None = None
    seed: int | None = None
    model: str | None = None
    role: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    upload: bool = False


@dataclass(frozen=True)
class Call:
    """A call that has passed the model's own schema, and what it costs to describe it.

    `checked` carries a placeholder where the image goes: the schema check is about types and
    a URL is a string whatever is in it, so the real reference is made at the last moment —
    after the cache has been consulted and the credential proved. Uploading art to a CDN to
    find out it was already cached is exactly the kind of thing this project does not do.
    """

    endpoint: str
    checked: dict[str, Any]
    recorded: dict[str, Any]
    inputs: tuple[str, ...]
    image_field: str | None = None
    image: Image | None = None
    template: str | None = None
    size: Size | None = None

    def arguments(self, url: str | None) -> dict[str, Any]:
        payload = dict(self.checked)
        if self.image_field is not None and url is not None:
            existing = payload.get(self.image_field)
            payload[self.image_field] = [url] if isinstance(existing, list) else url
        return payload

    def key(self) -> str:
        """R4.2 — the resolved call, the images, and the model as salt.

        The model id is salt rather than a parameter for `model-registry`'s reason: the same
        prompt against two models is two different results, and a cache that conflates them is
        worse than no cache at all.
        """
        return cache_key(
            "gen",
            params=self.recorded,
            inputs=list(self.inputs),
            salt={"model": self.endpoint},
        )

    def report(self) -> dict[str, Any]:
        return {
            "model": self.endpoint,
            "template": self.template,
            "arguments": self.recorded,
            "size": None if self.size is None else self.size.report,
            "cache_key": self.key(),
        }


PLACEHOLDER_URL = "https://placeholder.invalid/image"


def by_role(registry: models.Registry, role: str) -> str:
    """The one model that does this job, or a refusal that makes the caller pick.

    `registry.chosen` answers "which model for this media", which is the right question for
    generating and the wrong one for background removal: BiRefNet is an image model that makes
    an image, and taking `models.image` would send the call to whatever generates pictures.
    """
    found = sorted(model.endpoint for model in registry.models if model.role == role)
    if len(found) == 1:
        return found[0]
    if not found:
        raise SscError(
            "no-model-configured",
            f"no model in the registry does {role}",
            fix="name one with --model, or ssc model list",
        )
    raise UsageError(
        "ambiguous-model",
        f"more than one model does {role}: {', '.join(found)}",
        fix="name the one you want with --model",
    )


def endpoint_for(
    registry: models.Registry,
    ask: Ask,
    profile: kinds.Profile,
    settings: dict[str, Any],
) -> str:
    """Which model runs, and — when an image is passed — which of its endpoints (R2.6)."""
    if ask.model is not None:
        # Named on the command line. Checked against the registry rather than trusted, so a
        # typo is a refusal here instead of a bill from an endpoint nobody meant.
        endpoint = registry.get(ask.model).endpoint
    elif ask.role is not None:
        endpoint = by_role(registry, ask.role)
    else:
        from_kind = profile.image_model if ask.media == "image" else profile.video_model
        endpoint = registry.chosen(ask.media, config=settings, from_kind=from_kind or None)

    if ask.image is None or registry.core_for(endpoint).get("image"):
        return endpoint

    # Passing a reference image is a different endpoint, not a parameter — both image models
    # put it behind `/edit`. See `docs/wiki/model-parameters.md`.
    editing = f"{endpoint}/edit"
    if any(model.endpoint == editing for model in registry.models) and registry.core_for(
        editing
    ).get("image"):
        return editing
    raise UsageError(
        "no-edit-endpoint",
        f"{endpoint} takes no input image, and there is no {editing} in the registry",
        fix=f"name a model that does with --model, or ssc model list --media {ask.media}",
    )


def build(
    registry: models.Registry,
    ask: Ask,
    profile: kinds.Profile,
    settings: dict[str, Any],
) -> Call:
    """The call this ask becomes, checked against the model's schema (R2.1, R2.5, R2.6).

    Nothing here touches the network. That is what lets `--dry-run` report the whole resolved
    call, and what lets the cache be consulted before a byte is uploaded.
    """
    endpoint = endpoint_for(registry, ask, profile, settings)
    model = registry.get(endpoint)
    mapping = registry.core_for(endpoint)

    core: dict[str, Any] = {}
    template: str | None = None
    if ask.prompt is not None:
        template = ask.template or profile.template
        core["prompt"] = prompt_for(template, ask.prompt, profile.cell, ask.variables)
    if ask.seconds is not None:
        core["seconds"] = ask.seconds
    if ask.seed is not None:
        # Not dropped when the model has no seed: `registry.resolve` refuses, because a caller
        # who asked for reproducibility and did not get it cannot find out except by running
        # twice and comparing.
        core["seed"] = ask.seed

    image_field: str | None = None
    if ask.image is not None:
        image_field = mapping.get("image")
        if not isinstance(image_field, str):
            # Not reachable through `endpoint_for`, which has already resolved to an endpoint
            # whose core mapping names an image field — or refused with `no-edit-endpoint`.
            # It stays because it is the check that makes that guarantee local: a registry
            # whose `image` is truthy and not a string would otherwise put a non-name into
            # the payload of a call that bills. Kept as a belt, and said to be one.
            raise UsageError(
                "no-image-option",
                f"{endpoint} takes no input image",
                fix=f"ssc model show {endpoint}",
            )
        option = model.options.get(image_field)
        placeholder: Any = (
            [PLACEHOLDER_URL] if option is not None and option.type == "array" else PLACEHOLDER_URL
        )
        core["image"] = placeholder

    size = reconcile_size(registry, endpoint, ask.size)
    options = dict(ask.options)
    if size is not None:
        clashing = sorted(set(options) & set(size.fields))
        if clashing:
            raise UsageError(
                "size-conflict",
                f"--size already sets {', '.join(clashing)} on {endpoint}",
                fix=f"drop --size, or drop --opt {clashing[0]}=…",
            )
        options.update(size.fields)

    checked = registry.resolve(endpoint, core=core, options=options)
    recorded = dict(checked)
    if image_field is not None and ask.image is not None:
        # The shape is kept — a list stays a list — so the record reads as the call that was
        # made rather than as a differently shaped summary of it.
        elided = ask.image.elided()
        recorded[image_field] = [elided] if isinstance(checked.get(image_field), list) else elided

    return Call(
        endpoint=endpoint,
        checked=checked,
        recorded=recorded,
        inputs=() if ask.image is None else (ask.image.digest,),
        image_field=image_field,
        image=ask.image,
        template=template,
        size=size,
    )


def parse_options(pairs: tuple[str, ...]) -> dict[str, Any]:
    """`--opt key=value`, repeatable, with the value read as JSON where it looks like it.

    `--opt num_images=2` has to reach the model as a number and `--opt system_prompt=2 cats`
    as text, and the model's schema is what decides which — so this only reads the obvious
    JSON scalars and leaves everything else a string. `registry.check` is what refuses a type
    the model does not want, with the schema in hand.
    """
    found: dict[str, Any] = {}
    for pair in pairs:
        name, separator, raw = pair.partition("=")
        if not separator or not name.strip():
            raise UsageError(
                "invalid-option",
                f"{pair!r} is not key=value",
                fix="write it as --opt name=value, once per option",
            )
        name = name.strip()
        if name in found:
            raise UsageError(
                "invalid-option",
                f"--opt {name} was given more than once",
                fix="pass each option once",
            )
        try:
            value = json.loads(raw)
            if not isinstance(value, (int, float, bool)) or isinstance(value, str):
                value = raw
        except ValueError:
            value = raw
        found[name] = value
    return found


# ------------------------------------------------------- submitting and filing


#: How long `gen` waits for a job before handing the id back. The work is minutes, not
#: seconds, and a command that never returns is indistinguishable from a hang inside a
#: harness — so this ends in a report rather than in a failure.
DEFAULT_TIMEOUT = 900.0
POLL_SECONDS = 3.0


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def job_id() -> str:
    """Sortable by time, unique without a registry, and a valid name.

    The random half is not decoration: two commands starting in the same second would
    otherwise write one job file, and the second would lose the first's request id.
    """
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(3)}"


def sniff(data: bytes) -> str | None:
    """What these bytes are, from their first few of them."""
    for offset, marker, suffix in MAGIC:
        if data[offset : offset + len(marker)] == marker:
            return suffix
    return None


def extension_for(url: str, data: bytes) -> str:
    """The name a collected file gets: the content first, the URL only as a fallback."""
    found = sniff(data)
    if found is not None:
        return found
    from_url = Path(url.split("?", 1)[0]).suffix.lstrip(".").lower()
    return from_url if from_url.isalnum() else "bin"


def file_into(
    held: Directory,
    record: meta.AssetMeta,
    data: bytes,
    *,
    stage: str,
    extension: str,
    provenance: meta.Provenance,
) -> str:
    """Write a collected result into the asset and record it as a `source` (R4.1).

    `source` is the class `ssc clean` must refuse to touch, and this is the reason that class
    exists: a generated file cost money and the model is not deterministic, so it is the one
    thing in a workspace that cannot be reproduced.
    """
    name = meta.filename(record.next_prefix(), record.key, [stage], extension)
    held.write_new(name, data)
    meta.record(
        record,
        path=name,
        stage=stage,
        file_class="source",
        data=data,
        produced_by=provenance,
    )
    meta.save(held, record)
    return name


def collect(
    workspace: Workspace,
    provider: fal.Fal,
    job: jobs.Job,
    *,
    timeout: float,
    poll: float,
) -> tuple[jobs.Job, dict[str, Any]]:
    """Wait for a job to finish, and return what it produced (R1.5).

    Every state the provider reports is written down as it happens: the process may die in
    this loop, and what is on disk is the only thing that survives it.
    """
    deadline = time.monotonic() + timeout
    while job.state not in jobs.TERMINAL:
        if job.request_id is None:
            raise SscError(
                "no-request-id",
                f"{job.id} has no request id, so it was never submitted",
                fix="ssc job list",
            )
        moved = job.to_state(provider.status(job.application, job.request_id), at=now())
        if moved is not job:
            jobs.save(workspace, moved)
            job = moved
        if job.state in jobs.TERMINAL:
            break
        if time.monotonic() >= deadline:
            raise SscError(
                "still-running",
                f"{job.id} is still {job.state} after {timeout:g}s, and it is paid for",
                fix=f"ssc job wait {job.id}, then ssc gen collect {job.id} --asset <kind>/<key>",
            )
        time.sleep(poll)

    if job.state != "done":
        raise SscError(
            "job-failed",
            f"{job.id} is {job.state}"
            + (f": {job.error}" if job.error else "")
            + " — nothing was written",
            fix=f"ssc job status {job.id}",
        )
    if job.request_id is None:  # pragma: no cover - a done job always has one
        raise SscError("no-request-id", f"{job.id} is done and has no request id")
    return job, provider.result(job.application, job.request_id)


def write_result(
    workspace: Workspace,
    address: str,
    payload: dict[str, Any],
    *,
    stage: str,
    provenance: meta.Provenance,
    cache: Cache | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    """Fetch what a finished call produced and file it into the asset (R1.5, R4.1, R4.2)."""
    url = fal.file_url(payload)
    data = fal.fetch(url)
    if cache is not None and key is not None:
        cache.put(key, data)

    held, record = listing.resolve(workspace, address)
    with held:
        name = file_into(
            held,
            record,
            data,
            stage=stage,
            extension=extension_for(url, data),
            provenance=provenance,
        )
    return {"file": name, "bytes": len(data), "url": url}


def run(
    workspace: Workspace,
    ask: Ask,
    address: str,
    *,
    provider: fal.Fal,
    registry: models.Registry | None = None,
    dry_run: bool = False,
    wait: bool = True,
    timeout: float = DEFAULT_TIMEOUT,
    poll: float = POLL_SECONDS,
) -> Result:
    """One paid command, from the ask to the file (R1.1, R1.2, R1.3, R1.4, R1.6, R4.3).

    The order of the last four steps is the whole leaf: check the cache before spending, prove
    the credential before recording a job, record the job before submitting, and file what
    came back as a `source`.
    """
    held, record = listing.resolve(workspace, address)
    with held:
        profile = kinds.resolve(record.kind, workspace).profile
        stages = tuple(entry.stage for entry in record.files)
    registry = models.load() if registry is None else registry
    settings = config.document(workspace)
    call = build(registry, ask, profile, settings)
    key = call.key()

    # First, and before the cache: it holds whether or not there is a ceiling and whether or
    # not anything is cached. A workspace that has declared no budget at all still should
    # not pay for a `np.pad` (`specs/budget-guard/` R1.1).
    free = budget.covered_by(ask, stages)
    limits = budget.limits_of(settings)

    if dry_run:
        return Result(
            ask.verb,
            f"would call {call.endpoint}",
            {
                "asset": address,
                "stage": ask.stage,
                "submitted": False,
                "free_path": None if free is None else free.command,
                **call.report(),
            },
            dry_run=True,
        )

    budget.clear(free)

    cache = Cache(workspace.cache)
    hit = cache.get(key)
    if hit is not None:
        held, record = listing.resolve(workspace, address)
        with held:
            name = file_into(
                held,
                record,
                hit,
                stage=ask.stage,
                # The bytes are the same bytes, so the name is the same name: `extension_for`
                # reads the content, which is why a cached result does not need the URL that
                # originally carried it.
                extension=extension_for("", hit),
                provenance=meta.Provenance(command=ask.verb, params=call.recorded, cache_key=key),
            )
        return Result(
            ask.verb,
            f"{name} from the cache; nothing was submitted",
            {
                "asset": address,
                "stage": ask.stage,
                "submitted": False,
                "file": name,
                **call.report(),
            },
            cached=True,
        )

    # After the cache and before the credential. A cache hit submits nothing, so refusing
    # one for being over budget would be refusing to spend nothing (R2.2).
    warning = budget.check(limits, budget.load(workspace), budget.estimate_for(registry, call))

    # Before the job record, so a call that was never going to happen leaves no trace of
    # having been attempted.
    fal.credential()

    url = None
    if call.image is not None:
        url = provider.reference(call.image.data, call.image.content_type, upload=ask.upload)

    job = jobs.Job.new(
        id=job_id(),
        provider=fal.PROVIDER,
        application=call.endpoint,
        model=call.endpoint,
        arguments=call.recorded,
        at=now(),
        # Carried so that `gen collect` can store what it collects under the same key this
        # call would have stored it under. Recomputing it there is not possible from the
        # record alone — the key covers the digests of the images sent, which the record
        # elides — and a result collected under no key is a result the next identical call
        # pays for again.
        cache_key=key,
    )
    arguments = call.arguments(url)
    job = jobs.submit(workspace, job, lambda _: provider.submit(call.endpoint, arguments), at=now())
    # Here, not after collecting. The money is committed the moment `submit` returns, and a
    # caller who never collects — `--no-wait` in a loop — would otherwise bill the provider
    # while the ceiling compared against a total that never moved (R3.2).
    total, job = budget.count(workspace, job)

    if not wait:
        return Result(
            ask.verb,
            f"{job.id} submitted to {call.endpoint}",
            {
                "asset": address,
                "stage": ask.stage,
                "submitted": True,
                "collected": False,
                "job": job.as_dict(),
                "budget": total.as_dict(),
                **call.report(),
            },
        )

    job, payload = collect(workspace, provider, job, timeout=timeout, poll=poll)
    # After the call and not before it: the estimate is what a refusal is made on, and this
    # is what was actually spent (R2.5, R3.2). A provider that priced nothing is counted as
    # unpriced rather than as free.
    total, job = budget.settle(workspace, job, job.cost_usd)
    written = write_result(
        workspace,
        address,
        payload,
        stage=ask.stage,
        provenance=meta.Provenance(
            command=ask.verb, params={**call.recorded, "job": job.id}, cache_key=key
        ),
        cache=cache,
        key=key,
    )
    return Result(
        ask.verb,
        f"{written['file']} from {call.endpoint}"
        + (f" — {warning}" if warning is not None else ""),
        {
            "asset": address,
            "stage": ask.stage,
            "submitted": True,
            "collected": True,
            "job": job.as_dict(),
            "budget": total.as_dict(),
            "warning": warning,
            **written,
            **call.report(),
        },
    )


def collect_job(
    workspace: Workspace,
    job_name: str,
    address: str,
    *,
    provider: fal.Fal,
    stage: str,
    dry_run: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    poll: float = POLL_SECONDS,
) -> Result:
    """`ssc gen collect` — file an already-paid result, from the id alone (R1.5).

    The destination comes from the caller rather than from the record on purpose: a job is a
    provider-shaped pair of identifiers, and putting a workspace path in it would be the first
    thing a second provider could not honour. See `specs/gen-fal/design.md`.
    """
    record = jobs.load(workspace, job_name)
    if dry_run:
        return Result(
            "gen collect",
            f"would collect {record.id} into {address}",
            {"asset": address, "stage": stage, "collected": False, "job": record.as_dict()},
            dry_run=True,
        )

    record, payload = collect(workspace, provider, record, timeout=timeout, poll=poll)
    # Counted here as well as in `run`, and idempotently. `--no-wait` then `gen collect` is
    # an ordinary supported sequence, and counting only where `gen` waited meant a caller who
    # used it submitted billed work the ceiling never saw (R3.2).
    # Counted at submission; this only folds in a price, if the provider gave one.
    total, record = budget.settle(workspace, record, record.cost_usd)
    # Under the key the submitting call computed, which the job carried here. `--no-wait` then
    # `gen collect` has to leave the workspace in the state waiting would have: without this,
    # the result is filed but never cached, and the next identical `gen image` misses and
    # bills a second time for a result already sitting in the asset (R1.6).
    cache = Cache(workspace.cache)
    written = write_result(
        workspace,
        address,
        payload,
        stage=stage,
        provenance=meta.Provenance(
            command="gen collect",
            params={"job": record.id, "model": record.model},
            cache_key=record.cache_key,
        ),
        cache=None if record.cache_key is None else cache,
        key=record.cache_key,
    )
    return Result(
        "gen collect",
        f"{written['file']} from {record.id}",
        {
            "asset": address,
            "stage": stage,
            "collected": True,
            "job": record.as_dict(),
            "budget": total.as_dict(),
            **written,
        },
    )
