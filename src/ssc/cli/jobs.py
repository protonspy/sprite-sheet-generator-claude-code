"""`jobs/` — one file per paid call, written before the call is made.

In `cli/` and not `core/` for the reason `meta.py` is: this is nothing but IO and clock, and
a pure version of it would either break the rule or have no content.

See `adr:0005-a-job-always-exists` for why every provider call produces one of these, and
`adr:0006-job-store-rides-the-fal-client-handle-surface` for the capability that makes
`resume` from a fresh process possible — the recorded `(application, request_id)` pair is
the entire state, so nothing here holds a live handle.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from ssc.cli.atomic import replace as write_atomically
from ssc.cli.errors import SscError, UsageError
from ssc.cli.names import check_name
from ssc.cli.redact import scrubbed
from ssc.cli.workspace import Workspace

SCHEMA = 1

#: One file per job, never one index: two commands racing on a single document is a lost
#: write, and the premise here is that another process may be running while this one reads.
JOBS_DIR = "jobs"

STATES = ("submitted", "running", "done", "failed", "cancelled")

#: Absorbing. A provider answering `running` about a job we recorded as `done` is answering
#: about work already collected and paid for; believing it re-opens a job whose result is on
#: disk, and on some providers collecting twice costs twice.
TERMINAL = ("done", "failed", "cancelled")


class Provider(Protocol):
    """What the store needs of whatever spends the money.

    Three calls, each taking the pair as plain arguments and holding nothing between them —
    `adr:0006`'s finding restated as an interface. It is also what makes this testable with
    no network: a fake is a dozen lines.
    """

    def status(self, application: str, request_id: str) -> str: ...

    def result(self, application: str, request_id: str) -> dict[str, Any]: ...

    def cancel(self, application: str, request_id: str) -> None: ...


#: Empty here, and `specs/gen-fal/` registers `fal`. The job is the contract and generation
#: is one producer of it; shipping a provider from the store would make the store fal's.
PROVIDERS: dict[str, Provider] = {}


def provider_for(name: str) -> Provider | None:
    return PROVIDERS.get(name)


@dataclass(frozen=True)
class Job:
    """One paid call, as it is on disk."""

    id: str
    provider: str
    application: str
    model: str
    arguments: dict[str, Any]
    state: str = "submitted"
    request_id: str | None = None
    cost_usd: float | None = None
    error: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        *,
        id: str,
        provider: str,
        application: str,
        model: str,
        arguments: dict[str, Any],
        at: str,
    ) -> Job:
        return cls(
            id=id,
            provider=provider,
            application=application,
            model=model,
            arguments=dict(arguments),
            history=[{"state": "submitted", "at": at}],
        )

    def to_state(self, state: str, *, at: str, error: str | None = None) -> Job:
        """This job in `state`, with the move stamped (R2.1, R2.2, R2.3)."""
        if state not in STATES:
            raise SscError(
                "invalid-state",
                f"{state!r} is not a job state",
                fix=f"one of {', '.join(STATES)}",
            )
        if state == self.state:
            return self
        if self.state in TERMINAL:
            raise SscError(
                "job-finished",
                f"{self.id} is {self.state} and cannot become {state}",
                fix="a finished job keeps the result it was collected with",
            )
        return replace(
            self,
            state=state,
            error=error if error is not None else self.error,
            history=[*self.history, {"state": state, "at": at}],
        )

    def with_request_id(self, request_id: str, *, at: str) -> Job:
        """The id the provider handed back. A record written before the call cannot have one,
        and this second write is what makes recovery possible at all."""
        del at
        return replace(self, request_id=request_id)

    def with_cost(self, cost_usd: float | None) -> Job:
        return replace(self, cost_usd=cost_usd)

    @property
    def submitted_at(self) -> str:
        return self.history[0]["at"] if self.history else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "id": self.id,
            "provider": self.provider,
            "application": self.application,
            "request_id": self.request_id,
            "model": self.model,
            "arguments": self.arguments,
            "state": self.state,
            # Nullable on purpose, and `specs/budget-guard/` depends on it: a provider
            # metering by subscription reports no per-call cost, and a number here would
            # force it to lie with a zero.
            "cost_usd": self.cost_usd,
            "error": self.error,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Job:
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError(f"not a schema {SCHEMA} job record")
        missing = [
            key for key in ("id", "provider", "application", "model", "state") if key not in data
        ]
        if missing:
            raise ValueError(f"a job record needs {', '.join(missing)}")
        if data["state"] not in STATES:
            raise ValueError(f"{data['state']!r} is not a job state")

        # Shapes, not just presence. A `history` of the wrong shape used to pass here and
        # then fail far away, inside the sort in `every` — which turned one hand-edited file
        # into "no job in this workspace lists", the exact opposite of what R1.4 promises.
        # Every check here is one that keeps a bad record local to itself.
        arguments = data.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("a job record's arguments are an object")
        history = data.get("history") or []
        if not isinstance(history, list) or not all(
            isinstance(entry, dict) and {"state", "at"} <= set(entry) for entry in history
        ):
            raise ValueError("a job record's history is a list of {state, at}")
        cost = data.get("cost_usd")
        if (cost is not None and not isinstance(cost, (int, float))) or isinstance(cost, bool):
            raise ValueError("a job record's cost_usd is a number or null")
        request_id = data.get("request_id")
        if request_id is not None and not isinstance(request_id, str):
            raise ValueError("a job record's request_id is a string or null")
        error = data.get("error")
        if error is not None and not isinstance(error, str):
            raise ValueError("a job record's error is a string or null")

        return cls(
            id=str(data["id"]),
            provider=str(data["provider"]),
            application=str(data["application"]),
            model=str(data["model"]),
            arguments=dict(arguments),
            state=str(data["state"]),
            request_id=request_id,
            cost_usd=None if cost is None else float(cost),
            error=error,
            history=[dict(entry) for entry in history],
        )


def directory(workspace: Workspace) -> Path:
    return workspace.jobs


def path_of(workspace: Workspace, job_id: str) -> Path:
    # A job id becomes a path, so it is a name and gets a name's validation — the same gate
    # a key and a kind go through.
    check_name(job_id, "job id")
    return directory(workspace) / f"{job_id}.json"


def save(workspace: Workspace, job: Job) -> Path:
    """The record on disk, atomically and redacted (R1.2, R1.5).

    Redacted on the way *in*, not only on the way out. `jobs/` is git-ignored, which stops an
    accidental `git add .` and nothing else: a workspace gets zipped for a colleague, dropped
    into a support bundle, or `git add -f`'d, and a resolved argument holding a token would
    sit there in cleartext with no retention policy to remove it. What a credential-shaped
    key holds is not worth keeping — the prompt, the size and the seed, which is what makes
    a job readable afterwards, are not credential-shaped and survive untouched.
    """
    return write_atomically(
        path_of(workspace, job.id),
        json.dumps(scrubbed(job.as_dict()), indent=2, sort_keys=True).encode("utf-8"),
    )


def load(workspace: Workspace, job_id: str) -> Job:
    path = path_of(workspace, job_id)
    if not path.is_file():
        raise UsageError(
            "no-job",
            f"no job {job_id} in this workspace",
            fix="ssc job list",
        )
    try:
        return Job.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError) as refused:
        raise SscError(
            "job-invalid",
            f"{path} is not a readable job record: {refused}",
            fix="remove it, or fix it by hand",
        ) from refused


def every(workspace: Workspace, *, newest_first: bool = False) -> tuple[list[Job], list[str]]:
    """Every readable job, and the names of the files that were not (R1.1, R1.4).

    A broken file is a finding rather than the end of the scan: `list` is how somebody
    diagnoses a broken `jobs/`, and refusing to list makes the diagnostic unavailable exactly
    when it is needed.
    """
    where = directory(workspace)
    if not where.is_dir():
        return [], []

    found: list[Job] = []
    unreadable: list[str] = []
    for path in sorted(where.glob("*.json")):
        try:
            found.append(Job.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, RecursionError):
            # `RecursionError` is not a `ValueError`: deeply nested JSON raises it out of
            # `json.loads`, and uncaught it made one hostile file break the listing for
            # every job — which is the diagnostic somebody needs precisely then.
            unreadable.append(path.name)
    if newest_first:
        found.sort(key=lambda job: job.submitted_at, reverse=True)
    return found, unreadable


def submit(
    workspace: Workspace,
    job: Job,
    call: Callable[[Job], str],
    *,
    at: str,
) -> Job:
    """Record, then call, then record what the call returned (R1.1).

    The order is the whole store. Submitting first and recording after passes every test
    about what a job file holds and loses exactly one thing — the id of a request that was
    already billed, in the window where the process died.
    """
    save(workspace, job)
    try:
        request_id = call(job)
    except Exception as failed:
        # The record is the only evidence the call was attempted, so it stays and says so.
        save(workspace, job.to_state("failed", at=at, error=f"{type(failed).__name__}: {failed}"))
        raise

    submitted = job.with_request_id(request_id, at=at)
    save(workspace, submitted)
    return submitted
