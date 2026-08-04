"""The money guard — specs/budget-guard R1, R2, R3.

Two of these are the TDD tasks and both are money rather than complexity: whether a call
happens at all, and arithmetic over a running total. Nothing here reaches a provider — the
ceiling and the total are decided before anything is submitted, which is the point.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from ssc.cli import budget, workspace
from ssc.cli.errors import SscError, UsageError


@pytest.fixture
def space(tmp_path: Path) -> workspace.Workspace:
    space = workspace.create(tmp_path)
    return space


@dataclass
class FakeAsk:
    """Only the three fields `covered_by` reads. A real `Ask` would drag the whole pipeline
    into a test about arithmetic."""

    verb: str
    prompt: str | None = None
    variables: dict[str, str] | None = None

    def __post_init__(self) -> None:
        self.variables = self.variables or {}


# R2.1, R2.5 — what `ssc.yaml` says, and what it means to say nothing.


def test_no_budget_declared_refuses_nothing() -> None:
    """R2.5. A workspace that never mentioned money is not a workspace with a zero ceiling,
    and reading it as one would break every project that has not opted in."""
    limits = budget.limits_of({})
    assert limits.declared is False
    assert budget.check(limits, budget.Total(spent_usd=999.0), 500.0) is None


def test_a_declared_ceiling_of_zero_is_a_statement() -> None:
    """The difference R2.5 turns on: absent is "no opinion", zero is "not a cent"."""
    limits = budget.limits_of({"budget": {"max_usd": 0}})
    assert limits.declared is True
    with pytest.raises(UsageError):
        budget.check(limits, budget.Total(), None)


@pytest.mark.parametrize("value", ["free", True, -1, [5]])
def test_an_amount_that_is_not_one_is_refused(value: Any) -> None:
    """`max_usd: true` is a configuration mistake, not a ceiling of one dollar — `bool` is an
    `int` in Python and this is where that bites."""
    with pytest.raises(SscError) as refused:
        budget.limits_of({"budget": {"max_usd": value}})
    assert refused.value.code == "invalid-config"


def test_a_budget_that_is_not_a_map_is_refused() -> None:
    with pytest.raises(SscError):
        budget.limits_of({"budget": 5})


# R2.2, R2.3, R2.4 — the ceiling. Task 2.2, TDD.


def test_a_total_that_has_reached_the_ceiling_refuses_the_next_call() -> None:
    """R2.2, and this is the refusal that actually works.

    No provider publishes a per-call price, so the estimate is almost always absent. A
    ceiling written only against an estimate would report a number and enforce nothing.
    """
    limits = budget.limits_of({"budget": {"max_usd": 10.0}})
    with pytest.raises(UsageError) as refused:
        budget.check(limits, budget.Total(spent_usd=10.0, calls=4), None)
    assert refused.value.code == "over-budget"
    assert "10.00" in refused.value.message


def test_a_total_under_the_ceiling_proceeds_with_no_estimate() -> None:
    """The common case: something spent, no price published, room left."""
    limits = budget.limits_of({"budget": {"max_usd": 10.0}})
    assert budget.check(limits, budget.Total(spent_usd=4.0), None) is None


def test_an_estimate_that_would_cross_the_ceiling_refuses(  # R2.3
) -> None:
    """The tighter check, for the day a provider publishes a price. Specified now so that
    arriving prices change a number rather than a design."""
    limits = budget.limits_of({"budget": {"max_usd": 10.0}})
    with pytest.raises(UsageError) as refused:
        budget.check(limits, budget.Total(spent_usd=9.5), 1.0)
    assert refused.value.code == "over-budget"
    assert "10.50" in refused.value.message


def test_an_estimate_that_lands_exactly_on_the_ceiling_is_allowed() -> None:
    """The boundary, stated rather than left to whoever reads `>` first. Spending the last
    cent of a declared ceiling is spending what was authorised."""
    limits = budget.limits_of({"budget": {"max_usd": 10.0}})
    assert budget.check(limits, budget.Total(spent_usd=9.0), 1.0) is None


def test_the_warning_threshold_reports_and_proceeds(  # R2.4
) -> None:
    limits = budget.limits_of({"budget": {"max_usd": 10.0, "warn_at": 8.0}})
    warning = budget.check(limits, budget.Total(spent_usd=8.5), None)
    assert warning is not None
    assert "8.50" in warning and "10.00" in warning


def test_under_the_warning_threshold_says_nothing() -> None:
    limits = budget.limits_of({"budget": {"max_usd": 10.0, "warn_at": 8.0}})
    assert budget.check(limits, budget.Total(spent_usd=2.0), None) is None


# R3.2, R3.3 — the total. Task 3.1, TDD.


def test_a_priced_call_adds_its_cost(space: workspace.Workspace) -> None:
    budget.record(space, 0.04)
    total = budget.record(space, 0.06)
    assert total.spent_usd == pytest.approx(0.10)
    assert total.calls == 2 and total.unpriced == 0


def test_an_unpriced_call_is_counted_and_not_costed(space: workspace.Workspace) -> None:
    """R3.3 — the requirement that keeps a subscription provider from lying with a zero.

    Recording `None` as `0.0` would report a workspace that spent all month as having spent
    nothing, and the number would look authoritative while being false.
    """
    budget.record(space, 0.25)
    total = budget.record(space, None)
    assert total.spent_usd == pytest.approx(0.25)
    assert total.calls == 2 and total.unpriced == 1


def test_a_call_priced_at_zero_is_not_an_unpriced_one(space: workspace.Workspace) -> None:
    """A provider saying "this one was free" and a provider saying nothing are different
    facts, and the whole point of R3.3 is not to conflate them."""
    total = budget.record(space, 0.0)
    assert total.calls == 1 and total.unpriced == 0


def test_accumulation_does_not_drift(space: workspace.Workspace) -> None:
    """Floating point over many small amounts is the failure `methodology.md` names: wrong
    per call is invisible, wrong by the end of the month is not."""
    for _ in range(100):
        budget.record(space, 0.01)
    assert budget.load(space).spent_usd == pytest.approx(1.0, abs=1e-9)


def test_a_total_survives_being_read_back(space: workspace.Workspace) -> None:
    budget.record(space, 1.5)
    assert budget.load(space) == budget.Total(spent_usd=1.5, calls=1, unpriced=0)


def test_no_total_yet_is_zero_rather_than_an_error(space: workspace.Workspace) -> None:
    assert budget.load(space) == budget.Total()


def test_an_unreadable_total_is_refused_rather_than_silently_restarted(
    space: workspace.Workspace,
) -> None:
    """Starting the count again because a file would not parse is how a ceiling stops
    meaning anything, quietly."""
    budget.path_of(space).write_text("{not json", encoding="utf-8")
    with pytest.raises(SscError) as refused:
        budget.load(space)
    assert refused.value.code == "invalid-budget"


def test_a_total_of_the_wrong_schema_is_refused(space: workspace.Workspace) -> None:
    budget.path_of(space).write_text(json.dumps({"schema": 99}), encoding="utf-8")
    with pytest.raises(SscError):
        budget.load(space)


# R3.4 — the lock.


def test_the_lock_is_released_even_where_the_update_failed(
    space: workspace.Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock that outlives a failed command turns one error into every later command
    erroring, which is worse than the race it was guarding."""
    monkeypatch.setattr(budget, "write_atomically", _boom)
    with pytest.raises(RuntimeError):
        budget.record(space, 1.0)

    assert not (space.root / f"{budget.TOTAL_NAME}.lock").exists()

    monkeypatch.undo()
    budget.record(space, 1.0)  # the next command is not blocked by a lock nobody released


