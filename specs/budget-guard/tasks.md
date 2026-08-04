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

## Notes

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
