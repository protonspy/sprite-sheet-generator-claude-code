"""`ssc job list|status|wait|cancel|resume` — specs/job-store R3.

Every test here runs against a fake provider, which is the point of the interface rather than
a limitation of the tests: `adr:0006` found that the recorded `(application, request_id)` pair
is the entire state, so a provider is three functions and a fake is a dozen lines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ssc.cli import jobs
from ssc.cli.app import main

AT = "2026-08-03T10:00:00Z"


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


class Fake:
    """A provider that answers from a script, and remembers what it was asked."""

    def __init__(self, states: list[str], result: dict[str, Any] | None = None) -> None:
        self.states = states
        self.answer = result or {"images": ["out.png"]}
        self.asked: list[tuple[str, str]] = []
        self.cancelled: list[tuple[str, str]] = []

    def status(self, application: str, request_id: str) -> str:
        self.asked.append((application, request_id))
        return self.states[min(len(self.asked), len(self.states)) - 1]

    def result(self, application: str, request_id: str) -> dict[str, Any]:
        return self.answer

    def cancel(self, application: str, request_id: str) -> None:
        self.cancelled.append((application, request_id))


@pytest.fixture
def space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    return tmp_path


def record(space: Path, job_id: str = "j-0001", *, state: str = "submitted", at: str = AT) -> None:
    from ssc.cli import workspace as ws

    job = jobs.Job.new(
        id=job_id,
        provider="fake",
        application="fake/model",
        model="model",
        arguments={"prompt": "a knight"},
        at=at,
    ).with_request_id("req-42", at=at)
    if state != "submitted":
        job = job.to_state(state, at=at)
    jobs.save(ws.Workspace(root=space), job)


# R3.1 — list.


def test_init_makes_the_jobs_directory(space: Path) -> None:
    assert (space / "jobs").is_dir()


def test_an_empty_workspace_lists_no_jobs(space: Path) -> None:
    code, payload = run("job", "list")

    assert code == 0
    assert payload["count"] == 0
    assert payload["jobs"] == []


def test_jobs_list_newest_first(space: Path) -> None:
    record(space, "j-0001", at="2026-08-01T00:00:00Z")
    record(space, "j-0002", at="2026-08-03T00:00:00Z")
    record(space, "j-0003", at="2026-08-02T00:00:00Z")

    _, payload = run("job", "list")

    assert [entry["id"] for entry in payload["jobs"]] == ["j-0002", "j-0003", "j-0001"]


def test_a_broken_job_file_is_named_and_the_rest_still_list(space: Path) -> None:
    record(space, "j-0001")
    (space / "jobs" / "j-broken.json").write_text("{not json", encoding="utf-8")

    code, payload = run("job", "list")

    assert code == 0
    assert payload["count"] == 1
    assert payload["unreadable"] == ["j-broken.json"]


# R3.2, R3.6 — status.


def test_status_asks_the_provider_and_records_what_it_says(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(space, "j-0001")
    provider = Fake(["running"])
    monkeypatch.setitem(jobs.PROVIDERS, "fake", provider)

    code, payload = run("job", "status", "j-0001")

    assert code == 0
    assert payload["state"] == "running"
    assert provider.asked == [("fake/model", "req-42")]
    # Recorded, not just reported: the next process reads it off disk.
    assert json.loads((space / "jobs" / "j-0001.json").read_text())["state"] == "running"


def test_a_finished_job_is_not_asked_about_again(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider answering `running` about a job we recorded as `done` would re-open work
    already collected and paid for, so the question is not asked."""
    record(space, "j-0001", state="done")
    provider = Fake(["running"])
    monkeypatch.setitem(jobs.PROVIDERS, "fake", provider)

    _, payload = run("job", "status", "j-0001")

    assert payload["state"] == "done"
    assert provider.asked == []


def test_an_id_that_names_no_job_exits_two(space: Path) -> None:
    code, payload = run("job", "status", "j-nothing")

    assert code == 2
    assert payload["error"]["code"] == "no-job"


# R3.7 — no provider is not a failure.


def test_without_a_provider_the_record_is_still_reported(space: Path) -> None:
    """ "This build has no fal support" is a different problem from "your job failed", and the
    record is the useful part either way."""
    record(space, "j-0001")

    code, payload = run("job", "status", "j-0001")

    assert code == 0
    assert payload["asked_provider"] is False
    assert "fake" in payload["why"]
    assert payload["state"] == "submitted"
    assert payload["request_id"] == "req-42"


# R3.3 — wait.