def _boom(*_: Any, **__: Any) -> None:
    raise RuntimeError("the disk went away")


def test_a_held_lock_is_reported_rather_than_waited_on_for_ever(
    space: workspace.Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(budget, "LOCK_TIMEOUT_SECONDS", 0.05)
    (space.root / f"{budget.TOTAL_NAME}.lock").write_text("held", encoding="utf-8")
    with pytest.raises(UsageError) as refused:
        budget.record(space, 1.0)
    assert refused.value.code == "budget-locked"


# R1.1, R1.2, R1.3 — the free path.


def test_widening_a_canvas_with_no_prompt_is_refused_as_padding() -> None:
    """R1.1. Padding with the key colour *is* what the outpaint would have produced, so
    paying for it buys a `np.pad`. Exact, therefore a refusal."""
    free = budget.covered_by(FakeAsk(verb="gen expand", prompt=""), ())
    assert free is not None and free.exact is True
    assert "tool expand" in free.command
    with pytest.raises(UsageError) as refused:
        budget.clear(free)
    assert refused.value.code == "free-path"


def test_widening_a_canvas_with_a_prompt_is_generation() -> None:
    """R1.3 — the discriminator is the argument that already carries the intent. A prompt
    means invented content, which is what a model is for, and no flag turns this off."""
    assert budget.covered_by(FakeAsk(verb="gen expand", prompt="a ruined tower"), ()) is None


def test_east_when_west_exists_is_reported_and_not_refused() -> None:
    """R1.2 — the case the plan and the wiki disagree about.

    The plan calls mirroring East-from-West an exact equivalence. The wiki records that it
    breaks on asymmetry — a sheath, a scar, a pauldron on one shoulder — and that the
    breakage is invisible at a glance. Refusing would refuse a call the caller was right to
    make, and R1.3 leaves no flag to escape with. So it reports.
    """
    ask = FakeAsk(verb="gen image", prompt="the anchor, turned", variables={"direction": "East"})
    free = budget.covered_by(ask, ("anchor", "west"))
    assert free is not None and free.exact is False
    assert "tool mirror" in free.command
    budget.clear(free)  # reports, does not raise


def test_east_with_no_west_recorded_suggests_nothing() -> None:
    ask = FakeAsk(verb="gen image", variables={"direction": "East"})
    assert budget.covered_by(ask, ("anchor",)) is None


def test_a_direction_is_matched_as_a_word_and_not_a_substring() -> None:
    """`beast` is not East. A substring match would refuse — or here, nag about — an
    ordinary description."""
    ask = FakeAsk(verb="gen image", variables={"direction": "facing the beast"})
    assert budget.covered_by(ask, ("west",)) is None


# R2.2, R3.2 — failing closed. Both reviews returned `blocked` on these.


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_ceiling_that_is_not_a_finite_number_is_refused(bad: float) -> None:
    """The fail-open the security review found, and the reason the finiteness check sits
    *before* the sign check.

    `nan < 0` is `False`, so a `NaN` ceiling walked past a negativity test — and then every
    comparison in `check` is `False` on both sides, so the ceiling silently refused nothing,
    for ever, with no error anywhere. YAML spells it `.nan`, so a hand-edited config reaches
    it.
    """
    with pytest.raises(SscError) as refused:
        budget.limits_of({"budget": {"max_usd": bad}})
    assert refused.value.code == "invalid-config"


def test_a_non_finite_ceiling_cannot_reach_the_comparison() -> None:
    """Stated as the property rather than the parse: whatever else changes, a ceiling that
    cannot be compared must not be a ceiling that admits everything."""
    with pytest.raises(SscError):
        budget.check(budget.Limits(max_usd=float("nan")), budget.Total(spent_usd=1e9), None)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_a_total_holding_a_json_extension_constant_is_refused(
    space: workspace.Workspace, token: str
) -> None:
    """`json.loads` accepts these by extension, and `document.get(...) or 0.0` keeps a `NaN`
    because `NaN` is truthy. Same fail-open, arriving through the file this code writes."""
    budget.path_of(space).write_text(
        '{"schema": 1, "spent_usd": ' + token + ', "calls": 1, "unpriced": 0}', encoding="utf-8"
    )
    with pytest.raises(SscError) as refused:
        budget.load(space)
    assert refused.value.code == "invalid-budget"


def test_a_negative_total_is_refused(space: workspace.Workspace) -> None:
    """Negative spend buys headroom the same way `NaN` does, and means nothing besides."""
    budget.path_of(space).write_text(
        json.dumps({"schema": 1, "spent_usd": -100.0, "calls": 1, "unpriced": 0}),
        encoding="utf-8",
    )
    with pytest.raises(SscError):
        budget.load(space)


# R3.2 — counted once, whoever collected it.


def a_job(**over: Any) -> Any:
    from ssc.cli import jobs

    job = jobs.Job.new(
        id="j-0001",
        provider="fake",
        application="fake/model",
        model="model",
        arguments={},
        at="2026-08-03T10:00:00Z",
    )
    return job.to_state("done", at="2026-08-03T10:01:00Z") if not over else job


def test_a_job_is_counted_once_however_many_routes_collect_it(
    space: workspace.Workspace,
) -> None:
    """The critical finding both reviews returned.

    A result is collected by three routes — `gen` waiting, `gen collect` after `--no-wait`,
    and `job resume`. Counting inside the waiting path alone meant `--no-wait`, an ordinary
    supported flag, submitted billed work the ceiling never saw. Counting on every route
    without a flag would count the same money twice.
    """
    from ssc.cli import jobs

    job = a_job()
    jobs.save(space, job)

    _, marked = budget.reserve(space, budget.Limits(), None, job)
    assert budget.load(space).calls == 1 and marked.counted is True

    _, again = budget.reserve(space, budget.Limits(), None, marked)
    assert budget.load(space).calls == 1  # the second route collects, and does not bill again
    assert again.counted is True

    # And the flag survives the round trip, so a fresh process does not recount either.
    assert jobs.load(space, "j-0001").counted is True
    budget.reserve(space, budget.Limits(), None, jobs.load(space, "j-0001"))
    assert budget.load(space).calls == 1


def test_settling_twice_folds_one_price(space: workspace.Workspace) -> None:
    """R3.7 — the idempotency that matters once a price exists.

    Counting moved to submission, so `gen collect` and `job resume` no longer count; they
    settle. With no provider pricing anything today, settling is a no-op — which means the
    end-to-end "collected twice" test proves nothing about this on its own. This does.
    """
    from ssc.cli import jobs

    job = a_job()
    jobs.save(space, job)
    budget.reserve(space, budget.Limits(), None, job)
    assert budget.load(space) == budget.Total(spent_usd=0.0, calls=1, unpriced=1)

    settled, priced = budget.settle(space, jobs.load(space, job.id), 0.40)
    assert settled == budget.Total(spent_usd=0.40, calls=1, unpriced=0)

    # The second route collects the same result and must fold nothing further in.
    again, _ = budget.settle(space, priced, 0.40)
    assert again == settled
    assert budget.load(space).spent_usd == pytest.approx(0.40)


def test_a_price_that_arrives_does_not_recount_the_call(space: workspace.Workspace) -> None:
    """`calls` counts calls and `spent_usd` counts money, and a price arriving late is not a
    second call. Getting this wrong inflates the count that the ceiling reads."""
    from ssc.cli import jobs

    job = a_job()
    jobs.save(space, job)
    budget.reserve(space, budget.Limits(), None, job)
    settled, _ = budget.settle(space, jobs.load(space, job.id), 1.25)
    assert settled.calls == 1


# The four defects the reviews returned. Each of these fails against the code as it stood
# before the fix beside it, which is the only thing that makes them regression tests rather
# than restatements of the implementation.


def test_concurrent_processes_do_not_lose_an_update(
    space: workspace.Workspace, tmp_path: Path
) -> None:
    """R3.4, across processes rather than inside one — and the distinction is the whole bug.

    `os.open` with `O_EXCL` raises `FileExistsError` when the lock file merely exists on
    disk, and on Windows `PermissionError` when another *process* is holding it open. The
    lock caught only the first, so every genuinely concurrent writer fell straight out of the
    retry loop: a four-process run lost 50 of 200 updates. Every existing lock test was
    single-process — the second attempt was made by the same process that had already closed
    the handle — so all of them passed against the broken code.

    This one spawns real interpreters for that reason. It is the slowest test in the file and
    it is the only one that can see the defect.
    """
    workers, each = 4, 25
    child = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from ssc.cli import budget
        from ssc.cli.workspace import Workspace

        space = Workspace(root=Path(sys.argv[1]))
        for _ in range(int(sys.argv[2])):
            budget.record(space, 0.01)
        """
    )
    script = tmp_path / "hammer.py"
    script.write_text(child, encoding="utf-8")

    running = [
        subprocess.Popen(
            [sys.executable, str(script), str(space.root), str(each)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(workers)
    ]
    for process in running:
        _, complained = process.communicate(timeout=120)
        assert process.returncode == 0, complained.decode(errors="replace")

    total = budget.load(space)
    assert total.calls == workers * each
    assert total.spent_usd == pytest.approx(workers * each * 0.01)


def test_a_lock_another_process_holds_open_is_waited_for_not_raised(
    space: workspace.Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3.4 — the exact mechanism the cross-process test above cannot pin down.

    That test is honest about concurrency and useless as a regression test for *this*: the
    race it depends on showed up in two runs out of five, so it passes against the broken
    lock most of the time. This one is deterministic. It makes `os.open` fail the way Windows
    fails when another process is holding the lock file open — `PermissionError`, not
    `FileExistsError` — and asserts the retry loop treats it as contention.

    Against the code as it stood, `PermissionError` was not caught, so it escaped `__enter__`
    and the update was lost. Reverting the `except` clause fails this test every time.
    """
    attempts: list[int] = []
    real_open = os.open

    def sticky(path: Any, flags: int, *rest: Any, **kw: Any) -> int:
        if str(path).endswith(f"{budget.TOTAL_NAME}.lock"):
            attempts.append(1)
            if len(attempts) == 1:
                # The file exists, as it would while a holder has it: this is contention,
                # not an unwritable directory.
                Path(path).write_bytes(b"")
                raise PermissionError(13, "being used by another process")
            if len(attempts) == 2:
                Path(path).unlink(missing_ok=True)
        return real_open(path, flags, *rest, **kw)

    monkeypatch.setattr(os, "open", sticky)
    budget.record(space, 0.25)

    assert len(attempts) >= 2, "the lock gave up instead of retrying"
    assert budget.load(space).spent_usd == pytest.approx(0.25)


def test_a_permission_error_with_no_lock_present_is_not_retried(
    space: workspace.Workspace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of the same clause, and why it is not simply `except PermissionError`.

    A `PermissionError` with no lock file on disk is an unwritable directory, not a holder.
    Retrying it would spin for the full timeout and then answer "another ssc command may be
    running; if none is, delete that file" about a file that was never there. It is
    distinguished by what is on disk rather than by `os.name`, which keeps one code path
    under test on both platforms.
    """
    real_open = os.open

    def denied(path: Any, flags: int, *rest: Any, **kw: Any) -> int:
        if str(path).endswith(f"{budget.TOTAL_NAME}.lock"):
            raise PermissionError(13, "permission denied")
        return real_open(path, flags, *rest, **kw)

    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(PermissionError):
        budget.record(space, 0.25)


def test_a_reservation_is_visible_before_the_call_is_submitted(
    space: workspace.Workspace,
) -> None:
    """R2.2 with R3.4 — the ceiling has to be decided and published in one step.

    Asking the ceiling in one critical section and recording the answer in another leaves the
    paid call in the gap: every concurrent `gen` reads the same total, every one is under the
    ceiling, every one submits. The property that closes it is this one — once `reserve`
    returns, the call is already in the total that the next caller will read, and no
    submission has happened yet.
    """
    from ssc.cli import jobs

    job = a_job()
    jobs.save(space, job)

    assert budget.load(space).calls == 0
    _, reserved = budget.reserve(space, budget.Limits(max_usd=10.0), None, job)
    # Nothing has been submitted, and the next reader already sees the call.
    assert reserved.counted is True
    assert budget.load(space).calls == 1


def test_a_reservation_is_refused_once_the_ceiling_is_reached(
    space: workspace.Workspace,
) -> None:
    """R2.2 — and it refuses *before* writing, so a refusal costs the total nothing."""
    from ssc.cli import jobs

    spent = a_job()
    jobs.save(space, spent)
    budget.reserve(space, budget.Limits(), None, spent)
    budget.settle(space, jobs.load(space, spent.id), 5.0)

    # Built here rather than through `a_job`, whose kwargs only flip the state and do not
    # reach the record — a second call needs a genuinely different id.
    nxt = jobs.Job.new(
        id="j-0002",
        provider="fake",
        application="fake/model",
        model="model",
        arguments={},
        at="2026-08-03T10:02:00Z",
    )
    jobs.save(space, nxt)
    with pytest.raises(UsageError) as refused:
        budget.reserve(space, budget.Limits(max_usd=5.0), None, nxt)
    assert refused.value.code == "over-budget"
    # The refused call was not counted, and the refusal did not move the money.
    assert budget.load(space).calls == 1
    assert jobs.load(space, "j-0002").counted is False


def test_a_reservation_is_given_back_when_the_call_is_never_submitted(
    space: workspace.Workspace,
) -> None:
    """R3.2 — a `submit` that raised did not submit a call, so the total must not hold one.

    Otherwise an unreachable network spends a ceiling on calls that reached nobody.
    """
    from ssc.cli import jobs

    job = a_job()
    jobs.save(space, job)
    _, reserved = budget.reserve(space, budget.Limits(), None, job)
    assert budget.load(space).calls == 1

    given_back = budget.release(space, reserved)
    assert given_back.counted is False
    assert budget.load(space) == budget.Total(spent_usd=0.0, calls=0, unpriced=0)
    # And releasing twice does not drive the total below nothing.
    budget.release(space, given_back)
    assert budget.load(space).calls == 0


def test_two_routes_holding_the_same_job_settle_one_price(
    space: workspace.Workspace,
) -> None:
    """R3.7 — the idempotency check has to be made against disk, inside the lock.

    `gen collect` and `job resume` legitimately load the same job before either settles, so
    both in-memory copies say `cost_usd is None`. Deciding from the caller's copy let both
    pass and both add the cost: one call billed once and counted twice. Unreachable only
    while no provider prices a call, which is exactly the failure `methodology.md` names for
    money code — invisible per call, wrong by the end of the month.
    """
    from ssc.cli import jobs

    job = a_job()
    jobs.save(space, job)
    budget.reserve(space, budget.Limits(), None, job)

    # Both routes take their copy before either of them settles.
    one_route = jobs.load(space, job.id)
    other_route = jobs.load(space, job.id)

    budget.settle(space, one_route, 0.40)
    budget.settle(space, other_route, 0.40)

    assert budget.load(space).spent_usd == pytest.approx(0.40)
    assert budget.load(space).calls == 1


@pytest.mark.parametrize("recorded", ["", False, [], {}, "abc"])
def test_a_total_that_is_not_a_number_is_refused_rather_than_read_as_zero(
    space: workspace.Workspace, recorded: Any
) -> None:
    """R3.6, reached through the door the `NaN` fix left open.

    `document.get(name) or 0.0` swapped every *falsy* value for the default before anything
    could object, so `"spent_usd": ""` read as a workspace that had spent nothing while
    `"abc"` was correctly refused. A workspace five dollars into a five dollar ceiling then
    enforced against zero. `false` is in this list for its own reason: `float(False)` is
    `0.0` and `isinstance(True, int)` is true, so a bool is the one non-number that walks
    through every numeric check Python offers.
    """
    (space.root / budget.TOTAL_NAME).write_text(
        json.dumps({"schema": budget.SCHEMA, "spent_usd": recorded, "calls": 1, "unpriced": 0}),
        encoding="utf-8",
    )
    with pytest.raises(SscError) as refused:
        budget.load(space)
    assert refused.value.code == "invalid-budget"
