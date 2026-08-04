"""What a call is allowed to cost, and what has been spent.

Three things, and the order they run in inside `gen.run` is the design: the free path
refuses first because it holds whether or not there is a ceiling, the cache is consulted
next because a hit spends nothing, and only then is the ceiling asked. See
`specs/budget-guard/design.md`.

Nothing here submits anything. It decides whether a submission may happen, and records what
one cost afterwards.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ssc.cli import jobs
from ssc.cli.atomic import replace as write_atomically
from ssc.cli.errors import SscError, UsageError
from ssc.cli.workspace import Workspace


def _no_constants(name: str) -> float:
    raise ValueError(f"{name} is not a number a budget can hold")


#: What the running total lives in. Beside `jobs/`, not inside it: a job is one call and this
#: is every call, and putting it in `jobs/` would make `ssc job list` have to skip a file.
TOTAL_NAME = "budget.json"

SCHEMA = 1

#: How long a writer waits for the lock before giving up. Generously above any real
#: read-modify-write of a few hundred bytes, and short enough that a stale lock from a killed
#: process is an error a person sees rather than a command that hangs for ever.
LOCK_TIMEOUT_SECONDS = 10.0

LOCK_POLL_SECONDS = 0.02


@dataclass(frozen=True)
class Limits:
    """What `ssc.yaml` says a workspace may spend.

    Both nullable, and `max_usd` being absent is not "zero" — R2.4 says a workspace that
    declares no ceiling refuses nothing. A zero ceiling is a workspace that has said, out
    loud, that it will not pay for anything, and that is a different statement.
    """

    max_usd: float | None = None
    warn_at: float | None = None

    @property
    def declared(self) -> bool:
        return self.max_usd is not None


@dataclass(frozen=True)
class Total:
    """What a workspace has spent, and what it could not price (R3.3).

    Two numbers rather than one. A provider metering by subscription reports no per-call
    cost, and folding that into the amount as a zero would report a workspace that spent all
    month as having spent nothing — `job-store` made `cost_usd` nullable for this reason and
    this is the same decision one level up.
    """

    spent_usd: float = 0.0
    calls: int = 0
    unpriced: int = 0

    def plus(self, cost_usd: float | None) -> Total:
        if cost_usd is None:
            return Total(self.spent_usd, self.calls + 1, self.unpriced + 1)
        return Total(round(self.spent_usd + cost_usd, 6), self.calls + 1, self.unpriced)

    def settled(self, cost_usd: float) -> Total:
        """A call already counted, now that its price is known (R3.7).

        The call was added at submission with no amount, because at submission there is no
        amount to add. This folds the figure in without counting the call twice: the amount
        rises, `calls` does not move, and one call leaves `unpriced`.
        """
        return Total(
            round(self.spent_usd + cost_usd, 6),
            self.calls,
            max(0, self.unpriced - 1),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "spent_usd": self.spent_usd,
            "calls": self.calls,
            "unpriced": self.unpriced,
        }


def limits_of(settings: dict[str, Any]) -> Limits:
    """`budget:` out of `ssc.yaml`, which `cli/config.py` has already read and shape-checked
    as a document (R2.1)."""
    found = settings.get("budget")
    if found is None:
        return Limits()
    if not isinstance(found, dict):
        raise SscError(
            "invalid-config",
            f"`budget` is a {type(found).__name__}, not a map of settings",
            fix="write it as `budget:` with `max_usd` and `warn_at` under it",
        )
    return Limits(
        max_usd=_amount(found.get("max_usd"), "budget.max_usd"),
        warn_at=_amount(found.get("warn_at"), "budget.warn_at"),
    )


def _amount(value: Any, name: str) -> float | None:
    if value is None:
        return None
    # `bool` is an `int`, and `max_usd: true` is a configuration mistake rather than a
    # ceiling of one dollar.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SscError(
            "invalid-config",
            f"{name} is {value!r}, which is not an amount",
            fix="write it as a number of US dollars, for example 5.00",
        )
    # Before the sign check, and this ordering is the whole point: `nan < 0` is `False`, so a
    # `NaN` ceiling walks past a negativity test and then makes every later comparison in
    # `check` `False` as well — a ceiling that refuses nothing, silently, for ever. YAML
    # spells it `.nan` and `.inf`, so this is reachable from a hand-edited config.
    if not math.isfinite(float(value)):
        raise SscError(
            "invalid-config",
            f"{name} is {value}, which is not a finite amount",
            fix="write it as a number of US dollars, for example 5.00",
        )
    if value < 0:
        raise SscError(
            "invalid-config",
            f"{name} is {value}, and an amount cannot be negative",
            fix="write it as a number of US dollars, for example 5.00",
        )
    return float(value)


def path_of(workspace: Workspace) -> Path:
    return workspace.root / TOTAL_NAME


def _finite(value: Any, name: str, target: Path) -> float:
    """A number out of `budget.json` that can be compared against a ceiling.

    The same `NaN` hole as `_amount`, arriving from the other side. `json.loads` accepts the
    non-standard `NaN` and `Infinity` tokens by default, and `document.get(...) or 0.0` keeps
    a `NaN` rather than defaulting it, because `NaN` is truthy. A total that cannot be
    compared is a ceiling that is off, so this fails closed.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SscError(
            "invalid-budget",
            f"{target} records {name} as {value!r}, which is not a number",
            fix="delete it to start the total again",
        ) from None
    if not math.isfinite(number) or number < 0:
        raise SscError(
            "invalid-budget",
            f"{target} records {name} as {number}, which cannot be a running total",
            fix="delete it to start the total again",
        )
    return number


