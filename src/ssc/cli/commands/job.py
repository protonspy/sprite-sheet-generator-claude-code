"""`ssc job list|status|wait|cancel|resume` — the surface over `jobs/`.

`resume` is why the rest exists: a fresh process reads an id off disk and collects a result
it never submitted. See `adr:0005-a-job-always-exists`.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import click

from ssc.cli import jobs
from ssc.cli import workspace as ws
from ssc.cli.errors import SscError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result

#: How long `wait` sleeps between asks. Small enough to feel immediate on a fast job, large
#: enough that a slow one is not a thousand requests.
POLL_SECONDS = 2.0

#: `wait` without a deadline would be a command that never returns, which inside a harness is
#: indistinguishable from a hang.
DEFAULT_TIMEOUT = 600.0


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@click.group("job", help="Look at, wait for, cancel and collect paid work.")
def job() -> None:
    """A noun, because everything under it is about something that already exists."""


def unreachable(record: jobs.Job, why: str) -> Result:
    """What is on disk, and why it could go no further (R3.7).

    Not an error: the record is still the useful part, and "this build has no fal support" is
    a different problem from "your job failed".
    """
    return Result(
        "job",
        f"{record.id} is {record.state}; {why}",
        {**record.as_dict(), "asked_provider": False, "why": why},
    )


def ask(workspace: ws.Workspace, record: jobs.Job) -> tuple[jobs.Job, Result | None]:
    """The job as the provider sees it, or a reason it could not be asked."""
    if record.state in jobs.TERMINAL:
        return record, None
    provider = jobs.provider_for(record.provider)
    if provider is None:
        return record, unreachable(record, f"no provider named {record.provider!r} is available")
    if record.request_id is None:
        return record, unreachable(record, "it has no request id, so it was never submitted")

    moved = record.to_state(provider.status(record.application, record.request_id), at=now())
    if moved is not record:
        jobs.save(workspace, moved)
    return moved, None


@ssc_command("list", help="Every job, most recently submitted first.", needs_workspace=True)
def job_list(*, dry_run: bool, workspace: ws.Workspace) -> Result:
    found, unreadable = jobs.every(workspace, newest_first=True)
    return Result(
        "job list",
        f"{len(found)} job{'' if len(found) == 1 else 's'}",
        {
            "count": len(found),
            "jobs": [record.as_dict() for record in found],
            # Reported rather than raised: `list` is how somebody diagnoses a broken `jobs/`.
            "unreadable": unreadable,
        },
        dry_run=dry_run,
    )


@ssc_command(
    "status",
    help="Where one job is, asking the provider if it is unfinished.",
    needs_workspace=True,
)
@click.argument("job_id")
def job_status(job_id: str, *, dry_run: bool, workspace: ws.Workspace) -> Result:
    record, blocked = ask(workspace, jobs.load(workspace, job_id))
    if blocked is not None:
        return blocked
    return Result("job status", f"{record.id} is {record.state}", record.as_dict(), dry_run=dry_run)


@ssc_command(
    "wait", help="Keep asking until the job finishes or the deadline passes.", needs_workspace=True
)
@click.option("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Seconds before giving up.")
@click.option("--poll", type=float, default=POLL_SECONDS, help="Seconds between asks.")
@click.argument("job_id")
def job_wait(
    job_id: str, timeout: float, poll: float, *, dry_run: bool, workspace: ws.Workspace
) -> Result:
    """R3.3 — and it says which of the two happened, because a caller that cannot tell
    "finished" from "gave up" has to guess whether the money bought anything."""
    # Not `<= 0`: every comparison against `nan` is False, so `--timeout nan` walked
    # through that guard, made the deadline `nan`, and left the poll loop running forever —
    # a command that never returns, which inside a harness is exactly what `wait` exists to
    # avoid looking like. `inf` is refused for both, and on the poll side for a second
    # reason: `time.sleep(inf)` is an `OverflowError`, not a long sleep.
    if not timeout > 0 or not poll > 0 or float("inf") in (timeout, poll):
        raise SscError(
            "invalid-wait",
            "--timeout and --poll are durations, and both have to be above zero",
            fix="leave them out for the defaults",
        )

    record = jobs.load(workspace, job_id)
    deadline = time.monotonic() + timeout
    while True:
        record, blocked = ask(workspace, record)
        if blocked is not None:
            return blocked
        if record.state in jobs.TERMINAL:
            return Result(
                "job wait",
                f"{record.id} is {record.state}",
                {**record.as_dict(), "timed_out": False},
                dry_run=dry_run,
            )
        if time.monotonic() >= deadline:
            return Result(
                "job wait",
                f"{record.id} is still {record.state} after {timeout:g}s",
                {**record.as_dict(), "timed_out": True},
                dry_run=dry_run,
            )
        time.sleep(poll)


@ssc_command(
    "cancel", help="Ask the provider to cancel, and record what happened.", needs_workspace=True
)
@click.argument("job_id")
def job_cancel(job_id: str, *, dry_run: bool, workspace: ws.Workspace) -> Result:
    record = jobs.load(workspace, job_id)
    if record.state in jobs.TERMINAL:
        return Result(
            "job cancel",
            f"{record.id} is already {record.state}",
            {**record.as_dict(), "cancelled": False},
            dry_run=dry_run,
        )

    provider = jobs.provider_for(record.provider)
    if provider is None:
        return unreachable(record, f"no provider named {record.provider!r} is available")
    if record.request_id is None:
        return unreachable(record, "it has no request id, so there is nothing to cancel")
    if dry_run:
        return Result(
            "job cancel",
            f"would cancel {record.id}",
            {**record.as_dict(), "cancelled": False},
            dry_run=True,
        )

    provider.cancel(record.application, record.request_id)
    cancelled = record.to_state("cancelled", at=now())
    jobs.save(workspace, cancelled)
    return Result(
        "job cancel", f"{cancelled.id} cancelled", {**cancelled.as_dict(), "cancelled": True}
    )


@ssc_command(
    "resume", help="Collect a finished job's result from what is on disk.", needs_workspace=True
)
@click.argument("job_id")
def job_resume(job_id: str, *, dry_run: bool, workspace: ws.Workspace) -> Result:
    """R3.5, and the reason the store exists: nothing here needs the process that paid."""
    record, blocked = ask(workspace, jobs.load(workspace, job_id))
    if blocked is not None:
        return blocked

    if record.state != "done":
        return Result(
            "job resume",
            f"{record.id} is {record.state}, so there is nothing to collect yet",
            {**record.as_dict(), "collected": False},
            dry_run=dry_run,
        )

    provider = jobs.provider_for(record.provider)
    if provider is None:
        return unreachable(record, f"no provider named {record.provider!r} is available")
    if record.request_id is None:
        return unreachable(record, "it has no request id, so there is nothing to collect")

    collected: dict[str, Any] = provider.result(record.application, record.request_id)
    return Result(
        "job resume",
        f"{record.id} collected",
        {**record.as_dict(), "collected": True, "result": collected},
        dry_run=dry_run,
    )


job.add_command(job_list)
job.add_command(job_status)
job.add_command(job_wait)
job.add_command(job_cancel)
job.add_command(job_resume)
