"""Reading a pipeline, and deciding where a run has got to.

specs/gates-and-resume R4.2, R4.4, R4.5, R4.6, R4.7, R4.8, R4.9.

`plan` is TDD because it is the whole of "resume from disk": it decides, from recorded
stages and gate records alone, what has already happened. Getting it wrong does not crash —
it silently re-runs work, or silently walks past a decision nobody took.
"""

from __future__ import annotations

import pytest

from ssc.cli import gates, steps
from ssc.cli.errors import SscError, UsageError


def pipeline(*items: dict[str, object]) -> list[steps.Step]:
    return steps.declared({"pipeline": list(items)})


def a_gate(topic: str, state: str, why: str | None = None) -> gates.Gate:
    gate = gates.Gate.new(
        subject="hero", topic=topic, question="?", material=None, at="2026-08-04T12:00:00Z"
    )
    if state == gates.PENDING:
        return gate
    return gate.decided_as(state, at="2026-08-04T13:00:00Z", why=why, choice="01")


# R4.7, R4.8, R4.9 — reading the declaration.
def test_a_pipeline_reads_into_steps_in_order() -> None:
    read = pipeline(
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
        {"stage": "pixels", "command": "pixelart", "params": {"colors": 16}},
    )
    assert [step.stage for step in read] == ["nobg", "pixels"]
    assert read[0].params == {"tol": 60}
    assert read[0].gated is False


def test_a_step_can_declare_a_gate() -> None:
    (step,) = pipeline({"stage": "nobg", "command": "bgremove", "gate": "does the key hold?"})
    assert step.gated
    assert step.gate == "does the key hold?"


def test_yaml_scalars_are_parsed_by_the_registry() -> None:
    (step,) = pipeline(
        {"stage": "nobg", "command": "bgremove", "params": {"tol": 60, "edge_pass": True}}
    )
    assert step.params == {"tol": 60, "edge_pass": True}


def test_no_pipeline_is_refused_naming_where_one_is_declared() -> None:
    with pytest.raises(UsageError) as refused:
        steps.declared({})
    assert refused.value.code == "no-pipeline"
    assert "ssc.yaml" in (refused.value.fix or "")


def test_a_step_whose_command_cannot_be_run_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        pipeline({"stage": "nobg", "command": "bgremoove"})
    assert refused.value.code == "unknown-command"


def test_a_step_that_would_bill_is_refused_by_name() -> None:
    with pytest.raises(UsageError) as refused:
        pipeline({"stage": "art", "command": "gen image"})
    assert refused.value.code == "paid-step"
    assert "gen image" in (refused.value.fix or "")


def test_a_later_step_being_invalid_refuses_the_whole_pipeline() -> None:
    with pytest.raises(UsageError) as refused:
        pipeline(
            {"stage": "nobg", "command": "bgremove", "params": {"tol": 60}},
            {"stage": "pixels", "command": "pixelart", "params": {"colours": 16}},
        )
    assert refused.value.code == "unknown-parameter"


def test_a_step_with_a_value_out_of_bounds_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        pipeline({"stage": "nobg", "command": "bgremove", "params": {"tol": 99999}})
    assert refused.value.code == "invalid-value"


def test_two_steps_writing_one_stage_are_refused() -> None:
    with pytest.raises(SscError) as refused:
        pipeline(
            {"stage": "nobg", "command": "bgremove"},
            {"stage": "nobg", "command": "pixelart"},
        )
    assert refused.value.code == "invalid-pipeline"


@pytest.mark.parametrize("broken", [{"pipeline": "nobg"}, {"pipeline": []}, {"pipeline": [7]}])
def test_a_pipeline_of_the_wrong_shape_is_refused(broken: dict[str, object]) -> None:
    with pytest.raises(SscError) as refused:
        steps.declared(broken)
    assert refused.value.code == "invalid-pipeline"


def test_a_stage_that_is_not_a_name_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        pipeline({"stage": "../escape", "command": "bgremove"})
    assert refused.value.code == "invalid-name"


# R4.2 — a step whose stage the asset already records is done.
def test_a_step_whose_stage_is_recorded_is_done() -> None:
    read = pipeline(
        {"stage": "nobg", "command": "bgremove"},
        {"stage": "pixels", "command": "pixelart"},
    )
    planned = steps.plan(read, recorded={"nobg"}, gate_for=lambda _: None)
    assert [one.state for one in planned] == ["done", "outstanding"]


