"""`ssc budget` — what this workspace has spent, against what it declared it would.

Reporting only. The refusals live inside `gen.run`, because a rule an agent has to remember
to call is a rule that gets forgotten under load, and this particular failure produces
correct output — see `specs/budget-guard/design.md`.
"""

from __future__ import annotations

from ssc.cli import budget as money
from ssc.cli import config
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace


@ssc_command("budget", help="Report what this workspace has spent.", needs_workspace=True)
def budget(*, dry_run: bool, workspace: Workspace) -> Result:
    """R3.1, R3.3 — the total, the ceiling, and what the total does not know.

    `unpriced` is reported next to the amount rather than folded into it. A provider metering
    by subscription reports no per-call cost, and a total that quietly counted those as zero
    would say a workspace spent nothing when it spent all month.
    """
    del dry_run  # nothing is written, so there is nothing to not-write
    total = money.load(workspace)
    limits = money.limits_of(config.document(workspace))

    remaining = None if limits.max_usd is None else round(limits.max_usd - total.spent_usd, 6)
    if limits.max_usd is None:
        summary = f"${total.spent_usd:.2f} over {total.calls} call{'' if total.calls == 1 else 's'}"
    else:
        summary = f"${total.spent_usd:.2f} of ${limits.max_usd:.2f}"
    if total.unpriced:
        summary += f", and {total.unpriced} call{'' if total.unpriced == 1 else 's'} unpriced"

    return Result(
        "budget",
        summary,
        {
            **total.as_dict(),
            "max_usd": limits.max_usd,
            "warn_at": limits.warn_at,
            "remaining_usd": remaining,
        },
    )
