"""The refresh script that regenerates `models.json` — `specs/model-pricing/` R3.1-R3.5.

Every test injects the getter, so none of them reaches the network. The script lives
outside the package, so it is loaded from its path rather than imported by name.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fetch_model_schemas.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("fetch_model_schemas", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


refresh = _load()


def openapi(endpoint: str, *, about: str = "A model", category: str = "text-to-image") -> dict:
    """The shape the queue OpenAPI document actually has, cut down to what is read."""
    return {
        "info": {
            "x-fal-metadata": {
                "endpointId": endpoint,
                "category": category,
                "about": about,
                "documentationUrl": f"https://fal.ai/models/{endpoint}/api",
            }
        },
        "paths": {
            f"/{endpoint}": {
                "post": {
                    "requestBody": {
                        "content": {"application/json": {"schema": {"$ref": "#/c/schemas/In"}}}
                    }
                }
            }
        },
        "components": {"schemas": {"In": {"properties": {"prompt": {"type": "string"}}}}},
    }


def test_the_keyword_is_the_model_family_not_the_account() -> None:
    """The listing indexes the family; the first segment is the account (R3.2)."""
    assert refresh.keyword_for("fal-ai/kling-video/v2.5-turbo/pro/image-to-video") == "kling-video"
    assert refresh.keyword_for("bytedance/seedance-2.5/image-to-video") == "seedance-2.5"
    assert refresh.keyword_for("solo") == "solo"


def test_listing_follows_every_page() -> None:
    """The page size is capped below what a broad keyword matches, so reading page one
    misses endpoints that are there (R3.2)."""
    pages = {
        1: {"items": [{"id": "a"}, {"id": "b"}], "pages": 3},
        2: {"items": [{"id": "c"}], "pages": 3},
        3: {"items": [{"id": "d"}], "pages": 3},
    }
    asked: list[str] = []

    def get(url: str) -> dict:
        asked.append(url)
        page = int(url.rsplit("page=", 1)[1])
        return pages[page]

    found = refresh.listing("kling-video", get)

    assert sorted(found) == ["a", "b", "c", "d"]
    assert len(asked) == 3


def test_listing_stops_on_an_empty_page_rather_than_looping() -> None:
    def get(url: str) -> dict:
        return {"items": [], "pages": 99}

    assert refresh.listing("nothing", get) == {}


def test_price_is_the_providers_text_stamped_with_the_day_it_was_read() -> None:
    """R2.1, R3.3 — the sentence verbatim, and no number derived from it (R2.4)."""
    item = {"id": "x", "pricingInfoOverride": "For **5s** video your request will cost **$0.35**."}

    price = refresh.price_of(item, "2026-08-13")

    assert price == {
        "text": "For **5s** video your request will cost **$0.35**.",
        "fetched": "2026-08-13",
        "source": "https://fal.ai/api/models",
    }
    assert not any(isinstance(value, (int, float)) for value in price.values())


@pytest.mark.parametrize(
    "item",
    [
        None,
        {"id": "x"},
        {"id": "x", "pricingInfoOverride": "   "},
        {"id": "x", "hidePricing": True},
    ],
)
def test_price_is_none_where_the_provider_publishes_none(item: dict | None) -> None:
    """R2.5 — `fal-ai/birefnet/v2` is the real one of these."""
    assert refresh.price_of(item, "2026-08-13") is None


def test_entry_carries_the_media_the_category_implies_and_the_role_verbatim() -> None:
    entry = refresh.entry_for(
        "bytedance/seedance-2.5/image-to-video",
        openapi("bytedance/seedance-2.5/image-to-video", category="image-to-video"),
        {"id": "bytedance/seedance-2.5/image-to-video", "pricingInfoOverride": "$0.47 per second"},
        "2026-08-13",
    )

    assert entry["media"] == "video"
    assert entry["role"] == "image-to-video"
    assert entry["provider"] == "fal"
    assert entry["input_schema"]["properties"] == {"prompt": {"type": "string"}}
    assert entry["price"]["text"] == "$0.47 per second"


def test_a_curated_role_survives_the_refresh() -> None:
    """`gen bgremove` selects by role, and BiRefNet's category is the one every editing
    model carries — recomputing role from the category sends the call to the wrong model."""
    entry = refresh.entry_for(
        "fal-ai/birefnet/v2",
        openapi("fal-ai/birefnet/v2", category="image-to-image"),
        None,
        "2026-08-13",
    )

    assert entry["role"] == "background-removal"
    assert entry["category"] == "image-to-image"


def test_a_model_with_no_curated_role_keeps_the_providers_category() -> None:
    entry = refresh.entry_for("a/b", openapi("a/b", category="text-to-image"), None, "2026-08-13")

    assert entry["role"] == "text-to-image"


def test_entry_writes_the_price_key_even_when_there_is_no_price() -> None:
    """R2.5 — present and null, never absent."""
    document = openapi("fal-ai/birefnet/v2")
    entry = refresh.entry_for("fal-ai/birefnet/v2", document, None, "2026-08-13")

    assert "price" in entry
    assert entry["price"] is None


def test_entry_refuses_a_document_with_no_input_schema() -> None:
    """Following `paths → post → requestBody → $ref` is the algorithm; a document that does
    not have it is a failure, not an entry with no options."""
    document = openapi("a/b")
    del document["paths"]["/a/b"]

    with pytest.raises(LookupError):
        refresh.entry_for("a/b", document, None, "2026-08-13")


def test_build_keeps_and_reports_an_endpoint_whose_document_failed() -> None:
    """R3.4 — dropping it would surface as `unknown-model` on a workspace that worked."""
    held = {"endpoint_id": "a/broken", "about": "from last time", "price": None}

    def get(url: str) -> dict:
        if "broken" in url:
            raise OSError("no route to host")
        if "api/models?" in url:
            return {"items": [], "pages": 1}
        return openapi("a/fine")

    models, failed = refresh.build(("a/fine", "a/broken"), get, "2026-08-13", {"a/broken": held})

    assert failed == ["a/broken"]
    assert [m["endpoint_id"] for m in models] == ["a/fine", "a/broken"]
    assert models[1] == held


def test_build_loses_the_price_but_not_the_model_when_the_listing_fails() -> None:
    def get(url: str) -> dict:
        if "api/models?" in url:
            raise OSError("listing down")
        return openapi("a/fine")

    models, failed = refresh.build(("a/fine",), get, "2026-08-13")

    assert failed == []
    assert models[0]["price"] is None
    assert models[0]["input_schema"]["properties"]


def test_build_reads_one_listing_per_family_not_one_per_endpoint() -> None:
    listings = 0

    def get(url: str) -> dict:
        nonlocal listings
        if "api/models?" in url:
            listings += 1
            return {"items": [], "pages": 1}
        return openapi("fal-ai/nano-banana-2")

    refresh.build(("fal-ai/nano-banana-2", "fal-ai/nano-banana-2/edit"), get, "2026-08-13")

    assert listings == 1


def test_today_is_a_day_not_a_timestamp() -> None:
    """R3.3, and the reason design.md gives: a timestamp churns every unchanged entry."""
    import datetime

    assert datetime.date.fromisoformat(refresh.today())


def test_read_refuses_a_url_that_is_not_https() -> None:
    """`urlopen` will open `file://` quite happily."""
    with pytest.raises(ValueError, match="non-https"):
        refresh.read("file:///etc/passwd")


def test_main_writes_the_catalogue_without_credentials(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    """R3.5 — the whole refresh reaches the provider unauthenticated."""
    out = tmp_path / "models.json"
    seen: list[str] = []

    def get(url: str) -> dict:
        seen.append(url)
        if "api/models?" in url:
            listed = {"id": "openai/gpt-image-2", "pricingInfoOverride": "$0.02"}
            return {"items": [listed], "pages": 1}
        return openapi("openai/gpt-image-2")

    monkeypatch.setattr(refresh, "read", get)
    monkeypatch.setattr(refresh, "ENDPOINTS", ("openai/gpt-image-2",))

    assert refresh.main(["--out", str(out)]) == 0

    written = json.loads(out.read_text(encoding="utf-8"))
    assert [m["endpoint_id"] for m in written["models"]] == ["openai/gpt-image-2"]
    assert written["models"][0]["price"]["text"] == "$0.02"
    secrets = ("api_key", "apikey", "token", "authorization", "secret")
    assert seen and all(url.startswith("https://fal.ai/") for url in seen)
    assert not any(marker in url.lower() for url in seen for marker in secrets)


def test_main_exits_non_zero_when_something_could_not_be_refreshed(  # type: ignore[no-untyped-def]
    tmp_path: Path, monkeypatch
) -> None:
    """R3.4 — a refresh that half worked must not look like one that worked."""

    def get(url: str) -> dict:
        raise OSError("down")

    monkeypatch.setattr(refresh, "read", get)
    monkeypatch.setattr(refresh, "ENDPOINTS", ("openai/gpt-image-2",))

    assert refresh.main(["--out", str(tmp_path / "models.json")]) == 1
