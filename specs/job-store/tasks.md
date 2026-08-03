# Job store — tasks

**What already covers these paths:** `tests/cli/test_atomic.py` covers temp-plus-rename and
the refusal to overwrite, which R1.2 is built on; `tests/cli/test_meta.py` covers the
record-on-disk pattern this follows; `tests/cli/test_workspace.py` covers locating a
workspace and the directories `init` creates, which `jobs/` joins. All were run green before
this work started.

## 1 · The record

- [x] 1.1 (Unit) Model a job — id, provider, application, request id, model, arguments, state, cost, history — and read it back — R1.3
- [x] 1.2 (TDD) Write a job atomically, and write it before the call it describes is made — R1.1, R1.2
- [x] 1.3 (Unit) Create `jobs/` with the workspace, and report a file that will not read as a job rather than failing the scan — R1.4
- [x] 1.4 (Unit) Validate a record's shapes, not only its keys, so a bad file stays local to itself — R1.4
- [x] 1.5 (Unit) Redact a credential-shaped argument on the way to disk, not only on the way to stdout — R1.5

## 2 · The states

- [x] 2.1 (TDD) Move a job between states, stamping each, and refuse any move out of a terminal one — R2.1, R2.2, R2.3
- [x] 2.2 (Unit) Define the provider interface and the registry that starts empty — R3.7

## 3 · The commands

- [x] 3.1 (Unit) `ssc job list` — every job with its state, most recent first — R3.1
- [x] 3.2 (Unit) `ssc job status` — ask the provider where the job is unfinished, record what it says — R3.2
- [x] 3.3 (Unit) `ssc job wait` — poll to a deadline, and say which of finished or timed out happened — R3.3
- [x] 3.4 (Unit) `ssc job cancel` — ask the provider, record the outcome — R3.4
- [x] 3.5 (Unit) `ssc job resume` — collect a finished job's result from the record alone — R3.5
- [x] 3.6 (Unit) Refuse an id that names no job, and report what is on disk where no provider is registered — R3.6, R3.7

## Notes

**Two tasks are TDD, and both are about money rather than about complexity.**

1.2 is the ordering the whole store exists for: the record is written, *then* the call is
made. Written the other way round it still passes every test about what a job file contains,
and loses exactly one thing — the id of a request that was already billed, in the window
where the process died. The test that catches it has to observe the order, so it is written
first.

2.1 is the terminal-state rule. A provider answering `running` about a job we recorded as
`done` would re-open a job whose result is already collected and paid for; the failure is
silent and the second collection costs again on some providers. RED here is a transition that
should be refused and is not.

**The red was observed on both.** 1.2 and 2.1 failed on `ImportError` before `cli/jobs.py`
existed, and the assertions that mattered were written before the module they describe: the
submit test observes the record on disk *from inside* the provider call, which is the only
place the order is visible, and the terminal test is parametrised over every state against
every terminal one, so an absorbing rule that holds for `done` and not `cancelled` fails it.