def test_wait_returns_as_soon_as_the_job_finishes(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(space, "j-0001")
    monkeypatch.setitem(jobs.PROVIDERS, "fake", Fake(["running", "done"]))

    code, payload = run("job", "wait", "--poll", "0.01", "j-0001")

    assert code == 0
    assert payload["state"] == "done"
    assert payload["timed_out"] is False


def test_wait_says_when_it_gave_up_rather_than_looking_finished(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A caller that cannot tell "finished" from "gave up" has to guess whether the money
    bought anything."""
    record(space, "j-0001")
    monkeypatch.setitem(jobs.PROVIDERS, "fake", Fake(["running"]))

    code, payload = run("job", "wait", "--timeout", "0.05", "--poll", "0.01", "j-0001")

    assert code == 0
    assert payload["timed_out"] is True
    assert payload["state"] == "running"


def test_waiting_on_a_finished_job_returns_at_once(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(space, "j-0001", state="done")
    provider = Fake(["running"])
    monkeypatch.setitem(jobs.PROVIDERS, "fake", provider)

    _, payload = run("job", "wait", "j-0001")

    assert payload["timed_out"] is False
    assert provider.asked == []


@pytest.mark.parametrize("argv", [["--timeout", "0"], ["--poll", "-1"]])
def test_a_duration_that_is_not_positive_is_refused(argv: list[str], space: Path) -> None:
    record(space, "j-0001")

    code, payload = run("job", "wait", *argv, "j-0001")

    assert code == 1
    assert payload["error"]["code"] == "invalid-wait"


# R3.4 — cancel.


def test_cancel_asks_the_provider_and_records_it(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(space, "j-0001")
    provider = Fake(["running"])
    monkeypatch.setitem(jobs.PROVIDERS, "fake", provider)

    code, payload = run("job", "cancel", "j-0001")

    assert code == 0
    assert payload["cancelled"] is True
    assert provider.cancelled == [("fake/model", "req-42")]
    assert json.loads((space / "jobs" / "j-0001.json").read_text())["state"] == "cancelled"


def test_cancelling_a_finished_job_asks_nothing(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(space, "j-0001", state="done")
    provider = Fake(["done"])
    monkeypatch.setitem(jobs.PROVIDERS, "fake", provider)

    _, payload = run("job", "cancel", "j-0001")

    assert payload["cancelled"] is False
    assert provider.cancelled == []


def test_a_dry_run_cancel_asks_nothing(space: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record(space, "j-0001")
    provider = Fake(["running"])
    monkeypatch.setitem(jobs.PROVIDERS, "fake", provider)

    _, payload = run("job", "cancel", "--dry-run", "j-0001")

    assert payload["cancelled"] is False
    assert provider.cancelled == []
    assert json.loads((space / "jobs" / "j-0001.json").read_text())["state"] == "submitted"


# R3.5 — resume, which is why the rest exists.


def test_resume_collects_from_the_record_alone(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No process that submitted anything is involved: the id came off disk."""
    record(space, "j-0001")
    monkeypatch.setitem(jobs.PROVIDERS, "fake", Fake(["done"], {"images": ["hero.png"]}))

    code, payload = run("job", "resume", "j-0001")

    assert code == 0
    assert payload["collected"] is True
    assert payload["result"] == {"images": ["hero.png"]}


def test_resume_on_an_unfinished_job_collects_nothing(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record(space, "j-0001")
    monkeypatch.setitem(jobs.PROVIDERS, "fake", Fake(["running"]))

    _, payload = run("job", "resume", "j-0001")

    assert payload["collected"] is False
    assert payload["state"] == "running"


def test_resume_without_a_provider_reports_the_record(space: Path) -> None:
    record(space, "j-0001", state="done")

    code, payload = run("job", "resume", "j-0001")

    assert code == 0
    assert payload["asked_provider"] is False


@pytest.mark.parametrize(
    "argv", [["--timeout", "nan"], ["--poll", "nan"], ["--timeout", "inf"], ["--poll", "inf"]]
)
def test_a_duration_that_is_not_a_number_is_refused_rather_than_looping_forever(
    argv: list[str], space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every comparison against `nan` is False, so `--timeout nan` walked through a `<= 0`
    guard, made the deadline `nan`, and left the loop running forever — a command that never
    returns, which is what `wait` exists to avoid looking like."""
    record(space, "j-0001")
    monkeypatch.setitem(jobs.PROVIDERS, "fake", Fake(["running"]))

    code, payload = run("job", "wait", *argv, "j-0001")

    assert code == 1
    assert payload["error"]["code"] == "invalid-wait"


def test_a_credential_shaped_argument_never_reaches_the_output(
    space: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssc.cli import workspace as ws

    jobs.save(
        ws.Workspace(root=space),
        jobs.Job.new(
            id="j-0002",
            provider="fake",
            application="fake/model",
            model="model",
            arguments={"prompt": "a knight", "api_key": "sk-live-9999"},
            at=AT,
        ),
    )

    result = CliRunner().invoke(main, ["job", "list", "--json"], catch_exceptions=False)

    assert "sk-live-9999" not in result.stdout
    assert "a knight" in result.stdout
