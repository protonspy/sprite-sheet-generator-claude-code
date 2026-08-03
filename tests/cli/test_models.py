"""The registry, and the check that runs before the money — specs/model-registry R1, R2.

Both TDD tasks are the same argument. An option a model does not have is not an error at the
provider: the call succeeds, the parameter is dropped, the job is billed, and the image is
plausible enough that nobody notices it ignored you. The failure is invisible by
construction, which is why these assertions were written before the validator they describe.

Nothing here touches the network. The fetcher is injected, so the shipped copy is what the
tests exercise — and that is also the path that matters when Fal is down.
"""

from __future__ import annotations

from typing import Any

import pytest

from ssc.cli import models
from ssc.cli.errors import SscError, UsageError

NANO = "fal-ai/nano-banana-2"
GPT = "fal-ai/gpt-image-1.5"


@pytest.fixture
def registry() -> models.Registry:
    """The shipped copy, with a fetcher that always fails — the offline path."""
    return models.load(fetch=lambda endpoint: None)


# R1.1, R1.3 — what is in the registry.


def test_every_shipped_model_is_read(registry: models.Registry) -> None:
    assert len(registry.models) == 6
    assert NANO in {model.endpoint for model in registry.models}


def test_a_model_carries_its_media_and_its_options(registry: models.Registry) -> None:
    model = registry.get(NANO)

    assert model.media == "image"
    assert "prompt" in model.options
    assert model.options["resolution"].default == "1K"
    assert model.options["resolution"].allowed == ["0.5K", "1K", "2K", "4K"]


def test_an_option_the_schema_bounds_reports_its_bounds(registry: models.Registry) -> None:
    option = registry.get(NANO).options["num_images"]

    assert option.type == "integer"
    assert (option.minimum, option.maximum) == (1, 4)


def test_a_nullable_option_reports_the_type_inside_the_anyof(registry: models.Registry) -> None:
    """`seed` is `anyOf: [integer, null]`, which is a schema saying "an integer, optional" —
    reading that as "no type" would make every value valid."""
    assert registry.get(NANO).options["seed"].type == "integer"


# R1.4, R1.5 — where the schema came from.


def test_the_provider_is_asked_first(registry: models.Registry) -> None:
    fetched = {
        "properties": {"prompt": {"type": "string"}, "brand_new": {"type": "string"}},
        "required": ["prompt"],
    }

    live = models.load(fetch=lambda endpoint: fetched if endpoint == NANO else None)

    assert "brand_new" in live.get(NANO).options
    assert live.get(NANO).source == "provider"


def test_the_shipped_copy_is_used_when_the_provider_cannot_be_reached(
    registry: models.Registry,
) -> None:
    """A registry hard-coded in the package would be stale the week after Fal adds a model,
    and stale quietly — so it is the fallback, and the report says so."""
    assert registry.get(NANO).source == "package"


def test_a_fetch_that_raises_is_a_fallback_and_not_a_crash() -> None:
    def broken(endpoint: str) -> dict[str, Any] | None:
        raise OSError("the network went away")

    assert models.load(fetch=broken).get(NANO).source == "package"


def test_a_name_that_matches_no_model_is_refused_naming_the_ones_there_are(
    registry: models.Registry,
) -> None:
    with pytest.raises(UsageError) as refused:
        registry.get("fal-ai/imaginary")
    assert refused.value.code == "no-model"
    assert refused.value.exit_code == 2
    assert NANO in (refused.value.fix or "")


# R2.1, R2.2 — the first TDD task.


def test_an_option_the_model_does_not_declare_stops_the_call(registry: models.Registry) -> None:
    """`--opt guidance_scale=7` at a model whose field is `cfg`: the provider accepts the
    call, drops the parameter and bills for it."""
    with pytest.raises(UsageError) as refused:
        registry.check(NANO, {"guidance_scale": 7})

    assert refused.value.code == "unknown-option"
    assert "guidance_scale" in refused.value.message
    # Naming what it does accept is the difference between a refusal and a dead end.
    assert "resolution" in (refused.value.fix or "")


def test_an_option_the_model_does_declare_is_accepted(registry: models.Registry) -> None:
    assert registry.check(NANO, {"prompt": "a knight", "resolution": "2K"}) == {
        "prompt": "a knight",
        "resolution": "2K",
    }


def test_a_value_outside_the_schema_s_enum_stops_the_call(registry: models.Registry) -> None:
    with pytest.raises(UsageError) as refused:
        registry.check(NANO, {"prompt": "x", "resolution": "8K"})

    assert refused.value.code == "invalid-option"
    assert "8K" in refused.value.message
    # What it *does* take belongs in the fix, which is the field a harness acts on.
    assert "0.5K" in (refused.value.fix or "")


def test_a_value_outside_the_schema_s_bounds_stops_the_call(registry: models.Registry) -> None:
    with pytest.raises(UsageError) as refused:
        registry.check(NANO, {"prompt": "x", "num_images": 99})

    assert refused.value.code == "invalid-option"
    assert "4" in refused.value.message


def test_a_value_of_the_wrong_type_stops_the_call(registry: models.Registry) -> None:
    with pytest.raises(UsageError) as refused:
        registry.check(NANO, {"prompt": "x", "num_images": "several"})

    assert refused.value.code == "invalid-option"


