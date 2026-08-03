"""The job store — specs/job-store R1, R2.

Two of these are the TDD tasks, and both are about money rather than complexity. The record
is written *before* the call it describes: written the other way round the store still holds
everything a job file should, and loses exactly one thing — the id of a request that was
already billed, in the window where the process died. And a terminal state is final, because
a provider answering `running` about a job we already collected would re-open it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ssc.cli import jobs, workspace
from ssc.cli.errors import SscError, UsageError

AT = "2026-08-03T10:00:00Z"
LATER = "2026-08-03T10:05:00Z"


@pytest.fixture
def space(tmp_path: Path) -> workspace.Workspace:
    return workspace.create(tmp_path)


def a_job(**over: Any) -> jobs.Job:
    fields: dict[str, Any] = {
        "id": "j-0001",
        "provider": "fake",
        "application": "fake/model",
        "model": "model",
        "arguments": {"prompt": "a knight"},
        "at": AT,
    }
    fields.update(over)
    return jobs.Job.new(**fields)


# R1.3 — what a record holds, and that it survives a round trip.


def test_a_job_records_everything_a_later_process_needs(space: workspace.Workspace) -> None:
    jobs.save(space, a_job())

    loaded = jobs.load(space, "j-0001")

    assert loaded.provider == "fake"
    assert loaded.application == "fake/model"
    assert loaded.model == "model"
    assert loaded.arguments == {"prompt": "a knight"}
    assert loaded.state == "submitted"
    assert loaded.cost_usd is None
    assert loaded.history == [{"state": "submitted", "at": AT}]


def test_the_request_id_starts_empty_and_is_recorded_when_it_arrives(
    space: workspace.Workspace,
) -> None:
    """The id is what the provider hands back, so a record written before the call cannot
    have one — and the second write is the one that makes recovery possible."""
    job = a_job()
    jobs.save(space, job)
    assert jobs.load(space, "j-0001").request_id is None

    jobs.save(space, job.with_request_id("req-42", at=LATER))

    assert jobs.load(space, "j-0001").request_id == "req-42"


def test_cost_stays_none_rather_than_becoming_zero(space: workspace.Workspace) -> None:
    """`specs/budget-guard/` depends on this: a provider metering by subscription reports no
    per-call cost, and modelling cost as a number would make it lie with a zero."""
    jobs.save(space, a_job())

    assert jobs.load(space, "j-0001").as_dict()["cost_usd"] is None


# R1.1, R1.2 — the order, and the atomicity. The TDD pair.


def test_the_record_is_on_disk_before_the_call_is_made(space: workspace.Workspace) -> None:
    """The whole store, in one assertion. Recording after submitting passes every test about
    what a job file contains and loses the id of something already billed."""
    seen: list[bool] = []

    def submit(job: jobs.Job) -> str:
        # Whatever the provider does, the record is already there to be found by a process
        # that starts after this one dies.
        seen.append(jobs.path_of(space, job.id).exists())
        return "req-42"

    jobs.submit(space, a_job(), submit, at=LATER)

    assert seen == [True]


def test_the_id_the_call_returned_is_recorded_after_it(space: workspace.Workspace) -> None:
    jobs.submit(space, a_job(), lambda job: "req-42", at=LATER)

    assert jobs.load(space, "j-0001").request_id == "req-42"


def test_a_call_that_fails_leaves_the_record_behind(space: workspace.Workspace) -> None:
    """The submission may itself be what dies. The record is the only evidence the call was
    ever attempted, so it stays and the job is marked failed rather than removed."""

    def submit(job: jobs.Job) -> str:
        raise RuntimeError("the network went away")

    with pytest.raises(RuntimeError):
        jobs.submit(space, a_job(), submit, at=LATER)

    failed = jobs.load(space, "j-0001")
    assert failed.state == "failed"
    assert failed.error and "network" in failed.error


def test_a_record_is_written_atomically(space: workspace.Workspace) -> None:
    """Never a moment where the file is half a job: `atomic.replace` is the mechanism, and
    this asserts the store actually goes through it."""
    jobs.save(space, a_job())
    jobs.save(space, a_job(arguments={"prompt": "a longer prompt entirely"}))

    text = jobs.path_of(space, "j-0001").read_text(encoding="utf-8")
    assert json.loads(text)["arguments"] == {"prompt": "a longer prompt entirely"}
    assert not list(jobs.directory(space).glob(".*tmp*"))


# R2.1, R2.2, R2.3 — the states. The other TDD task.


def test_a_job_moves_between_states_and_stamps_each(space: workspace.Workspace) -> None:
    job = a_job().to_state("running", at=LATER)

    assert job.state == "running"
    assert job.history == [
        {"state": "submitted", "at": AT},
        {"state": "running", "at": LATER},
    ]


@pytest.mark.parametrize("terminal", ["done", "failed", "cancelled"])
@pytest.mark.parametrize("attempted", ["submitted", "running", "done", "failed", "cancelled"])
def test_nothing_moves_a_job_out_of_a_terminal_state(
    terminal: str, attempted: str, space: workspace.Workspace
) -> None:
    """A provider that says `running` about a job we recorded as `done` is answering about
    work already collected and paid for. Believing it re-opens the job, and on some providers
    collecting twice costs twice."""
    finished = a_job().to_state(terminal, at=LATER)

    if attempted == terminal:
        assert finished.to_state(attempted, at=LATER).state == terminal
        return
    with pytest.raises(SscError) as refused:
        finished.to_state(attempted, at=LATER)
    assert refused.value.code == "job-finished"


def test_a_state_that_is_not_one_of_the_five_is_refused() -> None:
    with pytest.raises(SscError) as refused:
        a_job().to_state("nearly-done", at=LATER)
    assert refused.value.code == "invalid-state"


def test_the_five_states_are_the_five() -> None:
    assert set(jobs.STATES) == {"submitted", "running", "done", "failed", "cancelled"}
    assert set(jobs.TERMINAL) == {"done", "failed", "cancelled"}


# R1.4 — a broken file is a finding, not the end of the scan.


def test_a_file_that_is_not_a_job_is_reported_and_the_others_still_list(
    space: workspace.Workspace,
) -> None:
    """`list` is how somebody diagnoses a broken `jobs/`, so refusing to list because one
    file is corrupt makes the diagnostic unavailable exactly when it is needed."""
    jobs.save(space, a_job())
    jobs.save(space, a_job(id="j-0002"))
    (jobs.directory(space) / "j-0003.json").write_text("{not json", encoding="utf-8")

    found, unreadable = jobs.every(space)

    assert [job.id for job in found] == ["j-0001", "j-0002"]
    assert unreadable == ["j-0003.json"]


def test_jobs_are_listed_most_recently_submitted_first(space: workspace.Workspace) -> None:
    jobs.save(space, a_job(id="j-0001", at="2026-08-01T00:00:00Z"))
    jobs.save(space, a_job(id="j-0002", at="2026-08-03T00:00:00Z"))
    jobs.save(space, a_job(id="j-0003", at="2026-08-02T00:00:00Z"))

    found, _ = jobs.every(space, newest_first=True)

    assert [job.id for job in found] == ["j-0002", "j-0003", "j-0001"]


def test_an_id_that_names_no_job_is_a_usage_error(space: workspace.Workspace) -> None:
    with pytest.raises(UsageError) as refused:
        jobs.load(space, "j-nothing")
    assert refused.value.code == "no-job"
    assert refused.value.exit_code == 2


def test_an_id_cannot_escape_the_jobs_directory(space: workspace.Workspace) -> None:
    """A job id reaches a path, so it is a name and gets a name's validation."""
    with pytest.raises(SscError):
        jobs.load(space, "../../etc/passwd")


