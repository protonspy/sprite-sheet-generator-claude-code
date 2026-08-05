# Budget guard — tasks

**What already covers these paths:** `tests/cli/test_gen_commands.py` covers `gen.run`, the
pipeline this inserts two refusals into and reads a cost back from; `tests/cli/test_jobs.py`
and `tests/cli/test_job_commands.py` cover the `cost_usd` field the total reads and the
`atomic` writes the total borrows; `tests/cli/test_kinds.py` covers `cli/config.py`, the one
reader of `ssc.yaml` that `budget:` joins. 165 tests, run green before this work started.

## 1 · The free path

- [x] 1.1 (Unit) Refuse a paid call a deterministic command produces exactly, naming that command as the fix — R1.1, R1.3
- [x] 1.2 (Unit) Report, without refusing, a deterministic command that may produce the same result — R1.2, R1.3
- [x] 1.3 (Unit) `--dry-run` reports whichever of those two applies — R1.4
- [x] 1.4 (Unit) Refuse a colour-variant paid call, naming ssc tool recolour — R1.5
  _Reason R1.5 delta from plan task 5.4: a gen image colour variant of an existing tool style stage is exact, refused under R1.1 not reported under R1.2_

## 2 · The ceiling

- [x] 2.1 (Unit) Read `budget.max_usd` and `budget.warn_at` through `cli/config.py`, and run unrestricted when neither is declared — R2.1, R2.5
- [x] 2.2 (TDD) Refuse a call the total has already used up or an estimate would carry past the ceiling, report both amounts, and warn above the threshold — R2.2, R2.3, R2.4
- [x] 2.3 (Unit) Refuse on the estimate before the call and record what it actually cost after — R2.6

## 3 · The total

- [x] 3.1 (TDD) Add a reported cost to the running total, and count a call the provider priced at nothing as unpriced rather than free — R3.2, R3.3
- [x] 3.2 (Unit) Update the total under a lock, so a concurrent update is not lost — R3.4
- [x] 3.3 (Unit) `ssc budget` reports the total, the ceiling, and how many calls the total omits — R3.1, R3.3
- [x] 3.4 (Unit) Count a call when it is submitted, once, and settle its price later without recounting it — R3.2, R3.5, R3.7
- [x] 3.5 (Unit) Refuse a ceiling or a total that is not a finite, non-negative amount — R3.6

## 4 · What the reviews returned

- [x] 4.1 (TDD) Decide the ceiling and record the call in one step, before the call is submitted, and give the reservation back where the submission never happened — R3.8, R3.2
- [x] 4.2 (TDD) Wait for a lock another process is holding, without mistaking an unwritable directory for one — R3.9, R3.4
- [x] 4.3 (Unit) Decide from the record on disk, inside the lock, so two routes holding one job settle one price — R3.7, R3.5
- [x] 4.4 (Unit) Refuse a total that is not a number rather than defaulting a falsy one to zero — R3.6

## Notes

**Group 4 is a fix round, and the red was observed on every task in it.** Each fix was
reverted after its test was written and the test run against the broken code: the lock test
fails 3 runs out of 3 with `PermissionError` escaping `__enter__`, the settle test reports
`0.8 == 0.4` for one $0.40 call, the falsy-total test fails on four of its five values, and
the reservation tests fail when `reserve` stops publishing before it returns. That is the
point of RED and it is why these are regression tests rather than restatements of the code.

**4.2 took two attempts, and the second review caught the first one.** Catching
`PermissionError` fixed the lock; disambiguating it with `self._path.exists()` inside the
retry loop then broke the same guarantee a narrower way, because that check races the holder
it is asking about. It surfaced as a flaky suite — one full run in three — which is the
reason it is worth naming here: the first fix was verified by a deterministic test that
could not see it, since the test writes the lock file before raising and so never races
anything. Waiting first and deciding afterwards has both properties, and
`test_a_lock_released_in_the_racy_window_is_still_waited_for` fails 3 runs out of 3 against
the version that decided early.

**The cross-process concurrency test is kept and is deliberately not the regression test.**
It spawns four interpreters and asserts no update is lost, which is worth having — it catches
the lock being removed outright. It does *not* reliably catch the defect it was written for:
the race showed up in two runs out of five for the reviewer, and passed three times out of
three here against the broken lock. A test that finds its bug sometimes is not evidence, so
`4.2` is pinned by a deterministic test that forces the platform's error instead of hoping
for it.

**Whether the red was observed on 2.2 and 3.1 originally cannot be established.** This leaf
was recovered from an uncommitted working tree with no incremental history, so the record
that `methodology.md` asks for is simply absent and no one can now say either way.

Rather than assert something unverifiable, both were checked the way group 4's were.
Disabling the ceiling comparison fails three tests, `test_a_total_that_has_reached_the_ceiling_refuses_the_next_call`
among them; dropping the `unpriced` increment in `Total.plus` fails
`test_an_unpriced_call_is_counted_and_not_costed` and `test_settling_twice_folds_one_price`.
So the tests do constrain the behaviour their tasks claim. That is strictly weaker than
having watched the red when the code was written — it shows the tests are load-bearing, not
that they were written first — and the distinction is left visible rather than smoothed over.

**Two TDD tasks, and both are money rather than complexity.** 2.2 decides whether a call
happens, and being wrong in the permissive direction spends money nobody authorised while
being wrong in the strict direction refuses work with no way around it — the test says where
the boundary is before the code gets a vote. 3.1 is arithmetic over a running total, which
is the case `methodology.md` names outright: a rounding or accumulation error here is
invisible per call and wrong by the end of the month.

**1.1 and 1.2 are two tasks because they are two answers, and the plan and the wiki
disagree about which one `mirror` gets.** See the note on R1.2. The split is what lets the
disagreement be recorded rather than decided by whoever writes the code first.

**Order matters inside `gen.run` and is asserted, not assumed.** Free path, then cache, then
ceiling. A test that only checks each refusal in isolation would pass with them in any
order, and the wrong order refuses a cached — free — reuse for being over budget.
