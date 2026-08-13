"""What each model accepts, and the check that runs before anything is paid for.

An unknown option is a money leak rather than an error: type `--opt guidance_scale=7` at a
model whose field is `cfg` and the call succeeds, the parameter is dropped, the job is
billed, and the image is plausible enough that nobody notices it ignored you.

The schema is read from the provider and the copy in `data/models.json` is the fallback —
never the source. A registry hard-coded in the package is stale the week after Fal adds a
model, and stale quietly. `docs/wiki/model-parameters.md` records what those schemas
actually say.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from ssc.cli.errors import SscError, UsageError

#: The concepts that genuinely exist across models, under one name each. Everything else goes
#: through raw and is checked against the schema. Normalising more would mean owning a
#: translation table that goes stale silently; normalising none would push per-model
#: divergence into every skill and template.
#:
#: `count`, `quality` and `format` earned a name for a reason that is not symmetry
#: (`specs/model-options/` R3.1): they are the three an agent has to be *told about* to use at
#: the right moment, and `count` is the one that multiplies what a call costs.
CONCEPTS = ("prompt", "image", "seconds", "size", "seed", "count", "quality", "format")

#: Fal serves one of these per endpoint, unauthenticated.
SCHEMA_URL = "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={endpoint}"

#: A schema document is tens of kilobytes. `read()` with no argument is how a response that
#: is hostile — or merely enormous — becomes this process's memory.
MAX_SCHEMA_BYTES = 4 * 1024 * 1024

#: Per socket operation, not wall clock: a server trickling a byte every nine seconds keeps
#: every `recv` under this and never finishes. `MAX_FETCH_SECONDS` is what bounds that.
SOCKET_TIMEOUT = 10.0

#: How long one fetch may take in total. This is the one that stops the trickle: the read is
#: chunked and abandoned when this elapses, because a check *before* the call cannot
#: interrupt a call already in progress, however tightly it is set.
MAX_FETCH_SECONDS = 10.0

#: And this bounds the *set* — six models is six fetches, so a budget per call is a minute of
#: hanging on a command that only reads a schema. It skips fetches not yet started; the one
#: above is what bounds the one that has.
FETCH_BUDGET_SECONDS = 20.0

#: No model has hundreds of options. A live schema past this is not a model's input schema.
MAX_PROPERTIES = 200

Fetcher = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True)
class Option:
    """One field a model accepts, as its own schema describes it."""

    name: str
    type: str | None = None
    default: Any = None
    allowed: list[Any] | None = None
    minimum: float | None = None
    maximum: float | None = None
    required: bool = False
    description: str = ""

    #: Whether the field also takes an object — `specs/model-options/` R2.2. GPT Image 2's
    #: `image_size` is `anyOf: [$ref ImageSize, enum of seven presets]`, so `type` reads as
    #: `string` and `allowed` as those presets, and `{"width": …, "height": …}` would be
    #: refused as not one of them. The `$ref` is not followed: what bounds the value is the
    #: pixels size shape in `core.json`, not the shape inside the ref.
    objects: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "type": self.type, "required": self.required}
        if self.objects:
            payload["objects"] = True
        if self.default is not None:
            payload["default"] = self.default
        if self.allowed is not None:
            payload["allowed"] = self.allowed
        if self.minimum is not None:
            payload["minimum"] = self.minimum
        if self.maximum is not None:
            payload["maximum"] = self.maximum
        if self.description:
            payload["description"] = self.description
        return payload


@dataclass(frozen=True)
class Model:
    endpoint: str
    media: str
    role: str
    provider: str
    options: dict[str, Option] = field(default_factory=dict)

    #: `provider` or `package` — R1.5. A caller debugging a rejected option needs to know
    #: whether it was checked against today's schema or last release's.
    source: str = "package"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.endpoint,
            "media": self.media,
            "role": self.role,
            "provider": self.provider,
            "source": self.source,
            "options": [option.as_dict() for option in self.options.values()],
        }


def _type_of(schema: dict[str, Any]) -> str | None:
    """The type, seeing through `anyOf: [T, null]`.

    That shape is a schema saying "a T, optional". Reading it as "no type" would make every
    value valid for `seed`, which is exactly the field a caller most wants checked.
    """
    if "type" in schema:
        return str(schema["type"])
    for branch in schema.get("anyOf", []):
        if isinstance(branch, dict) and branch.get("type") not in (None, "null"):
            return str(branch["type"])
    return None


def _objects(schema: dict[str, Any]) -> bool:
    """Whether an object is one of the things this field accepts (R2.2).

    A `$ref` branch counts without being followed: every object shape Fal offers is served as
    a ref, and the branch existing is the whole fact needed here.
    """
    if schema.get("type") == "object" or "$ref" in schema:
        return True
    return any(
        isinstance(branch, dict) and (branch.get("type") == "object" or "$ref" in branch)
        for branch in schema.get("anyOf", [])
    )


def _allowed(schema: dict[str, Any]) -> list[Any] | None:
    if "enum" in schema:
        return list(schema["enum"])
    for branch in schema.get("anyOf", []):
        if isinstance(branch, dict) and "enum" in branch:
            return list(branch["enum"])
    return None


def _options(schema: dict[str, Any]) -> dict[str, Option]:
    required = set(schema.get("required") or [])
    found: dict[str, Option] = {}
    for name, described in (schema.get("properties") or {}).items():
        if not isinstance(described, dict):
            continue
        found[name] = Option(
            name=name,
            type=_type_of(described),
            default=described.get("default"),
            allowed=_allowed(described),
            minimum=described.get("minimum"),
            maximum=described.get("maximum"),
            required=name in required,
            description=str(described.get("description") or ""),
            objects=_objects(described),
        )
    return found


def _shipped(name: str) -> dict[str, Any]:
    text = resources.files("ssc.data").joinpath(name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def input_schema_of(document: dict[str, Any], endpoint: str) -> dict[str, Any] | None:
    """The request-body schema for this endpoint, followed rather than guessed.

    `scripts/fetch_model_schemas.py` already walks `paths → post → requestBody → $ref`, and
    that is the algorithm because the shortcut is wrong: `components.schemas` on a real
    FastAPI document holds `HTTPValidationError` and `ValidationError` too, both of which
    have `properties` and one of which sorts first. Taking the first match returns the
    error schema, `load` marks it authoritative, and every real option is then "unknown" —
    a failure that only appears when the network is *reachable*, which is the normal case.
    """
    try:
        path = document["paths"][f"/{endpoint}"]
        ref = path["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        found = document["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    except (KeyError, TypeError, AttributeError):
        return None
    return found if isinstance(found, dict) and "properties" in found else None


def plausible(schema: dict[str, Any]) -> bool:
    """Whether a live schema is worth believing over the shipped one.

    The fetched schema *is* the acceptance check that stops a money leak, so a response that
    is empty or absurd is a reason to fall back rather than a new set of rules to obey. This
    does not make a hostile response safe — a subtly wider `maximum` is indistinguishable
    from a real one — and `design.md` says so. It bounds the shapes that are obviously not a
    model's input schema.
    """
    properties = schema.get("properties")
    return isinstance(properties, dict) and 0 < len(properties) <= MAX_PROPERTIES


def fetch_from_provider(endpoint: str) -> dict[str, Any] | None:
    """The default fetcher. Injected everywhere else, so no test reaches the network."""
    import urllib.parse
    import urllib.request

    url = SCHEMA_URL.format(endpoint=urllib.parse.quote(endpoint, safe=""))
    if urllib.parse.urlparse(url).scheme != "https":
        # Belt and braces: `urlopen` will open `file://` quite happily, and the one thing
        # this function must never do is read a local path because a string looked like one.
        return None

    give_up_at = time.monotonic() + MAX_FETCH_SECONDS
    chunks: list[bytes] = []
    read = 0
    with urllib.request.urlopen(url, timeout=SOCKET_TIMEOUT) as response:
        # Chunked, and timed between chunks. `read()` with no argument is how a hostile
        # response — or an honest but enormous one — becomes this process's memory; and a
        # single bounded `read` still waits forever on a server that trickles a byte at a
        # time, because each `recv` stays under the socket timeout and the socket timeout is
        # the only clock a plain read consults.
        while read <= MAX_SCHEMA_BYTES:
            if time.monotonic() > give_up_at:
                return None
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            read += len(chunk)
    if read > MAX_SCHEMA_BYTES:
        return None
    raw = b"".join(chunks)

    document: dict[str, Any] = json.loads(raw.decode("utf-8"))
    found = input_schema_of(document, endpoint)
    return found if found is not None and plausible(found) else None


@dataclass(frozen=True)
class Registry:
    models: list[Model]
    core: dict[str, dict[str, Any]]

    #: Media to endpoint, from `core.json`. Empty is legitimate: it means every media has to
    #: be configured, which is what a workspace predating this had.
    defaults: dict[str, str] = field(default_factory=dict)

    def get(self, name: str) -> Model:
        for model in self.models:
            if model.endpoint == name:
                return model
        known = ", ".join(sorted(model.endpoint for model in self.models))
        raise UsageError("no-model", f"no model {name!r} in the registry", fix=f"one of: {known}")

    def for_media(self, media: str | None) -> list[Model]:
        return [model for model in self.models if media is None or model.media == media]

    def core_for(self, endpoint: str) -> dict[str, Any]:
        return self.core.get(endpoint, dict.fromkeys(CONCEPTS))

    def size_of(self, endpoint: str) -> Any:
        return self.core_for(endpoint).get("size")

    def check(self, endpoint: str, options: dict[str, Any]) -> dict[str, Any]:
        """The options, or a refusal naming what went wrong (R2.1, R2.2).

        Walks the model's own schema rather than a table this project keeps: a restated table
        drifts silently, which is the failure the whole leaf exists to prevent.
        """
        model = self.get(endpoint)

        unknown = sorted(set(options) - set(model.options))
        if unknown:
            accepted = ", ".join(sorted(model.options))
            raise UsageError(
                "unknown-option",
                f"{model.endpoint} does not accept {', '.join(unknown)}",
                fix=f"it accepts: {accepted}",
            )

        for name, value in options.items():
            _check_value(model, model.options[name], value)

        missing = sorted(
            name
            for name, option in model.options.items()
            if option.required and name not in options
        )
        if missing:
            raise UsageError(
                "missing-option",
                f"{model.endpoint} requires {', '.join(missing)}",
                fix="pass it, or use a command that fills it in",
            )
        return dict(options)

    def resolve(
        self, endpoint: str, *, core: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        """The core options in the model's own spelling, plus the raw ones (R2.3, R2.4)."""
        mapping = self.core_for(endpoint)
        resolved: dict[str, Any] = dict(options)

        for concept, value in core.items():
            if concept not in CONCEPTS:
                raise UsageError(
                    "no-such-concept",
                    f"{concept!r} is not one of the core options",
                    fix=f"they are: {', '.join(CONCEPTS)}",
                )
            mapped = mapping.get(concept)
            if mapped is None:
                # Not dropped. A caller who asked for reproducibility and did not get it has
                # no way to find out except by running twice and comparing.
                raise UsageError(
                    "no-such-concept",
                    f"{endpoint} has no {concept!r}, so it cannot be set",
                    fix=f"drop it, or use a model that has it — ssc model show {endpoint}",
                )
            if isinstance(mapped, dict):
                raise UsageError(
                    "no-such-concept",
                    f"{concept!r} is not one field on {endpoint} and has to be resolved first",
                    fix=f"ssc model show {endpoint} reports its shape",
                )
            resolved[mapped] = value

        return self.check(endpoint, resolved)

    def default_for(self, media: str) -> str | None:
        """The model the package reaches for when nothing else says
        (`specs/model-options/` R1.5).

        In `core.json` beside the mappings rather than written into a new workspace's
        `ssc.yaml`: one fact in two places drifts, and the copy in every workspace ever
        created is the one that would go stale.
        """
        found = self.defaults.get(media)
        return str(found) if found else None

    def chosen(self, media: str, *, config: dict[str, Any], from_kind: str | None = None) -> str:
        """Which model runs for this media (R3.1, R3.2, R3.3, `specs/model-options/` R1.6)."""
        named = from_kind or (config.get("models") or {}).get(media) or self.default_for(media)
        if not named:
            raise SscError(
                "no-model-configured",
                f"no model is configured for {media}",
                fix=f"set models.{media} in ssc.yaml, or name one on the kind",
            )
        if named not in {model.endpoint for model in self.models}:
            known = ", ".join(sorted(m.endpoint for m in self.models if m.media == media))
            raise SscError(
                "unknown-model",
                f"{named!r} is configured for {media} and is not a model in the registry",
                fix=f"for {media}: {known}",
            )
        return str(named)