def load(workspace: Workspace) -> Total:
    """What has been spent so far, or nothing where no call has been made yet."""
    target = path_of(workspace)
    if not target.is_file():
        return Total()
    try:
        # `parse_constant` is what refuses the tokens `json.loads` accepts by extension:
        # bare `NaN`, `Infinity` and `-Infinity` are not JSON, and each of them would reach
        # a comparison against the ceiling and make it `False`.
        document = json.loads(
            target.read_text(encoding="utf-8"),
            parse_constant=_no_constants,
        )
    except (OSError, ValueError) as unreadable:
        raise SscError(
            "invalid-budget",
            f"{target} could not be read: {unreadable}",
            fix="delete it to start the total again, or restore it from a backup",
        ) from unreadable

    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise SscError(
            "invalid-budget",
            f"{target} is not a schema {SCHEMA} budget record",
            fix="delete it to start the total again",
        )
    return Total(
        spent_usd=_finite(document.get("spent_usd") or 0.0, "spent_usd", target),
        calls=int(_finite(document.get("calls") or 0, "calls", target)),
        unpriced=int(_finite(document.get("unpriced") or 0, "unpriced", target)),
    )


def _load_unlocked(workspace: Workspace) -> Total:
    """`load`, for a caller that is already holding the lock."""
    return load(workspace)