def test_a_required_option_that_is_missing_stops_the_call(registry: models.Registry) -> None:
    with pytest.raises(UsageError) as refused:
        registry.check(NANO, {"resolution": "2K"})

    assert refused.value.code == "missing-option"
    assert "prompt" in refused.value.message


# R2.3, R2.4 — the second TDD task, and the one that earns the annotation.


def test_a_core_option_is_translated_into_the_model_s_own_spelling(
    registry: models.Registry,
) -> None:
    resolved = registry.resolve(NANO, core={"prompt": "a knight", "seed": 7}, options={})

    assert resolved == {"prompt": "a knight", "seed": 7}


def test_a_core_option_the_model_has_no_concept_of_stops_the_call(
    registry: models.Registry,
) -> None:
    """The behaviour a reasonable implementation arrives at by accident: `mapping.get(name)`
    returns `None`, `None` is falsy, the option quietly does not go — and the caller believes
    their generations are reproducible with no way to find out but running twice."""
    with pytest.raises(UsageError) as refused:
        registry.resolve(GPT, core={"prompt": "a knight", "seed": 7}, options={})

    assert refused.value.code == "no-such-concept"
    assert "seed" in refused.value.message
    assert GPT in refused.value.message


def test_the_same_core_option_reaches_two_models_under_two_names(
    registry: models.Registry,
) -> None:
    video = "xai/grok-imagine-video/image-to-video"

    # A complete call, because `resolve` checks what the model requires as well as what it
    # accepts — a translation that produced an unsubmittable call would have moved the
    # failure to the provider, which is where the money is.
    on_video = registry.resolve(
        video, core={"seconds": 1, "prompt": "a knight", "image": "https://x/a.png"}, options={}
    )

    assert on_video["duration"] == 1
    assert on_video["image_url"] == "https://x/a.png"
    assert registry.resolve(NANO, core={"prompt": "x"}, options={}) == {"prompt": "x"}


def test_size_is_a_shape_because_the_models_disagree_about_the_question(
    registry: models.Registry,
) -> None:
    """Not a spelling difference: an enum of three literal sizes on one, an aspect ratio plus
    a resolution tier on the other. `gen-fal` reconciles a layout against this."""
    assert registry.size_of(GPT) == {"kind": "enum", "field": "image_size"}
    assert registry.size_of(NANO)["kind"] == "ratio"


def test_a_raw_option_rides_alongside_a_core_one(registry: models.Registry) -> None:
    resolved = registry.resolve(NANO, core={"prompt": "x"}, options={"output_format": "webp"})

    assert resolved == {"prompt": "x", "output_format": "webp"}


def test_a_raw_option_is_checked_too(registry: models.Registry) -> None:
    with pytest.raises(UsageError) as refused:
        registry.resolve(NANO, core={"prompt": "x"}, options={"nonesuch": 1})
    assert refused.value.code == "unknown-option"


def test_the_core_mapping_names_only_fields_the_schemas_have(registry: models.Registry) -> None:
    """The hand-authored file kept honest against the fetched one — it fails at the refresh
    rather than at the first paid call."""
    for model in registry.models:
        for concept, mapped in registry.core_for(model.endpoint).items():
            if isinstance(mapped, str):
                assert mapped in model.options, f"{model.endpoint}.{concept} -> {mapped}"
            elif isinstance(mapped, dict):
                for field in ("field", "ratio_field", "resolution_field"):
                    if field in mapped:
                        assert mapped[field] in model.options


def test_every_model_has_a_core_mapping(registry: models.Registry) -> None:
    for model in registry.models:
        assert set(registry.core_for(model.endpoint)) == set(models.CONCEPTS)


# R3.1, R3.2, R3.3 — which model runs.


def test_the_workspace_default_is_used_for_a_media(registry: models.Registry) -> None:
    assert registry.chosen("image", config={"models": {"image": GPT}}) == GPT


def test_a_kind_that_names_a_model_overrides_the_workspace(registry: models.Registry) -> None:
    assert registry.chosen("image", config={"models": {"image": GPT}}, from_kind=NANO) == NANO


def test_a_configured_model_nobody_knows_is_refused_by_name(registry: models.Registry) -> None:
    """Not a fallback to a default: generating with a different model than the one configured
    is the same class of failure as silently dropping an option."""
    with pytest.raises(SscError) as refused:
        registry.chosen("image", config={"models": {"image": "fal-ai/imaginary"}})

    assert refused.value.code == "unknown-model"
    assert "fal-ai/imaginary" in refused.value.message


def test_a_media_nobody_configured_is_refused(registry: models.Registry) -> None:
    with pytest.raises(SscError) as refused:
        registry.chosen("video", config={})

    assert refused.value.code == "no-model-configured"


def test_a_kind_can_name_a_model_for_each_media() -> None:
    """R3.2, as a delta against `asset-kinds` — a new field there is that spec's mechanism
    working rather than a hole in it."""
    from ssc.cli import kinds

    assert kinds.Profile(name="x").image_model == ""
    assert "image_model" in kinds.FIELDS
    assert "video_model" in kinds.Profile(name="x").as_dict()