# R3.7 — the registry that starts empty.


def test_no_provider_ships_with_the_store() -> None:
    """`specs/gen-fal/` registers the first one. The job is the contract; generation is one
    producer of it, and building them the other way round makes the store fal's."""
    assert jobs.provider_for("fal") is None


def test_a_registered_provider_is_found_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    class Fake:
        def status(self, application: str, request_id: str) -> str:
            return "done"

        def result(self, application: str, request_id: str) -> dict[str, Any]:
            return {}

        def cancel(self, application: str, request_id: str) -> None:
            return None

    monkeypatch.setitem(jobs.PROVIDERS, "fake", Fake())

    assert jobs.provider_for("fake") is not None


# What the reviews found, each pinned so it cannot come back.


def test_a_history_of_the_wrong_shape_is_refused_rather_than_half_read(
    space: workspace.Workspace,
) -> None:
    """`list(...)` of a string is a list of characters, which passed validation and then
    failed far away inside the sort — turning one hand-edited file into "no job lists"."""
    (jobs.directory(space) / "j-bad.json").write_text(
        json.dumps({**a_job().as_dict(), "history": "running"}), encoding="utf-8"
    )

    found, unreadable = jobs.every(space, newest_first=True)

    assert found == []
    assert unreadable == ["j-bad.json"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("arguments", ["not", "an", "object"]),
        ("cost_usd", "free"),
        ("request_id", {"id": 1}),
        ("error", 7),
        ("history", [{"state": "submitted"}]),
        ("history", 0),
        ("arguments", []),
        ("arguments", ""),
    ],
)
def test_a_field_of_the_wrong_type_keeps_the_bad_record_local_to_itself(
    field: str, value: Any, space: workspace.Workspace
) -> None:
    jobs.save(space, a_job())
    (jobs.directory(space) / "j-bad.json").write_text(
        json.dumps({**a_job(id="j-bad").as_dict(), field: value}), encoding="utf-8"
    )

    found, unreadable = jobs.every(space)

    assert [job.id for job in found] == ["j-0001"]
    assert unreadable == ["j-bad.json"]


def test_json_too_deep_to_parse_is_a_finding_not_the_end_of_the_scan(
    space: workspace.Workspace,
) -> None:
    """`RecursionError` is not a `ValueError`, so it escaped the handler and one hostile file
    broke the listing for every job — the diagnostic somebody needs precisely then."""
    jobs.save(space, a_job())
    (jobs.directory(space) / "j-deep.json").write_text("[" * 5000 + "]" * 5000, encoding="utf-8")

    found, unreadable = jobs.every(space)

    assert [job.id for job in found] == ["j-0001"]
    assert unreadable == ["j-deep.json"]


def test_a_credential_shaped_argument_is_not_written_to_disk(
    space: workspace.Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`jobs/` is git-ignored, which stops `git add .` and nothing else — a workspace still
    gets zipped, bundled and shared."""
    jobs.save(space, a_job(arguments={"prompt": "a knight", "api_key": "sk-live-9999"}))

    text = jobs.path_of(space, "j-0001").read_text(encoding="utf-8")

    assert "sk-live-9999" not in text
    # And what makes the job readable afterwards is not credential-shaped, so it stays.
    assert "a knight" in text
