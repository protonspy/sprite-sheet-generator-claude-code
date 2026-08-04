"""The gate record — specs/gates-and-resume R1.1, R1.2, R1.3, R1.4, R3.1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ssc.cli import gates
from ssc.cli.errors import SscError, UsageError
from ssc.cli.workspace import Workspace


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "gates").mkdir()
    return Workspace(root=tmp_path)


def opened(subject: str = "hero", topic: str = "bgremove") -> gates.Gate:
    return gates.Gate.new(
        subject=subject,
        topic=topic,
        question="does the key hold at the edges?",
        material="review/hero",
        at="2026-08-04T12:00:00Z",
    )


# R1.1 — what a gate names.
def test_a_new_gate_is_pending_and_names_what_it_is_about() -> None:
    gate = opened()
    assert gate.id == "hero.bgremove"
    assert gate.subject == "hero"
    assert gate.topic == "bgremove"
    assert gate.material == "review/hero"
    assert gate.state == gates.PENDING
    assert gate.pending


# R1.2 — every move is stamped.
def test_opening_stamps_the_history() -> None:
    assert opened().history == [{"state": "pending", "at": "2026-08-04T12:00:00Z"}]


def test_a_decision_appends_to_the_history() -> None:
    decided = opened().decided_as(gates.APPROVED, at="2026-08-04T13:00:00Z", choice="01_tol-60")
    assert decided.state == gates.APPROVED
    assert decided.choice == "01_tol-60"
    assert [entry["state"] for entry in decided.history] == ["pending", "approved"]


def test_a_rejection_keeps_the_reason() -> None:
    decided = opened().decided_as(gates.REJECTED, at="2026-08-04T13:00:00Z", why="all of them halo")
    assert decided.state == gates.REJECTED
    assert decided.why == "all of them halo"


# R1.3 — a decision is taken once.
def test_a_decided_gate_cannot_be_decided_again() -> None:
    decided = opened().decided_as(gates.APPROVED, at="2026-08-04T13:00:00Z", choice="01")
    with pytest.raises(UsageError) as refused:
        decided.decided_as(gates.REJECTED, at="2026-08-04T14:00:00Z", why="changed my mind")
    assert refused.value.code == "gate-decided"
    assert "approved" in refused.value.message


def test_a_state_that_is_not_a_decision_is_refused() -> None:
    with pytest.raises(SscError) as refused:
        opened().decided_as("pending", at="2026-08-04T13:00:00Z")
    assert refused.value.code == "invalid-state"


# Round trip.
def test_a_gate_survives_being_written_and_read_back(workspace: Workspace) -> None:
    gate = opened()
    gates.save(workspace, gate)
    assert gates.load(workspace, gate.id) == gate


def test_a_gate_that_is_not_there_is_a_usage_error(workspace: Workspace) -> None:
    with pytest.raises(UsageError) as refused:
        gates.load(workspace, "nobody.nothing")
    assert refused.value.code == "no-gate"


def test_find_returns_nothing_where_no_gate_was_opened(workspace: Workspace) -> None:
    assert gates.find(workspace, "hero", "bgremove") is None


def test_find_returns_the_gate_for_that_subject_and_topic(workspace: Workspace) -> None:
    gates.save(workspace, opened())
    found = gates.find(workspace, "hero", "bgremove")
    assert found is not None and found.id == "hero.bgremove"


@pytest.mark.parametrize(
    "broken",
    [
        {
            "schema": 99,
            "id": "a.b",
            "subject": "a",
            "topic": "b",
            "question": "?",
            "state": "pending",
        },
        {"schema": 1, "id": "a.b", "subject": "a", "topic": "b", "state": "pending"},
        {"schema": 1, "id": "a.b", "subject": "a", "topic": "b", "question": "?", "state": "maybe"},
        {
            "schema": 1,
            "id": "a.b",
            "subject": "a",
            "topic": "b",
            "question": "?",
            "state": "pending",
            "history": 0,
        },
        {
            "schema": 1,
            "id": "a.b",
            "subject": "a",
            "topic": "b",
            "question": "?",
            "state": "pending",
            "history": [{"state": "pending"}],
        },
        {
            "schema": 1,
            "id": "a.b",
            "subject": "a",
            "topic": "b",
            "question": "?",
            "state": "pending",
            "choice": 7,
        },
    ],
)
def test_a_malformed_record_is_refused_on_the_way_in(broken: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        gates.Gate.from_dict(broken)


def test_a_falsy_history_is_not_quietly_defaulted() -> None:
    """`data.get(x) or default` swaps a falsy value for the default before it can be
    refused. `history: 0` has to be a finding, not an empty history."""
    with pytest.raises(ValueError):
        gates.Gate.from_dict(
            {
                "schema": 1,
                "id": "a.b",
                "subject": "a",
                "topic": "b",
                "question": "?",
                "state": "pending",
                "history": 0,
            }
        )


# R1.4 — listing survives a broken file.
def test_listing_reports_what_it_could_not_read_and_lists_the_rest(workspace: Workspace) -> None:
    gates.save(workspace, opened("hero", "bgremove"))
    gates.save(workspace, opened("boss", "pixelart"))
    (gates.directory(workspace) / "wrecked.json").write_text("{not json", encoding="utf-8")

    found, unreadable = gates.every(workspace)
    assert sorted(gate.id for gate in found) == ["boss.pixelart", "hero.bgremove"]
    assert unreadable == ["wrecked.json"]


def test_listing_a_workspace_with_no_gates_is_empty(tmp_path: Path) -> None:
    assert gates.every(Workspace(root=tmp_path)) == ([], [])


def test_the_defaults_file_is_not_listed_as_a_gate(workspace: Workspace) -> None:
    gates.save(workspace, opened())
    gates.adopt(workspace, opened().decided_as(gates.APPROVED, at="t", choice="01"), at="t")
    found, unreadable = gates.every(workspace)
    assert [gate.id for gate in found] == ["hero.bgremove"]
    assert unreadable == []


# R3.1 — an approval adopted as a default.
def test_adopting_records_the_decision_for_the_topic(workspace: Workspace) -> None:
    decided = opened().decided_as(gates.APPROVED, at="2026-08-04T13:00:00Z", choice="01_tol-60")
    gates.adopt(workspace, decided, at="2026-08-04T13:00:00Z")

    adopted = gates.defaults(workspace)
    assert adopted["bgremove"].choice == "01_tol-60"
    assert adopted["bgremove"].came_from == "hero.bgremove"


def test_defaults_are_empty_where_none_were_adopted(workspace: Workspace) -> None:
    assert gates.defaults(workspace) == {}


def test_adopting_a_second_topic_keeps_the_first(workspace: Workspace) -> None:
    gates.adopt(
        workspace,
        opened("hero", "bgremove").decided_as(gates.APPROVED, at="t", choice="01"),
        at="t",
    )
    gates.adopt(
        workspace,
        opened("hero", "pixelart").decided_as(gates.APPROVED, at="t", choice="02"),
        at="t",
    )
    assert sorted(gates.defaults(workspace)) == ["bgremove", "pixelart"]


def test_adopting_the_same_topic_again_replaces_it(workspace: Workspace) -> None:
    gates.adopt(
        workspace,
        opened("hero", "bgremove").decided_as(gates.APPROVED, at="t", choice="01"),
        at="t",
    )
    gates.adopt(
        workspace,
        opened("boss", "bgremove").decided_as(gates.APPROVED, at="t", choice="02"),
        at="t",
    )
    assert gates.defaults(workspace)["bgremove"].choice == "02"
    assert gates.defaults(workspace)["bgremove"].came_from == "boss.bgremove"


def test_a_broken_defaults_file_is_a_finding_rather_than_an_empty_map(
    workspace: Workspace,
) -> None:
    gates.defaults_path(workspace).write_text("{not json", encoding="utf-8")
    with pytest.raises(SscError) as refused:
        gates.defaults(workspace)
    assert refused.value.code == "gate-defaults-invalid"


def test_a_defaults_file_of_the_wrong_schema_is_refused(workspace: Workspace) -> None:
    gates.defaults_path(workspace).write_text(json.dumps({"schema": 99}), encoding="utf-8")
    with pytest.raises(SscError) as refused:
        gates.defaults(workspace)
    assert refused.value.code == "gate-defaults-invalid"


# R3.2 — a gate opened against a default.
def test_inheriting_opens_the_gate_approved_and_says_where_from(workspace: Workspace) -> None:
    decided = opened("hero", "bgremove").decided_as(gates.APPROVED, at="t", choice="01_tol-60")
    default = gates.adopt(workspace, decided, at="t")

    fresh = opened("boss", "bgremove").inheriting(default, at="2026-08-04T14:00:00Z")
    assert fresh.state == gates.APPROVED
    assert fresh.choice == "01_tol-60"
    assert fresh.inherited_from == "hero.bgremove"
    assert fresh.history[-1]["inherited"] == "hero.bgremove"


# A gate id becomes a path, so it goes through the same gate a key does.
@pytest.mark.parametrize("subject", ["../escape", "a/b", "", "con"])
def test_a_subject_that_is_not_a_name_is_refused(subject: str) -> None:
    with pytest.raises(UsageError) as refused:
        gates.identifier(subject, "bgremove")
    assert refused.value.code == "invalid-name"


# A gate id is `<subject>.<topic>`, so neither half may hold the separator: `hero.bg` +
# `approved` and `hero` + `bg.approved` would otherwise land on one record, and approving
# either would read as having approved the other.
@pytest.mark.parametrize(
    ("subject", "topic"),
    [("hero.bg", "approved"), ("hero", "bg.approved"), ("a.b", "c.d")],
)
def test_a_dot_in_either_half_of_a_gate_id_is_refused(subject: str, topic: str) -> None:
    with pytest.raises(UsageError) as refused:
        gates.identifier(subject, topic)
    assert refused.value.code == "invalid-name"


def test_two_gates_that_would_have_collided_cannot_both_be_made() -> None:
    assert gates.identifier("hero", "bgremove") == "hero.bgremove"
    with pytest.raises(UsageError):
        gates.identifier("hero.bg", "remove")


# Scrubbed on the way in, like a job record: a workspace gets zipped and sent to somebody.
def test_a_gate_record_is_redacted_before_it_is_written(workspace: Workspace) -> None:
    leaky = gates.Gate.new(
        subject="hero",
        topic="bgremove",
        question="check https://example.com/x?api_key=sk-live-abcdefghijklmnop",
        material=None,
        at="2026-08-04T12:00:00Z",
    )
    gates.save(workspace, leaky)
    on_disk = gates.path_of(workspace, leaky.id).read_text(encoding="utf-8")
    assert "sk-live-abcdefghijklmnop" not in on_disk


def test_the_adopted_defaults_are_redacted_too(workspace: Workspace) -> None:
    """The sibling write. Scrubbing `save` and not `adopt` leaves the same free text on
    disk one file over."""
    decided = opened().decided_as(
        gates.APPROVED,
        at="2026-08-04T13:00:00Z",
        choice="https://example.com/x?api_key=sk-live-abcdefghijklmnop",
    )
    gates.adopt(workspace, decided, at="2026-08-04T13:00:00Z")
    on_disk = gates.defaults_path(workspace).read_text(encoding="utf-8")
    assert "sk-live-abcdefghijklmnop" not in on_disk
