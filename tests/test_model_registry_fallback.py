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
    "xai/grok-imagine-video/image-to-video",
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


def test_a_reference_image_is_an_endpoint_not_a_parameter(
    by_endpoint: dict[str, dict[str, Any]],
) -> None:
    assert "image_urls" not in properties(by_endpoint["fal-ai/gpt-image-1.5"])
    assert "image_urls" in by_endpoint["fal-ai/gpt-image-1.5/edit"]["input_schema"]["required"]


def test_video_length_is_a_per_model_parameter(by_endpoint: dict[str, dict[str, Any]]) -> None:
    """`gen video` must not hard-code a duration; the model exposes one and enumerates
    nothing, so what loops well stays an empirical question."""
    model = by_endpoint["xai/grok-imagine-video/image-to-video"]
    assert "duration" in properties(model)
    assert enum_of(model, "duration") is None
