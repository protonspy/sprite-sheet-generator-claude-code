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
    """A human decision is outstanding. Exit `3`.

    Nothing in this leaf raises it; it exists so the four exit codes are one enumeration
    rather than three plus a promise. `specs/gates-and-resume/` is what raises it.
    """

    exit_code = EXIT_GATE_PENDING
