"""`ssc kind list` and `ssc kind show` — how a caller discovers what kinds exist.

They exist because the set is extensible: an agent driving this tool cannot have the kinds
compiled into it, so it has to be able to ask. See
`adr:0008-a-kind-is-a-profile-not-an-enum`.
"""

from __future__ import annotations

import click

from ssc.cli import kinds
from ssc.cli import workspace as ws
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@click.group("kind", help="Discover the kinds this workspace has.")
def kind() -> None:
    """A noun, like `asset` and `image`: the verbs under it only observe."""


@ssc_command("list", help="Every kind available here, built-in and declared.")
def kind_list(*, dry_run: bool) -> Result:
    # No workspace is not an error: the built-ins are available anywhere, which is what lets
    # `snap` and `pixelart` run against loose PNGs and still speak of kinds.
    available = kinds.every(ws.find())
    return Result(
        "kind list",
        f"{len(available)} kind{'' if len(available) == 1 else 's'}",
        {
            "count": len(available),
            "kinds": [resolved.as_dict() for resolved in available.values()],
        },
        dry_run=dry_run,
    )


@ssc_command("show", help="One kind's resolved profile, and where each field came from.")
@click.argument("name")
def kind_show(name: str, *, dry_run: bool) -> Result:
    resolved = kinds.resolve(name, ws.find())
    declared = sorted(item for item, source in resolved.source.items() if source == kinds.DECLARED)
    return Result(
        "kind show",
        f"{name}: {len(declared)} field{'' if len(declared) == 1 else 's'} from ssc.yaml",
        resolved.as_dict(),
        dry_run=dry_run,
    )


kind.add_command(kind_list)
kind.add_command(kind_show)
