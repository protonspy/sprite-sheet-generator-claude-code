"""Regenerate `src/ssc/data/models.json` from what the providers publish.

Two documents per model, neither of which needs a credential (`specs/model-pricing/` R3.5):

- the endpoint's queue OpenAPI document, which carries the input schema, the category and
  the prose `about`;
- the model listing, which carries the price — and only the listing carries it. There is
  no price of any kind in the OpenAPI document, which is why a file regenerated from that
  document alone could never have had one.

Run it from the repository root, after adding an endpoint to `ENDPOINTS` or when a schema
or a price has moved:

    uv run python scripts/fetch_model_schemas.py

Nothing here is hand-editable afterwards. `core.json` beside the output is the file that
*is* hand-authored — which of these fields is this project's `--seed` is a decision no
provider document states.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ssc.cli.models import SCHEMA_URL, input_schema_of

#: The catalogue. Membership is a decision rather than something to discover: the listing
#: serves thousands of endpoints and this project supports the ones `core.json` maps.
ENDPOINTS: tuple[str, ...] = (
    "fal-ai/nano-banana-2",
    "fal-ai/nano-banana-2/edit",
    "fal-ai/gpt-image-1.5",
    "fal-ai/gpt-image-1.5/edit",
    "fal-ai/birefnet/v2",
    "openai/gpt-image-2",
    "openai/gpt-image-2/edit",
    "xai/grok-imagine-image/v2.0/text-to-image",
    "xai/grok-imagine-image/v2.0/edit",
    "xai/grok-imagine-video/image-to-video",
    "xai/grok-imagine-video/v1.5/image-to-video",
    "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "bytedance/seedance-2.5/image-to-video",
)

#: The listing has no by-id route — `…/api/models/<id>` returns the site's 404 page — so it
#: is searched by keyword and filtered to the exact id.
LISTING_URL = "https://fal.ai/api/models?{query}"

#: What a category makes. `media` is the axis `ssc.yaml` and every kind select a model on.
MEDIA: dict[str, str] = {
    "text-to-image": "image",
    "image-to-image": "image",
    "text-to-video": "video",
    "image-to-video": "video",
}

#: `role` is the provider's category, except where this project needs a job the category
#: does not name. `gen bgremove` picks its model by role, and BiRefNet's category —
#: `image-to-image` — is the same one every editing model carries, so selecting on it would
#: send a background removal to whatever edits pictures. A refresh that recomputed role from
#: the category would erase that, silently, and the failure is a wrong paid call rather than
#: an error. Hand-authored here for the same reason `core.json` is hand-authored.
ROLES: dict[str, str] = {
    "fal-ai/birefnet/v2": "background-removal",
}

OUTPUT = Path(__file__).resolve().parent.parent / "src" / "ssc" / "data" / "models.json"

NOTE = (
    "Offline fallback; the runtime reads the same URL. Refreshed by scripts/fetch_model_schemas.py."
)

Getter = Callable[[str], dict[str, Any]]


def read(url: str) -> dict[str, Any]:
    """Fetch one JSON document. Injected everywhere else, so no test reaches the network."""
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError(f"refusing a non-https url: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ssc-fetch-model-schemas"})
    with urllib.request.urlopen(request, timeout=60) as response:
        document = json.loads(response.read().decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"expected a JSON object from {url}")
    return document


def keyword_for(endpoint: str) -> str:
    """The listing search term for an endpoint: its model family.

    `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` is found by `kling-video`, which is
    the second segment for every id the catalogue holds — the first is the account.
    """
    parts = endpoint.split("/")
    return parts[1] if len(parts) > 1 else endpoint


def listing(keyword: str, get: Getter) -> dict[str, dict[str, Any]]:
    """Every model the listing returns for a keyword, by id, following its paging.

    Paging is not optional: the page size is capped well below what a broad keyword
    matches, so reading page one silently misses endpoints that are there. Asking for a
    larger `size` does not raise the cap — it is ignored.
    """
    found: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        query = urllib.parse.urlencode({"keywords": keyword, "page": page})
        document = get(LISTING_URL.format(query=query))
        items = document.get("items") or []
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                found[item["id"]] = item
        pages = document.get("pages")
        if not items or not isinstance(pages, int) or page >= pages:
            return found
        page += 1


def price_of(item: dict[str, Any] | None, fetched: str) -> dict[str, Any] | None:
    """The provider's own price sentence, stamped with the day it was read.

    `None` where the provider publishes none — `fal-ai/birefnet/v2` is one — and the key is
    still written, because absent and "no such thing" read the same to a reader and mean
    different things (R2.5). The text is not parsed: see `design.md`.
    """
    if item is None or item.get("hidePricing"):
        return None
    text = item.get("pricingInfoOverride")
    if not isinstance(text, str) or not text.strip():
        return None
    return {"text": text, "fetched": fetched, "source": "https://fal.ai/api/models"}


def entry_for(
    endpoint: str, document: dict[str, Any], item: dict[str, Any] | None, fetched: str
) -> dict[str, Any]:
    """One model's record, from the two documents that describe it."""
    metadata = document.get("info", {}).get("x-fal-metadata", {})
    category = str(metadata.get("category") or "")
    schema = input_schema_of(document, endpoint)
    if schema is None:
        raise LookupError(f"{endpoint}: the OpenAPI document carries no input schema")
    return {
        "about": str(metadata.get("about") or ""),
        "category": category,
        "documentation_url": str(metadata.get("documentationUrl") or ""),
        "endpoint_id": endpoint,
        "input_schema": schema,
        "media": MEDIA.get(category, ""),
        "price": price_of(item, fetched),
        "provider": "fal",
        "role": ROLES.get(endpoint, category),
    }


