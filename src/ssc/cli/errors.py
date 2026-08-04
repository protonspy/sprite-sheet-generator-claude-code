"""Errors are values, and every one of them carries the exit code it means.

The `fix` field is the point: a refusal that names the command resolving it is the same
shape a `doctor` finding carries and the same shape a `gen` refusal will carry, so a
harness learns it once and never parses prose.
"""

from __future__ import annotations

from typing import Any

# Exit codes are the contract. See specs/workspace-foundation/requirements.md R4.2.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_GATE_PENDING = 3


class SscError(Exception):
    """A command ran and failed. Exit `1`."""

    exit_code = EXIT_ERROR

    def __init__(self, code: str, message: str, fix: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix

    def as_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.fix is not None:
            error["fix"] = self.fix
        return {"ok": False, "error": error}


class UsageError(SscError):
    """The command should not have been called this way. Exit `2`."""

    exit_code = EXIT_USAGE


class GatePending(SscError):
    """A human decision is outstanding, and there is nothing else to report. Exit `3`.

    `specs/gates-and-resume/` was expected to raise this and does not, which is worth
    recording rather than quietly leaving the class unused. A pending gate is not a failure:
    the gate was opened, and under `ssc run` the steps before it ran. Raising discards all of
    that and reports `ok: false`, so the leaf carries exit `3` on `Result.exit_code` instead
    and keeps the record.

    The class stays because the distinction is real — a command that *cannot even produce a
    result* while a decision is outstanding should refuse, and this is what it refuses with.
    Nothing needs that today.
    """

    exit_code = EXIT_GATE_PENDING
