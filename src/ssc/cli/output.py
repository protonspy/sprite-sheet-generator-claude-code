"""Everything a command prints is one object.

A command builds a `Result` and returns it; nothing calls `print`. That is what makes
"exactly one JSON object on stdout and nothing else" (R4.1) a property of the code rather
than a discipline reviewers have to keep enforcing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ssc.cli import redact


@dataclass
class Result:
    """The outcome of one command.

    `command` and `data` are the machine-readable part; `summary` is the one line a human
    reads instead. `dry_run` and `cached` are here rather than in `data` because every
    command has them and a harness should not have to know which key each one used.
    """

    command: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    cached: bool = False
    #: Almost always `0`. `specs/gates-and-resume/` is why it exists: exit `3` means a human
    #: decision is outstanding, which is an *outcome* rather than a failure — the gate was
    #: opened, the steps before it ran, and all of that is worth reporting. Carrying it as an
    #: exception instead would have made `ok` false and thrown away the run's progress, which
    #: is the one thing a caller resuming needs. See `errors.GatePending`.
    exit_code: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "command": self.command,
            "summary": self.summary,
            "dry_run": self.dry_run,
            "cached": self.cached,
            **self.data,
        }


def render(payload: dict[str, Any], *, as_json: bool) -> str:
    """One object, rendered either way. Prose is a view of the JSON, never a second
    source of truth about what happened.

    Redaction happens here because this is the boundary every command's output crosses —
    the deliberate `SscError` a leaf composes from a provider's response as much as the
    catch-all's `str(exception)`. Guarding only the catch-all would guard the path nobody
    writes on purpose and leave the one they do (R4.6). It runs before the encoder so a
    secret cannot be missed for having been JSON-escaped on the way past.
    """
    payload = redact.scrubbed(payload)
    if as_json:
        return json.dumps(payload, indent=2, sort_keys=True)

    if not payload.get("ok", False):
        error = payload.get("error", {})
        lines = [f"error: {error.get('message', 'unknown error')} [{error.get('code', '?')}]"]
        if error.get("fix"):
            lines.append(f"fix: {error['fix']}")
        return "\n".join(lines)

    lines = [payload["summary"]]
    if payload.get("dry_run"):
        lines[0] = f"[dry run] {lines[0]}"
    if payload.get("cached"):
        lines.append("(reused a cached result)")
    return "\n".join(lines)
