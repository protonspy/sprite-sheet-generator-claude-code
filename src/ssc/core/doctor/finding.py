"""What a check returns.

Every defect is a number and a named fix, never a judgement. That is what closes the loop
for an agent: it does not decide whether something "looks right", it reads a measurement
and runs the command in `fix`. The field is the same one `SscError` carries, so a harness
that knows what to do with a refusal already knows what to do with a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Check(StrEnum):
    """The seven `doctor` ships with. `seam` and `nineslice` arrive with the tile and UI
    kinds, as deltas against this spec rather than as a second detector."""

    PIXEL_GRID = "pixel_grid"
    BLEED = "bleed"
    DRIFT = "drift"
    HALO = "halo"
    PALETTE = "palette"
    FLICKER = "flicker"
    SILHOUETTE = "silhouette"


class Status(StrEnum):
    OK = "ok"
    WARNING = "warning"
    DEFECT = "defect"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class Finding:
    """One check's answer, clean or not.

    A check that found nothing still returns a finding: a report that omits what it did
    not find is indistinguishable from one where the check never ran.
    """

    check: Check
    status: Status
    measurement: dict[str, Any] = field(default_factory=dict)
    fix: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status is Status.SKIPPED and not self.reason:
            raise ValueError(f"{self.check} was skipped without saying why")
        if self.status in {Status.DEFECT, Status.WARNING} and not self.fix:
            raise ValueError(f"{self.check} reported {self.status} with no fix to name")

    @property
    def clean(self) -> bool:
        return self.status is Status.OK

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"check": str(self.check), "status": str(self.status)}
        if self.status is Status.SKIPPED:
            payload["reason"] = self.reason
            return payload
        payload["measurement"] = self.measurement
        if self.fix is not None:
            payload["fix"] = self.fix
        return payload


def skipped(check: Check, reason: str) -> Finding:
    return Finding(check=check, status=Status.SKIPPED, reason=reason)


def ok(check: Check, **measurement: Any) -> Finding:
    return Finding(check=check, status=Status.OK, measurement=measurement)


def defect(check: Check, fix: str, **measurement: Any) -> Finding:
    return Finding(check=check, status=Status.DEFECT, measurement=measurement, fix=fix)


def warning(check: Check, fix: str, **measurement: Any) -> Finding:
    return Finding(check=check, status=Status.WARNING, measurement=measurement, fix=fix)


@dataclass(frozen=True)
class Report:
    """Every check's finding, in a stable order."""

    findings: list[Finding]

    @property
    def defects(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.status is Status.DEFECT]

    def as_dict(self) -> dict[str, Any]:
        return {
            "checks": [finding.as_dict() for finding in self.findings],
            "defects": len(self.defects),
            "warnings": sum(1 for f in self.findings if f.status is Status.WARNING),
            "skipped": sum(1 for f in self.findings if f.status is Status.SKIPPED),
        }
