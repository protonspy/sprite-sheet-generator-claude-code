"""`ssc model list|show` — what each model accepts, before anything is paid for."""

from __future__ import annotations

from typing import Any

import click

from ssc.cli import models
from ssc.cli.main import ssc_command
from ssc.cli.output import Result

#: Travels with every price this reports (`specs/model-pricing/` R2.6). The provider writes
#: its price as prose, in a different billing shape per model, and `ssc` deliberately parses
#: no number out of it — so a reader has to be told, at the point of reading, that this is
#: indicative and that the amount actually charged is the one `ssc budget` recorded.
PRICE_CAVEAT = (
    "Indicative: the provider's own published text, not a quote, and not parsed into an "
    "amount. What a run cost is what `ssc budget` recorded."
)


@click.group("model", help="What the providers' models accept.")
def model() -> None:
    """A noun: everything under it observes, and none of it spends."""


@ssc_command("list", help="Every model, and what media it makes.")
@click.option("--media", type=click.Choice(["image", "video"]), default=None)
def model_list(media: str | None, *, dry_run: bool) -> Result:
    registry = models.load()
    found = registry.for_media(media)
    return Result(
        "model list",
        f"{len(found)} model{'' if len(found) == 1 else 's'}",
        {
            "count": len(found),
            # Which one a command reaches for when neither `ssc.yaml` nor the kind names one
            # (`specs/model-options/` R1.7). An agent choosing a model needs the default to be
            # in the listing rather than something it learns by generating.
            "defaults": {
                name: endpoint
                for name, endpoint in sorted(registry.defaults.items())
                if media is None or name == media
            },
            "models": [
                {
                    "id": entry.endpoint,
                    "media": entry.media,
                    "role": entry.role,
                    "provider": entry.provider,
                    "source": entry.source,
                    "default": registry.default_for(entry.media) == entry.endpoint,
                    # A boolean here and the sentence in `show` (R2.3): a paragraph of
                    # Markdown per row would make the one listing an agent scans unreadable.
                    "priced": entry.price is not None,
                }
                for entry in found
            ],
        },
        dry_run=dry_run,
    )


def resolved_core(registry: models.Registry, found: models.Model) -> dict[str, Any]:
    """Each core option, the field this model spells it with, and what it takes
    (`specs/model-options/` R3.6).

    The bare mapping beside it says *which field*; this says *what the field accepts*, which is
    the half a caller needs to choose a value without a second command. A concept the model
    does not have is `null` rather than missing: absent and "no such thing" read the same to a
    reader and mean different things to a call.
    """
    described: dict[str, Any] = {}
    for concept in models.CONCEPTS:
        mapped = registry.core_for(found.endpoint).get(concept)
        if mapped is None:
            described[concept] = None
        elif isinstance(mapped, dict):
            # `size`, which is a shape rather than one field — `reconcile_size` reads it.
            described[concept] = {"shape": mapped}
        else:
            option = found.options.get(mapped)
            described[concept] = {
                "field": mapped,
                **({} if option is None else option.as_dict()),
            }
    return described


@ssc_command("show", help="Every option one model accepts, with its type and its range.")
@click.argument("model_id")
def model_show(model_id: str, *, dry_run: bool) -> Result:
    registry = models.load()
    found = registry.get(model_id)
    priced = "" if found.price is None else f", priced {found.price['fetched']}"
    return Result(
        "model show",
        f"{found.endpoint}: {len(found.options)} option"
        f"{'' if len(found.options) == 1 else 's'}, from the {found.source}{priced}",
        {
            **found.as_dict(),
            # Beside the price rather than in the file it came from: the caveat is this
            # command's statement about what it is reporting, and `models.json` is
            # regenerated wholesale by a script that would carry no such sentence.
            "price_caveat": PRICE_CAVEAT,
            # The core mapping travels with the schema because it answers the question the
            # schema cannot: which of these fields is this project's `--seed`, and which
            # concepts this model simply does not have.
            "core": registry.core_for(found.endpoint),
            "core_options": resolved_core(registry, found),
            "default": registry.default_for(found.media) == found.endpoint,
        },
        dry_run=dry_run,
    )


model.add_command(model_list)
model.add_command(model_show)