def _check_value(model: Model, option: Option, value: Any) -> None:
    if isinstance(value, dict):
        # A field offering an object branch is checked no further here (R2.2): what bounds the
        # value is the pixels size shape in `core.json`, and the enum and the scalar type below
        # describe the *other* branch — applying either would refuse every object.
        if option.objects:
            return
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} does not take an object",
            fix=f"ssc model show {model.endpoint} reports what it takes",
        )
    # `value in allowed` alone lets `True` match an integer enum's `1`, because Python says
    # they are equal. The match has to agree about the type as well as the value, and it is
    # per member rather than per enum so a mixed `[true, 5]` still accepts `5`.
    if option.allowed is not None and not any(
        item == value and isinstance(item, bool) == isinstance(value, bool)
        for item in option.allowed
    ):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} does not take {value!r}",
            fix=f"one of: {', '.join(str(item) for item in option.allowed)}",
        )
    if option.type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} is an integer and got {value!r}",
            fix="pass a whole number",
        )
    if option.type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} is a number and got {value!r}",
            fix="pass a number",
        )
    if option.type == "string" and not isinstance(value, str):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} is a string and got {value!r}",
            fix="pass text",
        )
    if option.type == "array" and not isinstance(value, list):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} is a list and got {value!r}",
            fix="pass a list, even for one item",
        )
    if option.type == "object" and not isinstance(value, dict):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} is an object and got {value!r}",
            fix="pass an object",
        )
    if option.type == "boolean" and not isinstance(value, bool):
        raise UsageError(
            "invalid-option",
            f"{model.endpoint}.{option.name} is true or false and got {value!r}",
            fix="pass true or false",
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if option.minimum is not None and value < option.minimum:
            raise UsageError(
                "invalid-option",
                f"{model.endpoint}.{option.name} is at least {option.minimum} and got {value}",
                fix=f"pass {option.minimum} or more",
            )
        if option.maximum is not None and value > option.maximum:
            raise UsageError(
                "invalid-option",
                f"{model.endpoint}.{option.name} is at most {option.maximum} and got {value}",
                fix=f"pass {option.maximum} or less",
            )


def load(*, fetch: Fetcher | None = None) -> Registry:
    """The registry, provider first and package second (R1.4, R1.5).

    A fetcher that returns `None` or raises is a fallback, not a failure: Fal being
    unreachable must not stop a caller inspecting what it knows.
    """
    shipped = _shipped("models.json")
    declared = _shipped("core.json")
    core = declared.get("models", {})

    # Two records of one fact drift, and the copy is the one that goes stale — so the file's
    # own list of concepts is checked against this module's rather than merely sitting there.
    stated = tuple(declared.get("concepts") or ())
    if stated != CONCEPTS:
        raise SscError(
            "registry-invalid",
            f"core.json declares concepts {stated} and the code has {CONCEPTS}",
            fix="make them match; they are one decision recorded twice",
        )

    fetcher = fetch_from_provider if fetch is None else fetch
    deadline = time.monotonic() + FETCH_BUDGET_SECONDS

    built: list[Model] = []
    for described in shipped.get("models", []):
        endpoint = str(described["endpoint_id"])
        schema = described.get("input_schema") or {}
        source = "package"
        live = None
        # One budget for the whole load rather than a timeout each: six models times a
        # per-socket timeout is a minute of hanging on a command that reads a schema.
        if time.monotonic() < deadline:
            try:
                live = fetcher(endpoint)
            except Exception:
                live = None
        if live:
            schema, source = live, "provider"
        built.append(
            Model(
                endpoint=endpoint,
                media=str(described.get("media", "")),
                role=str(described.get("role", "")),
                provider=str(described.get("provider", "")),
                options=_options(schema),
                source=source,
            )
        )
    defaults = {
        str(media): str(endpoint)
        for media, endpoint in (declared.get("defaults") or {}).items()
        if endpoint
    }
    known = {model.endpoint: model.media for model in built}
    for media, endpoint in sorted(defaults.items()):
        # Checked at load rather than at the call it would have chosen: a default naming a
        # model that is not here is a packaging mistake, and reporting it as
        # `unknown-model` on somebody's `gen image` names the wrong culprit.
        if known.get(endpoint) != media:
            raise SscError(
                "registry-invalid",
                f"core.json makes {endpoint!r} the default for {media} and the registry has "
                f"no {media} model by that name",
                fix="make them match; the default has to name a model that is in models.json",
            )
    return Registry(models=built, core=core, defaults=defaults)
