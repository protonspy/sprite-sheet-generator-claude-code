"""Refresh `src/ssc/data/models.json`, the offline fallback for `ssc model show`.

Fal publishes an OpenAPI document per endpoint, unauthenticated, at

    https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint id>

so the parameter schemas are read rather than transcribed. That is what makes the shipped
copy a *fallback*: `model-registry` reads the same URL at runtime and only falls back to
this file when the network is unavailable, because a registry baked into the package is
stale the week after Fal changes a model.

    python scripts/fetch_model_schemas.py
    python scripts/fetch_model_schemas.py --check   # fail if the shipped copy has drifted
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

OPENAPI = "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={}"
REGISTRY = Path(__file__).resolve().parent.parent / "src/ssc/data/models.json"

# The endpoints `plans/ssc-pipeline.md` names, plus the sub-endpoint each one needs to be
# useful here: `ssc gen image` passes the anchor image as a reference, which on both image
# models is a different endpoint from text-to-image.
ENDPOINTS: list[tuple[str, str, str]] = [
    ("image", "fal-ai/nano-banana-2", "text-to-image"),
    ("image", "fal-ai/nano-banana-2/edit", "image-to-image"),
    ("image", "fal-ai/gpt-image-1.5", "text-to-image"),
    ("image", "fal-ai/gpt-image-1.5/edit", "image-to-image"),
    ("video", "xai/grok-imagine-video/image-to-video", "image-to-video"),
    ("image", "fal-ai/birefnet/v2", "background-removal"),
]


def fetch(endpoint_id: str) -> dict[str, Any]:
    response = httpx.get(OPENAPI.format(quote(endpoint_id, safe="/")), timeout=30.0)
    response.raise_for_status()
    document: dict[str, Any] = response.json()
    return document


def input_schema(document: dict[str, Any], endpoint_id: str) -> dict[str, Any]:
    """Follow the POST on the endpoint's own path to its request body schema."""
    path = document["paths"][f"/{endpoint_id}"]
    ref = path["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schemas = document["components"]["schemas"]
    root = schemas[ref.rsplit("/", 1)[-1]]

    # Enums and nested objects arrive as sibling components; carry the ones actually
    # referenced so the schema validates on its own with no network.
    defs: dict[str, Any] = {}
    pending = [root]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            target = node.get("$ref")
            if isinstance(target, str) and target.startswith("#/components/schemas/"):
                name = target.rsplit("/", 1)[-1]
                if name not in defs:
                    defs[name] = schemas[name]
                    pending.append(schemas[name])
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)

    schema = dict(root)
    if defs:
        schema["$defs"] = defs
    return schema


def build() -> dict[str, Any]:
    models = []
    for media, endpoint_id, role in ENDPOINTS:
        document = fetch(endpoint_id)
        metadata = document["info"].get("x-fal-metadata", {})
        models.append(
            {
                "provider": "fal",
                "media": media,
                "role": role,
                "endpoint_id": endpoint_id,
                "category": metadata.get("category"),
                "about": metadata.get("about"),
                "documentation_url": metadata.get("documentationUrl"),
                "input_schema": input_schema(document, endpoint_id),
            }
        )
        print(f"  {endpoint_id}", flush=True)
    return {
        "source": "https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint id>",
        "note": "Offline fallback; the runtime reads the same URL. Refreshed by "
        "scripts/fetch_model_schemas.py.",
        "models": models,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report drift instead of writing")
    args = parser.parse_args()

    print(f"fetching {len(ENDPOINTS)} endpoints", flush=True)
    fresh = json.dumps(build(), indent=2, sort_keys=True) + "\n"

    if args.check:
        if not REGISTRY.exists():
            print(f"{REGISTRY} is missing")
            return 2
        if REGISTRY.read_text(encoding="utf-8") != fresh:
            print(f"{REGISTRY} has drifted from what Fal publishes today")
            return 2
        print(f"{REGISTRY} matches what Fal publishes today")
        return 0

    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(fresh, encoding="utf-8")
    print(f"wrote {REGISTRY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
