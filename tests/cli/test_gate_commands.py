"""`ssc gate` — specs/gates-and-resume R1.3, R1.4, R2.1..R2.6, R3.1, R3.2, R3.3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ssc.cli import gates
from ssc.cli.app import main


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    assert run("init")[0] == 0
    return tmp_path


def open_one(subject: str = "hero", topic: str = "bgremove") -> tuple[int, dict[str, Any]]:
    return run(
        "gate",
        "open",
        subject,
        "--topic",
        topic,
        "--question",
        "does the key hold at the edges?",
        "--material",
        "review/hero",
    )


# R2.1 — a pending gate is exit 3 and a record.
def test_opening_a_gate_writes_it_pending_and_exits_three(workspace: Path) -> None:
    code, payload = open_one()
    assert code == 3
    assert payload["ok"] is True
    assert payload["state"] == "pending"
    assert payload["id"] == "hero.bgremove"
    assert payload["material"] == "review/hero"
    assert (workspace / "gates" / "hero.bgremove.json").is_file()


def test_the_pending_gate_carries_the_question_it_asks(workspace: Path) -> None:
    _, payload = open_one()
    assert payload["question"] == "does the key hold at the edges?"


# R2.2 — one gate per subject and topic.
def test_opening_the_same_gate_again_reports_the_existing_one(workspace: Path) -> None:
    open_one()
    code, payload = open_one()
    assert code == 3
    assert payload["id"] == "hero.bgremove"
    assert len(list((workspace / "gates").glob("*.json"))) == 1


def test_a_different_topic_is_a_different_gate(workspace: Path) -> None:
    open_one("hero", "bgremove")
    open_one("hero", "pixelart")
    assert sorted(path.name for path in (workspace / "gates").glob("*.json")) == [
        "hero.bgremove.json",
        "hero.pixelart.json",
    ]


def test_reopening_a_decided_gate_reports_the_decision_and_does_not_exit_three(
    workspace: Path,
) -> None:
    open_one()
    run("gate", "approve", "hero.bgremove", "--choice", "01_tol-60")
    code, payload = open_one()
    assert code == 0
    assert payload["state"] == "approved"


# R2.3 — nothing is ever asked in conversation.
def test_opening_a_gate_reads_nothing_from_standard_input(workspace: Path) -> None:
    result = CliRunner().invoke(
        main,
        ["gate", "open", "hero", "--topic", "bgremove", "--question", "?", "--json"],
        input="",
        catch_exceptions=False,
    )
    assert result.exit_code == 3
    assert json.loads(result.output)["state"] == "pending"


# R2.4 — approving.
def test_approving_records_the_decision_and_the_choice(workspace: Path) -> None:
    open_one()
    code, payload = run("gate", "approve", "hero.bgremove", "--choice", "01_tol-60")
    assert code == 0
    assert payload["state"] == "approved"
    assert payload["choice"] == "01_tol-60"
    assert [entry["state"] for entry in payload["history"]] == ["pending", "approved"]


def test_approving_without_a_choice_is_still_a_decision(workspace: Path) -> None:
    open_one()
    code, payload = run("gate", "approve", "hero.bgremove")
    assert code == 0
    assert payload["state"] == "approved"
    assert payload["choice"] is None


# R2.5 — rejecting.
def test_rejecting_records_the_reason(workspace: Path) -> None:
    open_one()
    code, payload = run("gate", "reject", "hero.bgremove", "--why", "every variant halos")
    assert code == 0
    assert payload["state"] == "rejected"
    assert payload["why"] == "every variant halos"


# R1.3 — one decision per gate.
def test_a_decided_gate_cannot_be_decided_again(workspace: Path) -> None:
    open_one()
    run("gate", "approve", "hero.bgremove", "--choice", "01")
    code, payload = run("gate", "reject", "hero.bgremove", "--why", "changed my mind")
    assert code == 2
    assert payload["error"]["code"] == "gate-decided"
    assert "approved" in payload["error"]["message"]


def test_deciding_a_gate_that_does_not_exist_is_refused(workspace: Path) -> None:
    code, payload = run("gate", "approve", "nobody.nothing")
    assert code == 2
    assert payload["error"]["code"] == "no-gate"


# R2.6 — listing.
def test_listing_reports_every_gate_and_exits_zero(workspace: Path) -> None:
    open_one("hero", "bgremove")
    open_one("boss", "pixelart")
    run("gate", "approve", "hero.bgremove", "--choice", "01")

    code, payload = run("gate", "list")
    assert code == 0
    assert payload["count"] == 2
    assert payload["pending"] == 1
    assert [one["id"] for one in payload["gates"]] == ["boss.pixelart", "hero.bgremove"]


def test_listing_an_empty_workspace_exits_zero(workspace: Path) -> None:
    code, payload = run("gate", "list")
    assert code == 0
    assert payload["count"] == 0


# R1.4 — a broken record does not break the listing.
def test_listing_reports_an_unreadable_record_and_lists_the_rest(workspace: Path) -> None:
    open_one()
    (workspace / "gates" / "wrecked.json").write_text("{not json", encoding="utf-8")
    code, payload = run("gate", "list")
    assert code == 0
    assert payload["count"] == 1
    assert payload["unreadable"] == ["wrecked.json"]


# R3.1, R3.2, R3.3 — the inheritable default.
def test_approving_as_a_default_adopts_it_for_the_topic(workspace: Path) -> None:
    open_one("hero", "bgremove")
    code, payload = run("gate", "approve", "hero.bgremove", "--choice", "01_tol-60", "--default")
    assert code == 0
    assert payload["adopted"]["choice"] == "01_tol-60"
    assert payload["adopted"]["from"] == "hero.bgremove"
    assert (workspace / "gates" / "defaults.json").is_file()


def test_a_gate_on_an_adopted_topic_opens_approved_without_exiting_three(
    workspace: Path,
) -> None:
    open_one("hero", "bgremove")
    run("gate", "approve", "hero.bgremove", "--choice", "01_tol-60", "--default")

    code, payload = open_one("boss", "bgremove")
    assert code == 0
    assert payload["state"] == "approved"
    assert payload["choice"] == "01_tol-60"
    assert payload["inherited_from"] == "hero.bgremove"


def test_an_approval_that_is_not_a_default_is_not_inherited(workspace: Path) -> None:
    open_one("hero", "bgremove")
    run("gate", "approve", "hero.bgremove", "--choice", "01_tol-60")

    code, payload = open_one("boss", "bgremove")
    assert code == 3
    assert payload["state"] == "pending"


def test_a_default_does_not_reach_another_topic(workspace: Path) -> None:
    open_one("hero", "bgremove")
    run("gate", "approve", "hero.bgremove", "--choice", "01", "--default")

    code, payload = open_one("hero", "pixelart")
    assert code == 3
    assert payload["state"] == "pending"


def test_listing_reports_the_adopted_defaults(workspace: Path) -> None:
    open_one("hero", "bgremove")
    run("gate", "approve", "hero.bgremove", "--choice", "01", "--default")
    _, payload = run("gate", "list")
    assert payload["defaults"]["bgremove"]["choice"] == "01"


# --dry-run writes nothing, like every other command.
def test_a_dry_run_open_writes_no_record(workspace: Path) -> None:
    code, payload = run(
        "gate", "open", "hero", "--topic", "bgremove", "--question", "?", "--dry-run"
    )
    assert code == 3
    assert payload["dry_run"] is True
    assert not (workspace / "gates" / "hero.bgremove.json").exists()


def test_a_dry_run_approve_leaves_the_gate_pending(workspace: Path) -> None:
    open_one()
    code, payload = run("gate", "approve", "hero.bgremove", "--dry-run")
    assert code == 0
    assert payload["dry_run"] is True
    assert gates.load(gates.Workspace(root=workspace), "hero.bgremove").state == "pending"


# A gate outside a workspace has nowhere to live.
def test_a_gate_outside_a_workspace_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    code, payload = run("gate", "list")
    assert code == 2
    assert payload["error"]["code"] == "no-workspace"