def build(
    endpoints: tuple[str, ...],
    get: Getter,
    fetched: str,
    existing: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Every model's record, plus the endpoints that could not be refreshed (R3.4).

    An endpoint whose document fails keeps whatever the catalogue already holds for it. The
    alternative — dropping it — turns one bad network minute into a registry that quietly
    lost a model, and that surfaces as `unknown-model` on a workspace that worked yesterday.
    """
    kept = existing or {}
    models: list[dict[str, Any]] = []
    failed: list[str] = []
    catalogues: dict[str, dict[str, dict[str, Any]]] = {}

    for endpoint in endpoints:
        keyword = keyword_for(endpoint)
        if keyword not in catalogues:
            try:
                catalogues[keyword] = listing(keyword, get)
            except Exception:
                catalogues[keyword] = {}
        try:
            document = get(SCHEMA_URL.format(endpoint=urllib.parse.quote(endpoint, safe="")))
            models.append(entry_for(endpoint, document, catalogues[keyword].get(endpoint), fetched))
        except Exception:
            failed.append(endpoint)
            if endpoint in kept:
                models.append(kept[endpoint])
    return models, failed


def today() -> str:
    """The fetch date, to the day. A timestamp would churn the diff of every unchanged
    entry on each refresh, and the question a reader of a committed file has is how stale
    it is in days."""
    return datetime.date.today().isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT, help="where to write models.json")
    arguments = parser.parse_args(argv)

    existing: dict[str, dict[str, Any]] = {}
    if arguments.out.exists():
        held = json.loads(arguments.out.read_text(encoding="utf-8"))
        existing = {str(m["endpoint_id"]): m for m in held.get("models", [])}

    models, failed = build(ENDPOINTS, read, today(), existing)
    document = {
        "models": models,
        "note": NOTE,
        "source": SCHEMA_URL.replace("{endpoint}", "<endpoint id>"),
    }
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    arguments.out.write_text(text, encoding="utf-8", newline="\n")

    priced = sum(1 for model in models if model.get("price"))
    print(f"wrote {len(models)} models to {arguments.out} ({priced} priced)")
    for endpoint in failed:
        print(f"  could not refresh {endpoint}; kept what was there", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