def _write_unlocked(workspace: Workspace, total: Total) -> None:
    write_atomically(
        path_of(workspace),
        (json.dumps(total.as_dict(), indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _add_unlocked(workspace: Workspace, cost_usd: float | None) -> Total:
    updated = _load_unlocked(workspace).plus(cost_usd)
    _write_unlocked(workspace, updated)
    return updated


def record(workspace: Workspace, cost_usd: float | None) -> Total:
    """Add one call to the running total, losing no concurrent update (R3.2, R3.3, R3.4).

    Under a lock, and the lock is the point. `atomic.replace` makes each *write* whole; it
    does not make read-modify-write atomic, and a running total is exactly that. Two
    `gen` commands finishing together would each read the same figure, each add their own
    cost to it, and the second write would land — losing the first call's money silently,
    which is the one way this feature can be worse than not existing.
    """
    with _locked(workspace):
        return _add_unlocked(workspace, cost_usd)


def count(workspace: Workspace, job: jobs.Job) -> tuple[Total, jobs.Job]:
    """Add this call to the running total at the moment it is submitted (R3.2, R3.5).

    **At submission, not at collection**, and the second review is why. Counting when a
    result is collected leaves everything submitted-and-not-yet-collected invisible to the
    ceiling — and `--no-wait` is an ordinary supported flag, so a caller looping it bills the
    provider indefinitely while `check` compares against a total that never moves. The money
    is committed when `jobs.submit` returns, so that is when the call is counted.

    It is counted as *unpriced*, because at submission there is no amount to add. `settle`
    folds in the real figure later, without counting the call again.

    The whole read-check-write is under the lock rather than only the write: the flag is on
    the job, two routes may hold the same job, and checking a caller's stale copy outside the
    lock is what would let one call be counted twice.
    """
    with _locked(workspace):
        current = jobs.load(workspace, job.id) if _recorded(workspace, job) else job
        if current.counted:
            return _load_unlocked(workspace), current
        total = _add_unlocked(workspace, current.cost_usd)
        marked = current.as_counted()
        jobs.save(workspace, marked)
        return total, marked


def settle(workspace: Workspace, job: jobs.Job, cost_usd: float | None) -> tuple[Total, jobs.Job]:
    """Fold a call's real price in, once it is known (R3.7).

    Separate from `count` because the two happen at different moments and only one of them
    can happen at submission. A provider that never prices a call leaves this doing nothing,
    which is the case today: `jobs.Job.with_cost` has no caller, so every call stays
    unpriced and the ceiling bounds a count rather than an amount until `specs/gen-fal/`
    wires a figure through.
    """
    if cost_usd is None or job.cost_usd is not None:
        return load(workspace), job
    with _locked(workspace):
        updated = _load_unlocked(workspace).settled(cost_usd)
        _write_unlocked(workspace, updated)
        priced = job.with_cost(cost_usd)
        jobs.save(workspace, priced)
        return updated, priced


def _recorded(workspace: Workspace, job: jobs.Job) -> bool:
    return jobs.path_of(workspace, job.id).is_file()


class _locked:
    """`O_EXCL` on a sibling lock file, waited for and always released.

    A directory-based or `fcntl`-based lock would each be better on one platform and absent
    on the other; an exclusive create is the one primitive that means the same thing on both
    and that this project already relies on in `Directory.write_new`.
    """

    def __init__(self, workspace: Workspace) -> None:
        self._path = workspace.root / f"{TOTAL_NAME}.lock"
        self._fd: int | None = None

    def __enter__(self) -> None:
        give_up_at = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                self._fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return
            except FileExistsError:
                if time.monotonic() >= give_up_at:
                    raise UsageError(
                        "budget-locked",
                        f"{self._path} has been held for over {LOCK_TIMEOUT_SECONDS:g}s",
                        fix="another ssc command may be running; if none is, delete that file",
                    ) from None
                time.sleep(LOCK_POLL_SECONDS)

    def __exit__(self, *_: object) -> None:
        if self._fd is not None:
            os.close(self._fd)
        # Released even where the body raised: a lock that outlives a failed command turns
        # one error into every later command erroring.
        self._path.unlink(missing_ok=True)


@dataclass(frozen=True)
class Free:
    """A deterministic command that covers a paid one.

    `exact` is the difference between refusing and reporting (R1.1 against R1.2). It is a
    property of the pair of commands, decided where the free command is understood, and not
    something this module infers.
    """

    command: str
    why: str
    exact: bool


#: Matched on a whole word. `--var direction=West, seen from the character's left` is
#: ordinary phrasing, and a substring match would find "east" inside "beast".
_EAST = re.compile(r"\beast(ward|erly)?\b", re.IGNORECASE)
_WEST = re.compile(r"\bwest(ward|erly)?\b", re.IGNORECASE)


class Asked(Protocol):
    """The three fields the free path reads.

    A protocol rather than `Any`, so mypy checks the four call sites: `Any` there was buying
    nothing and hiding whether `variables` was reliably present — which is what made the
    `getattr` below look necessary.
    """

    @property
    def verb(self) -> str: ...

    @property
    def prompt(self) -> str | None: ...

    @property
    def variables(self) -> dict[str, str]: ...


def covered_by(ask: Asked, stages: tuple[str, ...]) -> Free | None:
    """The free command that does this, if one does (R1.1, R1.2, R1.3).

    Both cases read what the caller already said rather than a flag they could unset — the
    plan is explicit that an override would make the cheap path something you opt into
    rather than the default, which is the wrong way round.
    """
    if ask.verb == "gen expand" and not (ask.prompt or "").strip():
        # No content prompt means the caller wants *canvas*, and canvas is free: padding
        # with the key colour is what the outpaint would have produced, so paying for it
        # buys a `np.pad`. A prompt means invented content, which is what a model is for.
        return Free(
            command="ssc tool expand --fill chroma",
            why="widening a canvas with no prompt is padding, which is deterministic",
            exact=True,
        )

    direction = ask.variables.get("direction", "")
    if ask.verb == "gen image" and _EAST.search(direction):
        mirrored = [stage for stage in stages if _WEST.search(stage)]
        if mirrored:
            # Reported, not refused, and `specs/budget-guard/` R1.2 carries the argument:
            # the plan calls this an exact equivalence and the wiki records that it breaks
            # on asymmetry — a sheath, a scar, a pauldron on one shoulder — invisibly.
            return Free(
                command=f"ssc tool mirror --in {mirrored[0]}",
                why=f"{mirrored[0]} exists, and East is usually a horizontal flip of West",
                exact=False,
            )
    return None


def clear(free: Free | None) -> None:
    """Refuse where the free command is exactly equivalent, and say nothing otherwise."""
    if free is not None and free.exact:
        raise UsageError(
            "free-path",
            f"{free.why} — this call costs money and does not need to",
            fix=free.command,
        )


def estimate_for(registry: Any, call: Any) -> float | None:
    """What this call is expected to cost, where anyone says (R2.6).

    Nothing does, today. No model in the registry publishes a per-call price and this leaf
    ships no price table — a hard-coded figure is wrong the week a model is repriced, and
    wrong in the direction that spends money. So this is the seam a published price would
    arrive through, and until one does the ceiling does its work through `Total.spent_usd`
    rather than through a forecast (R2.2 against R2.3).
    """
    del registry, call
    return None


def check(limits: Limits, total: Total, estimate: float | None) -> str | None:
    """Whether this call may happen, and what to say about it (R2.2, R2.3, R2.4, R2.5).

    Returns a warning to report, or `None` where there is nothing to say. Refuses by raising,
    because a refusal is not a return value a caller should be able to ignore.

    Two refusals, and the first is the one that works. R2.2 asks whether the money already
    spent has reached the ceiling, which needs no estimate and is what actually stops a run.
    R2.3 is the tighter check for the day a provider publishes a price. Where nothing is
    known, the call proceeds: refusing every unpriced call would make `gen` unusable against
    most models, which converts a missing number into a broken tool.
    """
    if not limits.declared or limits.max_usd is None:
        return None

    # `limits_of` already refuses a non-finite ceiling, so this is the second line rather
    # than the first. It is here because the property worth holding is about `check` and not
    # about the parser: a ceiling that cannot be compared must never be a ceiling that
    # admits everything, however the `Limits` was built.
    if not math.isfinite(limits.max_usd):
        raise SscError(
            "invalid-config",
            f"the ceiling is {limits.max_usd}, which cannot be compared against a total",
            fix="write budget.max_usd as a number of US dollars, for example 5.00",
        )

    if total.spent_usd >= limits.max_usd:
        raise UsageError(
            "over-budget",
            f"this workspace has spent ${total.spent_usd:.2f} of its ${limits.max_usd:.2f} ceiling",
            fix="raise budget.max_usd in ssc.yaml, or use the tool commands, which are free",
        )

    would_be = total.spent_usd + (estimate or 0.0)
    if estimate is not None and would_be > limits.max_usd:
        raise UsageError(
            "over-budget",
            f"this call is about ${estimate:.2f} and would take the total to "
            f"${would_be:.2f}, over the ${limits.max_usd:.2f} ceiling",
            fix="raise budget.max_usd in ssc.yaml, or use the tool commands, which are free",
        )

    if limits.warn_at is not None and would_be >= limits.warn_at:
        return f"${would_be:.2f} of the ${limits.max_usd:.2f} ceiling"
    return None
