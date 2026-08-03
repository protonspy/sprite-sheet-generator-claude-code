"""`ssc model list|show` — what each model accepts, before anything is paid for."""

from __future__ import annotations

import click

from ssc.cli import models
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


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
            "models": [
                {
                    "id": entry.endpoint,
                    "media": entry.media,
                    "role": entry.role,
                    "provider": entry.provider,
                    "source": entry.source,
                }
                for entry in found
            ],
        },
        dry_run=dry_run,
    )


@ssc_command("show", help="Every option one model accepts, with its type and its range.")
@click.argument("model_id")
def model_show(model_id: str, *, dry_run: bool) -> Result:
    registry = models.load()
    found = registry.get(model_id)
    return Result(
        "model show",
        f"{found.endpoint}: {len(found.options)} option"
        f"{'' if len(found.options) == 1 else 's'}, from the {found.source}",
        {
            **found.as_dict(),
            # The core mapping travels with the schema because it answers the question the
            # schema cannot: which of these fields is this project's `--seed`, and which
            # concepts this model simply does not have.
            "core": registry.core_for(found.endpoint),
        },
        dry_run=dry_run,
    )


model.add_command(model_list)
model.add_command(model_show)
