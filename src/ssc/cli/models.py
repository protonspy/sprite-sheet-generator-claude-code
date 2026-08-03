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
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

from ssc.cli.errors import SscError, UsageError

#: The concepts that genuinely exist across models, under one name each. Everything else goes
#: through raw and is checked against the schema. Normalising more would mean owning a
#: translation table that goes stale silently; normalising none would push per-model
#: divergence into every skill and template.
CONCEPTS = ("prompt", "image", "seconds", "size", "seed")

#: Fal serves one of these per endpoint, unauthenticated.
SCHEMA_URL = "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={endpoint}"

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

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "type": self.type, "required": self.required}
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
        )
    return found


def _shipped(name: str) -> dict[str, Any]:
    text = resources.files("ssc.data").joinpath(name).read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    return data


def fetch_from_provider(endpoint: str) -> dict[str, Any] | None:
    """The default fetcher. Injected everywhere else, so no test reaches the network."""
    import urllib.request

    with urllib.request.urlopen(SCHEMA_URL.format(endpoint=endpoint), timeout=10) as response:
        document: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    for path in document.get("components", {}).get("schemas", {}).values():
        if isinstance(path, dict) and "properties" in path:
            return path
    return None


@dataclass(frozen=True)
class Registry:
    models: list[Model]
    core: dict[str, dict[str, Any]]

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

    def chosen(self, media: str, *, config: dict[str, Any], from_kind: str | None = None) -> str:
        """Which model runs for this media (R3.1, R3.2, R3.3)."""
        named = from_kind or (config.get("models") or {}).get(media)
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
    if option.allowed is not None and value not in option.allowed:
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
    core = _shipped("core.json").get("models", {})
    fetcher = fetch_from_provider if fetch is None else fetch

    built: list[Model] = []
    for described in shipped.get("models", []):
        endpoint = str(described["endpoint_id"])
        schema = described.get("input_schema") or {}
        source = "package"
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
    return Registry(models=built, core=core)
