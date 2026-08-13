"""`src/ssc/data/models.json` is the offline fallback for `ssc model show`.

These tests never touch the network. They check the shipped copy is well-formed, and they
pin the four facts `plans/ssc-pipeline.md` now reasons from — the ones that decide whether
`gen image` can honour a layout at all. A failure here after
`python scripts/fetch_model_schemas.py` means Fal changed a model and the plan's note on
size reconciliation has to be re-read, not that the test is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

REGISTRY = Path(__file__).resolve().parent.parent / "src/ssc/data/models.json"

EXPECTED_ENDPOINTS = {
    "fal-ai/nano-banana-2",
    "fal-ai/nano-banana-2/edit",
    "fal-ai/gpt-image-1.5",
    "fal-ai/gpt-image-1.5/edit",
    "openai/gpt-image-2",
    "openai/gpt-image-2/edit",
    "xai/grok-imagine-image/v2.0/text-to-image",
    "xai/grok-imagine-image/v2.0/edit",
    "xai/grok-imagine-video/image-to-video",
    "xai/grok-imagine-video/v1.5/image-to-video",
    "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "bytedance/seedance-2.5/image-to-video",
    "fal-ai/birefnet/v2",
}


@pytest.fixture(scope="module")
def registry() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="module")
def by_endpoint(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {model["endpoint_id"]: model for model in registry["models"]}


def properties(model: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = model["input_schema"]["properties"]
    return props


def enum_of(model: dict[str, Any], field: str) -> list[Any] | None:
    """Read a field's allowed values, following the one $ref level Fal emits."""
    node = properties(model)[field]
    if "$ref" in node:
        node = model["input_schema"]["$defs"][node["$ref"].rsplit("/", 1)[-1]]
    values: list[Any] | None = node.get("enum")
    return values


def test_every_named_model_is_present(by_endpoint: dict[str, dict[str, Any]]) -> None:
    assert set(by_endpoint) == EXPECTED_ENDPOINTS


def test_every_entry_carries_a_usable_schema(registry: dict[str, Any]) -> None:
    for model in registry["models"]:
        schema = model["input_schema"]
        assert schema["properties"], model["endpoint_id"]
        assert schema["required"], model["endpoint_id"]
        assert model["media"] in {"image", "video"}


