"""Everything a command prints is one object.

A command builds a `Result` and returns it; nothing calls `print`. That is what makes
"exactly one JSON object on stdout and nothing else" (R4.1) a property of the code rather
than a discipline reviewers have to keep enforcing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


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
    source of truth about what happened."""
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