def test_nothing_recorded_means_every_step_is_outstanding() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove"})
    assert [one.state for one in steps.plan(read, recorded=set(), gate_for=lambda _: None)] == [
        "outstanding"
    ]


def test_the_next_step_is_the_first_that_is_not_done() -> None:
    read = pipeline(
        {"stage": "nobg", "command": "bgremove"},
        {"stage": "pixels", "command": "pixelart"},
    )
    planned = steps.plan(read, recorded={"nobg"}, gate_for=lambda _: None)
    assert steps.next_of(planned) is not None
    assert steps.next_of(planned).step.stage == "pixels"


def test_a_finished_pipeline_has_no_next_step() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove"})
    planned = steps.plan(read, recorded={"nobg"}, gate_for=lambda _: None)
    assert steps.next_of(planned) is None


# A gated step that has produced its output but whose gate was never opened.
def test_a_gated_step_that_ran_but_has_no_gate_yet_is_outstanding() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove", "gate": "ok?"})
    planned = steps.plan(read, recorded={"nobg"}, gate_for=lambda _: None)
    assert planned[0].state == "outstanding"
    assert planned[0].needs == "gate"


# R4.4 — an approved gate lets the run continue.
def test_an_approved_gate_makes_a_gated_step_done() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove", "gate": "ok?"})
    planned = steps.plan(
        read, recorded={"nobg"}, gate_for=lambda topic: a_gate(topic, gates.APPROVED)
    )
    assert planned[0].state == "done"


def test_an_approved_gate_lets_the_next_step_be_next() -> None:
    read = pipeline(
        {"stage": "nobg", "command": "bgremove", "gate": "ok?"},
        {"stage": "pixels", "command": "pixelart"},
    )
    planned = steps.plan(
        read,
        recorded={"nobg"},
        gate_for=lambda topic: a_gate(topic, gates.APPROVED) if topic == "nobg" else None,
    )
    assert [one.state for one in planned] == ["done", "outstanding"]


# R4.5 — a rejected gate stops the run.
def test_a_rejected_gate_blocks_its_step_and_says_why() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove", "gate": "ok?"})
    planned = steps.plan(
        read,
        recorded={"nobg"},
        gate_for=lambda topic: a_gate(topic, gates.REJECTED, why="every variant halos"),
    )
    assert planned[0].state == "blocked"
    assert "every variant halos" in (planned[0].why or "")


def test_a_pending_gate_blocks_its_step() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove", "gate": "ok?"})
    planned = steps.plan(
        read, recorded={"nobg"}, gate_for=lambda topic: a_gate(topic, gates.PENDING)
    )
    assert planned[0].state == "blocked"


def test_a_blocked_step_stops_everything_after_it() -> None:
    read = pipeline(
        {"stage": "nobg", "command": "bgremove", "gate": "ok?"},
        {"stage": "pixels", "command": "pixelart"},
    )
    planned = steps.plan(
        read,
        recorded={"nobg"},
        gate_for=lambda topic: a_gate(topic, gates.PENDING) if topic == "nobg" else None,
    )
    assert [one.state for one in planned] == ["blocked", "outstanding"]
    assert steps.blocker_of(planned) is not None
    assert steps.blocker_of(planned).step.stage == "nobg"


def test_a_run_with_nothing_blocking_it_has_no_blocker() -> None:
    read = pipeline({"stage": "nobg", "command": "bgremove"})
    planned = steps.plan(read, recorded=set(), gate_for=lambda _: None)
    assert steps.blocker_of(planned) is None


# R4.6 — what `status` reports.
def test_every_step_is_reported_with_its_state() -> None:
    read = pipeline(
        {"stage": "nobg", "command": "bgremove", "gate": "ok?"},
        {"stage": "pixels", "command": "pixelart"},
    )
    planned = steps.plan(
        read,
        recorded={"nobg"},
        gate_for=lambda topic: a_gate(topic, gates.APPROVED) if topic == "nobg" else None,
    )
    reported = [one.as_dict() for one in planned]
    assert reported[0]["stage"] == "nobg"
    assert reported[0]["state"] == "done"
    assert reported[1]["state"] == "outstanding"