def test_gpt_image_offers_exactly_three_shapes(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """The reason a 6:1 pose board is unrepresentable rather than merely approximate."""
    assert enum_of(by_endpoint["fal-ai/gpt-image-1.5"], "image_size") == [
        "1024x1024",
        "1536x1024",
        "1024x1536",
    ]


def test_nano_banana_asks_the_size_question_differently(
    by_endpoint: dict[str, dict[str, Any]],
) -> None:
    """Aspect ratio plus a resolution tier — so `--size` maps per model, not globally."""
    model = by_endpoint["fal-ai/nano-banana-2"]
    assert "image_size" not in properties(model)
    assert "aspect_ratio" in properties(model)
    assert enum_of(model, "resolution") == ["0.5K", "1K", "2K", "4K"]


def test_seed_is_not_universal(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """A normalised --seed cannot be assumed to reach the model."""
    assert "seed" in properties(by_endpoint["fal-ai/nano-banana-2"])
    assert "seed" not in properties(by_endpoint["fal-ai/gpt-image-1.5"])
    for endpoint in (
        "openai/gpt-image-2",
        "openai/gpt-image-2/edit",
        "xai/grok-imagine-image/v2.0/text-to-image",
        "xai/grok-imagine-image/v2.0/edit",
    ):
        assert "seed" not in properties(by_endpoint[endpoint]), endpoint


def test_gpt_image_2_takes_a_size_in_pixels(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """The one model that does, and the reason `core.json` grew a third size shape.

    The bounds it really enforces — multiple of 16, 3840 per edge, 3:1, 655360 to 8294400
    pixels — are in the description and nowhere machine-readable, which is what this pins:
    the moment Fal states them in the schema, `core.json` should stop transcribing them.
    """
    node = properties(by_endpoint["openai/gpt-image-2"])["image_size"]
    branches = node["anyOf"]
    assert any("$ref" in branch for branch in branches)
    assert any(branch.get("type") == "string" for branch in branches)
    assert "multiples of 16" in node["description"]


def test_grok_imagine_image_asks_for_a_ratio_and_a_tier(
    by_endpoint: dict[str, dict[str, Any]],
) -> None:
    """Lower-case tiers, where Nano Banana 2 spells the same idea `1K` and `2K`."""
    model = by_endpoint["xai/grok-imagine-image/v2.0/text-to-image"]
    assert "image_size" not in properties(model)
    assert enum_of(model, "resolution") == ["1k", "2k"]
    assert enum_of(model, "quality") == ["low", "medium"]


def test_a_count_is_bounded_per_model(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """`--count` bills per image, so the ceiling is a fact worth pinning rather than
    discovering from an invoice."""
    for endpoint in (
        "openai/gpt-image-2",
        "xai/grok-imagine-image/v2.0/text-to-image",
    ):
        assert properties(by_endpoint[endpoint])["num_images"]["maximum"] == 4, endpoint


def test_a_reference_image_is_an_endpoint_not_a_parameter(
    by_endpoint: dict[str, dict[str, Any]],
) -> None:
    assert "image_urls" not in properties(by_endpoint["fal-ai/gpt-image-1.5"])
    assert "image_urls" in by_endpoint["fal-ai/gpt-image-1.5/edit"]["input_schema"]["required"]


def test_background_removal_is_a_role_of_its_own(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """`gen bgremove` finds its model by role. BiRefNet's provider category is
    `image-to-image`, which every editing model also carries, so the role has to say the job
    rather than the shape — and a refresh must not flatten it back."""
    birefnet = by_endpoint["fal-ai/birefnet/v2"]

    assert birefnet["role"] == "background-removal"
    assert birefnet["category"] == "image-to-image"
    roles = [model["role"] for model in by_endpoint.values()]
    assert roles.count("background-removal") == 1


def test_every_core_mapping_names_a_field_the_model_really_has(
    by_endpoint: dict[str, dict[str, Any]],
) -> None:
    """`specs/model-pricing/` R1.3 — the mapping is hand-authored, so nothing checks it but
    this. A concept mapped onto a field the schema does not have is a value dropped in
    flight: the call succeeds, the job is billed, and the parameter never arrived."""
    core = json.loads((REGISTRY.parent / "core.json").read_text(encoding="utf-8"))

    for endpoint, mapping in core["models"].items():
        available = properties(by_endpoint[endpoint])
        for concept, mapped in mapping.items():
            if mapped is None:
                continue
            if isinstance(mapped, dict):
                named = [value for key, value in mapped.items() if key.endswith("_field")]
                for field in named:
                    assert field in available, f"{endpoint}.{concept} -> {field}"
            else:
                assert mapped in available, f"{endpoint}.{concept} -> {mapped}"


def test_the_added_video_models_map_their_own_duration_and_take_no_size(
    by_endpoint: dict[str, dict[str, Any]],
) -> None:
    """R1.3, and the reason `design.md` gives for `size: null` — a `ratio` shape needs a
    field that enumerates its ratios, and none of the three has one."""
    core = json.loads((REGISTRY.parent / "core.json").read_text(encoding="utf-8"))

    for endpoint in (
        "xai/grok-imagine-video/v1.5/image-to-video",
        "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "bytedance/seedance-2.5/image-to-video",
    ):
        mapping = core["models"][endpoint]
        assert mapping["seconds"] == "duration", endpoint
        assert mapping["image"] == "image_url", endpoint
        assert mapping["size"] is None, endpoint
        available = properties(by_endpoint[endpoint])
        offers_ratios = "aspect_ratio" in available and enum_of(
            by_endpoint[endpoint], "aspect_ratio"
        )
        assert not offers_ratios, endpoint


def test_every_model_carries_a_price_key_even_where_there_is_no_price(
    registry: dict[str, Any],
) -> None:
    """R2.1, R2.5 — present and null, never absent, and never a number." """
    for model in registry["models"]:
        assert "price" in model, model["endpoint_id"]
        price = model["price"]
        if price is None:
            continue
        assert isinstance(price["text"], str) and price["text"].strip()
        assert isinstance(price["fetched"], str)


def test_video_length_is_a_per_model_parameter(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """`gen video` must not hard-code a duration; the model exposes one and enumerates
    nothing, so what loops well stays an empirical question."""
    model = by_endpoint["xai/grok-imagine-video/image-to-video"]
    assert "duration" in properties(model)
    assert enum_of(model, "duration") is None
