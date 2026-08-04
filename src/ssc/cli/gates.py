"""`gates/` — one file per decision reserved for a human.

Modelled on `cli/jobs.py`, deliberately and almost line for line: one file per record and
never an index, validate-on-read, a stamped history, and a listing that reports what it
could not read rather than failing. The premise is the same one — another process may be
running while this one reads — and where two stores in one codebase answer that differently,
one of them is wrong.

What is different is what the record is *for*. A job is work somebody else is doing and we
are waiting on; a gate is work **we** are waiting on a person for. So there is no provider
to ask, nothing to poll, and the only thing that moves a gate is somebody running
`ssc gate approve` or `ssc gate reject`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ssc.cli.atomic import replace as write_atomically
from ssc.cli.errors import SscError, UsageError
from ssc.cli.names import check_name
from ssc.cli.redact import scrubbed
from ssc.cli.workspace import Workspace

SCHEMA = 1

GATES_DIR = "gates"

#: Beside the gates rather than inside one: a default is a property of the workspace, and
#: the gate that established it may later be deleted.
DEFAULTS_NAME = "defaults.json"

PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"

STATES = (PENDING, APPROVED, REJECTED)

#: Absorbing, for the reason `jobs.TERMINAL` is: a decision that has been taken is evidence,
#: and re-opening it silently would lose what somebody actually decided.
DECIDED = (APPROVED, REJECTED)


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def identifier(subject: str, topic: str) -> str:
    """`<subject>.<topic>` — what makes R2.2 a file-existence question rather than a scan.

    Neither half may hold a dot, and that is not tidiness. `check_name` permits internal
    dots, so `("hero.bg", "approved")` and `("hero", "bg.approved")` both compose to
    `hero.bg.approved` and land on one file — two logically distinct decisions collapsed
    into one record, where approving either reads as having approved the other. The
    separator has to be a character the halves cannot contain.
    """
    for value, what in ((subject, "subject"), (topic, "topic")):
        check_name(value, what)
        if "." in value:
            raise UsageError(
                "invalid-name",
                f"{what} {value!r} holds a dot, which separates a gate's two halves",
                fix="use letters, digits, dash or underscore",
            )
    return f"{subject}.{topic}"


@dataclass(frozen=True)
class Gate:
    """One decision, as it is on disk."""

    id: str
    subject: str
    topic: str
    question: str
    material: str | None = None
    state: str = PENDING
    choice: str | None = None
    why: str | None = None
    inherited_from: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        *,
        subject: str,
        topic: str,
        question: str,
        material: str | None,
        at: str,
    ) -> Gate:
        return cls(
            id=identifier(subject, topic),
            subject=subject,
            topic=topic,
            question=question,
            material=material,
            history=[{"state": PENDING, "at": at}],
        )

    @property
    def pending(self) -> bool:
        return self.state == PENDING

    def decided_as(
        self, state: str, *, at: str, choice: str | None = None, why: str | None = None
    ) -> Gate:
        """This gate decided, with the move stamped (R1.2, R1.3)."""
        if state not in DECIDED:
            raise SscError(
                "invalid-state",
                f"{state!r} is not a decision",
                fix=f"one of {', '.join(DECIDED)}",
            )
        if self.state in DECIDED:
            raise UsageError(
                "gate-decided",
                f"{self.id} was already {self.state}"
                + (f" ({self.why})" if self.why else "")
                + (f", choosing {self.choice}" if self.choice else ""),
                fix="a decision that has been taken is the record; open a new gate instead",
            )
        return replace(
            self,
            state=state,
            choice=choice if choice is not None else self.choice,
            why=why if why is not None else self.why,
            history=[*self.history, {"state": state, "at": at}],
        )

    def inheriting(self, default: Default, *, at: str) -> Gate:
        """This gate, opened already approved against a recorded default (R3.2)."""
        return replace(
            self,
            state=APPROVED,
            choice=default.choice,
            inherited_from=default.came_from,
            history=[*self.history, {"state": APPROVED, "at": at, "inherited": default.came_from}],
        )

    @property
    def opened_at(self) -> str:
        return self.history[0]["at"] if self.history else ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "id": self.id,
            "subject": self.subject,
            "topic": self.topic,
            "question": self.question,
            "material": self.material,
            "state": self.state,
            "choice": self.choice,
            "why": self.why,
            "inherited_from": self.inherited_from,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Gate:
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError(f"not a schema {SCHEMA} gate record")
        missing = [
            key for key in ("id", "subject", "topic", "question", "state") if key not in data
        ]
        if missing:
            raise ValueError(f"a gate record needs {', '.join(missing)}")
        if data["state"] not in STATES:
            raise ValueError(f"{data['state']!r} is not a gate state")

        # Shapes, not just presence — `jobs.from_dict` carries the argument, learned there:
        # a `history` of the wrong shape passed the check and then failed far away inside the
        # listing's sort, turning one hand-edited file into "no gate in this workspace
        # lists". `data.get(x) or default` is the shape that looks right and is not, because
        # it swaps every *falsy* value for the default before the check can see it.
        history = data.get("history")
        history = [] if history is None else history
        if not isinstance(history, list) or not all(
            isinstance(entry, dict) and {"state", "at"} <= set(entry) for entry in history
        ):
            raise ValueError("a gate record's history is a list of {state, at}")
        for name in ("material", "choice", "why", "inherited_from"):
            value = data.get(name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"a gate record's {name} is a string or null")
        for name in ("id", "subject", "topic", "question"):
            if not isinstance(data[name], str):
                raise ValueError(f"a gate record's {name} is a string")

        return cls(
            id=str(data["id"]),
            subject=str(data["subject"]),
            topic=str(data["topic"]),
            question=str(data["question"]),
            material=data.get("material"),
            state=str(data["state"]),
            choice=data.get("choice"),
            why=data.get("why"),
            inherited_from=data.get("inherited_from"),
            history=[dict(entry) for entry in history],
        )


@dataclass(frozen=True)
class Default:
    """A decision a workspace has adopted for a whole topic (R3.1)."""

    topic: str
    choice: str | None
    came_from: str
    at: str

    def as_dict(self) -> dict[str, Any]:
        return {"choice": self.choice, "from": self.came_from, "at": self.at}


def directory(workspace: Workspace) -> Path:
    return workspace.root / GATES_DIR


def path_of(workspace: Workspace, gate_id: str) -> Path:
    # A gate id becomes a path, so it is validated as one — the same gate a key, a kind and a
    # job id go through. It is `<subject>.<topic>` and `check_name` allows the dot.
    check_name(gate_id, "gate id")
    return directory(workspace) / f"{gate_id}.json"


def save(workspace: Workspace, gate: Gate) -> Path:
    """The record on disk, atomically and redacted.

    Scrubbed on the way *in*, the same as `jobs.save`, and for the same reason rather than
    for symmetry: nothing a gate carries is credential-shaped today — a question, a choice,
    a reason, a path — but `question` and `why` are free text an agent composes, and a
    workspace gets zipped for a colleague or dropped into a support bundle. A store that
    scrubs only once somebody notices it needs to is a store that has already written the
    file it should not have.
    """
    return write_atomically(
        path_of(workspace, gate.id),
        (json.dumps(scrubbed(gate.as_dict()), indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def load(workspace: Workspace, gate_id: str) -> Gate:
    path = path_of(workspace, gate_id)
    if not path.is_file():
        raise UsageError(
            "no-gate",
            f"no gate {gate_id} in this workspace",
            fix="ssc gate list",
        )
    try:
        return Gate.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError) as refused:
        raise SscError(
            "gate-invalid",
            f"{path} is not a readable gate record: {refused}",
            fix="remove it, or fix it by hand",
        ) from refused


def find(workspace: Workspace, subject: str, topic: str) -> Gate | None:
    """The gate for this subject and topic, if there is one."""
    path = path_of(workspace, identifier(subject, topic))
    return load(workspace, identifier(subject, topic)) if path.is_file() else None


def every(workspace: Workspace) -> tuple[list[Gate], list[str]]:
    """Every readable gate, and the names of the files that were not (R1.4).

    A broken file is a finding rather than the end of the scan: `list` is how somebody
    diagnoses a broken `gates/`, and refusing to list makes the diagnostic unavailable
    exactly when it is needed.
    """
    where = directory(workspace)
    if not where.is_dir():
        return [], []

    found: list[Gate] = []
    unreadable: list[str] = []
    for path in sorted(where.glob("*.json")):
        if path.name == DEFAULTS_NAME:
            continue
        try:
            found.append(Gate.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError, RecursionError):
            unreadable.append(path.name)
    return found, unreadable


def defaults_path(workspace: Workspace) -> Path:
    return directory(workspace) / DEFAULTS_NAME


def defaults(workspace: Workspace) -> dict[str, Default]:
    """Every topic this workspace has adopted a decision for (R3.1)."""
    path = defaults_path(workspace)
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError) as unreadable:
        raise SscError(
            "gate-defaults-invalid",
            f"{path} could not be read: {unreadable}",
            fix="delete it to drop the inherited decisions, or fix it by hand",
        ) from unreadable

    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise SscError(
            "gate-defaults-invalid",
            f"{path} is not a schema {SCHEMA} defaults record",
            fix="delete it to drop the inherited decisions",
        )

    adopted = document.get("topics")
    adopted = {} if adopted is None else adopted
    if not isinstance(adopted, dict):
        raise SscError(
            "gate-defaults-invalid",
            f"{path} records topics as {type(adopted).__name__}, not a map",
            fix="delete it to drop the inherited decisions",
        )

    read: dict[str, Default] = {}
    for topic, entry in adopted.items():
        if not isinstance(topic, str) or not isinstance(entry, dict):
            raise SscError(
                "gate-defaults-invalid",
                f"{path} records {topic!r} as something other than a decision",
                fix="delete it to drop the inherited decisions",
            )
        choice = entry.get("choice")
        came_from = entry.get("from")
        if (choice is not None and not isinstance(choice, str)) or not isinstance(came_from, str):
            raise SscError(
                "gate-defaults-invalid",
                f"{path} records {topic!r} without a readable decision",
                fix="delete it to drop the inherited decisions",
            )
        read[topic] = Default(
            topic=topic,
            choice=choice,
            came_from=came_from,
            at=str(entry.get("at", "")),
        )
    return read


def adopt(workspace: Workspace, gate: Gate, *, at: str) -> Default:
    """Record this gate's decision as the default for its topic (R3.1).

    Read-modify-write, and unlike `budget.py`'s running total this one is not under a lock.
    The difference is what a lost update costs: there, money is miscounted silently; here,
    two people adopting a default in the same instant means one of two decisions about the
    same topic wins, and the loser's gate still carries its own approval. That is visible in
    `gate list` rather than silent, and a lock file per workspace for a decision taken by
    hand at human speed buys less than it costs.
    """
    adopted = defaults(workspace)
    adopted[gate.topic] = Default(topic=gate.topic, choice=gate.choice, came_from=gate.id, at=at)
    write_atomically(
        defaults_path(workspace),
        (
            json.dumps(
                # Scrubbed, like `save`. This is the sibling write that the first pass at
                # redaction missed: `--choice` is the same unconstrained free text, and
                # persisting it here rather than in the gate record does not make it a
                # different kind of string. A store that scrubs one of its two writers has
                # the hole it thinks it closed.
                scrubbed(
                    {
                        "schema": SCHEMA,
                        "topics": {name: one.as_dict() for name, one in sorted(adopted.items())},
                    }
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
    )
    return adopted[gate.topic]
