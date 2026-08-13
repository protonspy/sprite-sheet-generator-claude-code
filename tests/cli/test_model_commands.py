"""`ssc model list|show` — specs/model-registry R1.1, R1.2, R1.3, R1.5, R1.6."""

from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from ssc.cli import models
from ssc.cli.app import main

NANO = "fal-ai/nano-banana-2"


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches the network. The shipped copy is a real schema, so the fallback path
    is both what the tests exercise and what matters when Fal is down."""
    monkeypatch.setattr(models, "fetch_from_provider", lambda endpoint: None)


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def test_every_model_is_listed_with_its_media(offline: None) -> None:
    code, payload = run("model", "list")

    assert code == 0
    assert payload["count"] == 13
    assert {entry["media"] for entry in payload["models"]} == {"image", "video"}


def test_the_listing_names_the_default_for_each_media(offline: None) -> None:
    """`specs/model-options/` R1.7 — an agent picking a model reads the default here rather
    than learning it by generating."""
    _, payload = run("model", "list")

    assert payload["defaults"] == {
        "image": "openai/gpt-image-2",
        "video": "xai/grok-imagine-video/image-to-video",
    }
    flagged = {entry["id"] for entry in payload["models"] if entry["default"]}
    assert flagged == {"openai/gpt-image-2", "xai/grok-imagine-video/image-to-video"}


def test_a_narrowed_listing_names_only_that_media_s_default(offline: None) -> None:
    _, payload = run("model", "list", "--media", "image")

    assert payload["defaults"] == {"image": "openai/gpt-image-2"}


def test_a_media_narrows_the_listing(offline: None) -> None:
    _, payload = run("model", "list", "--media", "video")

    assert [entry["id"] for entry in payload["models"]] == [
        "xai/grok-imagine-video/image-to-video",
        "xai/grok-imagine-video/v1.5/image-to-video",
        "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "bytedance/seedance-2.5/image-to-video",
    ]


def test_show_reports_the_options_with_their_types_and_ranges(offline: None) -> None:
    code, payload = run("model", "show", NANO)

    assert code == 0
    by_name = {option["name"]: option for option in payload["options"]}
    assert by_name["resolution"]["allowed"] == ["0.5K", "1K", "2K", "4K"]
    assert by_name["num_images"]["maximum"] == 4
    assert by_name["prompt"]["required"] is True


def test_show_says_where_the_schema_came_from(offline: None) -> None:
    """A caller debugging a rejected option needs to know whether it was checked against
    today's schema or last release's."""
    _, payload = run("model", "show", NANO)

    assert payload["source"] == "package"


def test_show_carries_the_core_mapping_beside_the_schema(offline: None) -> None:
    """It answers what the schema cannot: which field is this project's `--seed`, and which
    concepts this model simply does not have."""
    _, nano = run("model", "show", NANO)
    _, gpt = run("model", "show", "fal-ai/gpt-image-1.5")

    assert nano["core"]["seed"] == "seed"
    assert gpt["core"]["seed"] is None
    assert gpt["core"]["size"] == {"kind": "enum", "field": "image_size"}


def test_show_says_what_each_core_option_accepts(offline: None) -> None:
    """`specs/model-options/` R3.6 — the mapping says which field, this says what the field
    takes, so choosing a value costs no second command."""
    _, payload = run("model", "show", "openai/gpt-image-2")
    described = payload["core_options"]

    assert described["quality"]["field"] == "quality"
    assert described["quality"]["allowed"] == ["auto", "low", "medium", "high"]
    assert described["count"]["field"] == "num_images"
    assert described["count"]["maximum"] == 4
    assert described["format"]["allowed"] == ["jpeg", "png", "webp"]
    assert described["size"]["shape"]["kind"] == "pixels"
    assert described["seed"] is None
    assert payload["default"] is True


def test_show_says_a_concept_the_model_does_not_have_is_absent(offline: None) -> None:
    _, payload = run("model", "show", NANO)

    assert payload["core_options"]["quality"] is None
    assert payload["core_options"]["seed"]["field"] == "seed"
    assert payload["default"] is False


def test_a_model_nobody_has_exits_two_naming_the_ones_there_are(offline: None) -> None:
    code, payload = run("model", "show", "fal-ai/imaginary")

    assert code == 2
    assert payload["error"]["code"] == "no-model"
    assert NANO in payload["error"]["fix"]


def test_show_reports_the_price_as_the_providers_own_text_with_its_date(
    offline: None,
) -> None:
    """`specs/model-pricing/` R2.2 — the sentence, not a number derived from it."""
    _, payload = run("model", "show", "fal-ai/kling-video/v2.5-turbo/pro/image-to-video")

    price = payload["price"]
    assert "$0.35" in price["text"]
    assert price["fetched"]
    assert set(price) == {"text", "fetched", "source"}


def test_show_carries_the_caveat_beside_the_price(offline: None) -> None:
    """R2.6 — a reader who takes the text for a quote has been told, where they read it."""
    _, payload = run("model", "show", NANO)

    assert "ssc budget" in payload["price_caveat"]
    assert "indicative" in payload["price_caveat"].lower()


def test_show_reports_a_null_price_rather_than_omitting_it(offline: None) -> None:
    """R2.5 — `fal-ai/birefnet/v2` is the model the provider publishes no price for."""
    _, payload = run("model", "show", "fal-ai/birefnet/v2")

    assert "price" in payload
    assert payload["price"] is None
    assert payload["price_caveat"]


def test_the_listing_says_which_models_have_a_price(offline: None) -> None:
    """R2.3 — a boolean per row; the sentence itself lives in `show`."""
    _, payload = run("model", "list")

    priced = {entry["id"]: entry["priced"] for entry in payload["models"]}
    assert priced["fal-ai/birefnet/v2"] is False
    assert priced["bytedance/seedance-2.5/image-to-video"] is True
    assert all(isinstance(value, bool) for value in priced.values())


def test_no_command_here_spends_anything(offline: None) -> None:
    """`model` is a noun under `main`, not under `gen`: everything below it observes."""
    result = CliRunner().invoke(main, ["model", "--help"], catch_exceptions=False)

    assert "list" in result.output
    assert "show" in result.output
