"""R4.2 · R4.5 — an error is a value carrying its exit code and, where one exists, a fix."""

from __future__ import annotations

from ssc.cli.errors import GatePending, SscError, UsageError


def test_an_error_reports_its_own_exit_code() -> None:
    assert SscError("x", "boom").exit_code == 1
    assert UsageError("x", "boom").exit_code == 2
    assert GatePending("x", "boom").exit_code == 3


def test_an_error_serialises_to_a_stable_code_and_message() -> None:
    payload = SscError("no-workspace", "no workspace found").as_dict()
    assert payload == {
        "ok": False,
        "error": {"code": "no-workspace", "message": "no workspace found"},
    }


def test_a_fix_is_carried_when_there_is_one() -> None:
    """The field a harness acts on, and the reason a refusal is useful rather than final."""
    payload = UsageError("no-workspace", "no workspace found", fix="ssc init").as_dict()
    assert payload["error"]["fix"] == "ssc init"


def test_no_fix_key_when_there_is_no_fix() -> None:
    """Absent, not null — a harness testing for the key gets the honest answer."""
    assert "fix" not in SscError("x", "boom").as_dict()["error"]


def test_an_error_is_still_an_exception() -> None:
    assert str(SscError("x", "boom")) == "boom"
