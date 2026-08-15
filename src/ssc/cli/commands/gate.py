"""`ssc gate list|open|approve|reject` — the surface over `gates/`.

Nothing here asks a question. A pending decision is a record on disk and exit `3`, which is
what lets a run stop, a session die, and a second session pick the decision up from the
repository rather than from a conversation nobody kept.
"""

from __future__ import annotations

import click

from ssc.cli import gates
from ssc.cli import workspace as ws
from ssc.cli.errors import EXIT_GATE_PENDING
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@click.group("gate", help="Decisions reserved for a human, held as state in the workspace.")
def gate() -> None:
    """A noun, like `job`: everything under it is about something that already exists."""


def opened(existing: gates.Gate, *, dry_run: bool = False) -> Result:
    """What a pending gate reports (R2.1, R2.2, R2.3).

    Exit `3` on a `Result` rather than by raising: the gate is the useful part, and a caller
    that has just been stopped is exactly the one that needs to know what it was stopped by.
    """
    return Result(
        "gate open",
        f"{existing.id} is pending: {existing.question}",
        existing.as_dict(),
        dry_run=dry_run,
        exit_code=EXIT_GATE_PENDING,
    )


@ssc_command(
    "open",
    help="Open a decision and stop, or report the one already open.",
    needs_workspace=True,
)
@click.option("--material", default=None, help="Where to look — a review directory, usually.")
@click.option("--question", required=True, help="What the person is being asked.")
@click.option("--topic", required=True, help="What kind of decision this is.")
@click.argument("subject")
def gate_open(
    subject: str,
    topic: str,
    question: str,
    material: str | None,
    *,
    dry_run: bool,
    workspace: ws.Workspace,
) -> Result:
    existing = gates.find(workspace, subject, topic)
    if existing is not None:
        # R2.2 — one gate per subject and topic. A second would make "is this decided?" a
        # question with two answers.
        if existing.pending:
            return opened(existing, dry_run=dry_run)
        return Result(
            "gate open",
            f"{existing.id} was already {existing.state}",
            existing.as_dict(),
            dry_run=dry_run,
        )

    fresh = gates.Gate.new(
        subject=subject,
        topic=topic,
        question=question,
        material=material,
        at=gates.now(),
    )

    # R3.2 — a topic this workspace has already settled opens already approved.
    adopted = gates.defaults(workspace).get(topic)
    if adopted is not None:
        inherited = fresh.inheriting(adopted, at=gates.now())
        if not dry_run:
            gates.save(workspace, inherited)
        # R3.3 — nothing is outstanding, so this does not exit `3`.
        return Result(
            "gate open",
            f"{inherited.id} is approved, inherited from {adopted.came_from}",
            inherited.as_dict(),
            dry_run=dry_run,
        )

    if not dry_run:
        gates.save(workspace, fresh)
    return opened(fresh, dry_run=dry_run)


@ssc_command("list", help="Every gate, with its state.", needs_workspace=True)
def gate_list(*, dry_run: bool, workspace: ws.Workspace) -> Result:
    """R2.6 — exit `0`. A query that reported a pending gate and exited `3` would make
    "I could not tell you" and "I told you, and it is pending" the same value."""
    found, unreadable = gates.every(workspace)
    pending = [one for one in found if one.pending]
    adopted = gates.defaults(workspace)
    return Result(
        "gate list",
        f"{len(found)} gate{'' if len(found) == 1 else 's'}, {len(pending)} pending"
        # In the line a person reads, not only in the JSON (`specs/generation-gates/` R4.1).
        # `adr:0014` asks for it by name: since a step may bill, a standing approval on a
        # topic that generates is a standing authorisation to spend, and the ADR's own
        # consequence is that it has to be visible in one place somebody goes and looks at.
        + (f"; standing approval for {', '.join(sorted(adopted))}" if adopted else ""),
        {
            "count": len(found),
            "pending": len(pending),
            "gates": [one.as_dict() for one in sorted(found, key=lambda one: one.id)],
            "defaults": {topic: one.as_dict() for topic, one in sorted(adopted.items())},
            # Reported rather than raised: `list` is how somebody diagnoses a broken `gates/`.
            "unreadable": unreadable,
        },
        dry_run=dry_run,
    )


@ssc_command(
    "approve",
    help="Take the decision, and optionally adopt it for the topic.",
    needs_workspace=True,
)
@click.option("--default", "as_default", is_flag=True, help="Adopt this for the whole topic.")
@click.option("--choice", default=None, help="Which one was chosen — a variant name, usually.")
@click.argument("gate_id")
def gate_approve(
    gate_id: str,
    choice: str | None,
    as_default: bool,
    *,
    dry_run: bool,
    workspace: ws.Workspace,
) -> Result:
    """R2.4, R3.1, and R1.3 through `decided_as`."""
    at = gates.now()
    decided = gates.load(workspace, gate_id).decided_as(gates.APPROVED, at=at, choice=choice)
    if dry_run:
        return Result(
            "gate approve", f"would approve {decided.id}", decided.as_dict(), dry_run=True
        )

    gates.save(workspace, decided)
    adopted = gates.adopt(workspace, decided, at=at) if as_default else None
    return Result(
        "gate approve",
        f"{decided.id} approved" + (f", adopted for {decided.topic}" if adopted else ""),
        {**decided.as_dict(), "adopted": adopted.as_dict() if adopted else None},
    )


@ssc_command("reject", help="Refuse what is behind the gate, and say why.", needs_workspace=True)
@click.option("--why", required=True, help="The reason, which is the useful part.")
@click.argument("gate_id")
def gate_reject(gate_id: str, why: str, *, dry_run: bool, workspace: ws.Workspace) -> Result:
    """R2.5. There is no `--default` here on purpose: a rejection says *this material* is no
    good, which is not a decision another subject can inherit."""
    decided = gates.load(workspace, gate_id).decided_as(gates.REJECTED, at=gates.now(), why=why)
    if dry_run:
        return Result("gate reject", f"would reject {decided.id}", decided.as_dict(), dry_run=True)

    gates.save(workspace, decided)
    return Result("gate reject", f"{decided.id} rejected: {why}", decided.as_dict())


gate.add_command(gate_open)
gate.add_command(gate_list)
gate.add_command(gate_approve)
gate.add_command(gate_reject)
