# Budget guard — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R2.1, R2.2, R2.4, R2.5.

One new module, `cli/budget.py`, and three call sites inside `gen.run` — which is the point
of putting this in `gen` rather than in a skill. A rule that lives in a skill is a rule an
agent forgets under load, and this failure is silent: money spent, plausible output, nobody
notices.

`gen.run`'s order today is cache → credential → job → submit. Two steps go in front and one
behind:

```
free path        ← R1.1, before anything else happens
cache            ← already there; a hit costs nothing, so it outranks the ceiling
reserve          ← R2.2 and R3.8: ask the ceiling and record the answer, in one step
credential, job, submit
release          ← R3.2, only where the submission never happened
settle           ← R3.7, once the provider says what it cost
```

**Asking the ceiling and recording the answer are one step, not two** (R3.8). The obvious
shape — check, submit, then count — puts the paid call in the gap between a read and a
write, and a lock around only the write does nothing about it: every concurrent `gen` reads
the same total, every one of them is under the ceiling, and every one of them submits. The
ceiling is discovered to have been passed after the money is gone. So the check and the
count share one critical section and both happen *before* `submit`.

That is the discipline `jobs.submit` already applies one layer down, where the record is
written before the provider is called so a death in the window cannot lose an already-billed
request. The cost of reserving first is a reservation matching no call when a submission
fails, which `release` gives back (R3.2) — a `submit` that raised returned no request id, so
nothing was accepted. What it cannot distinguish is a call billed and then lost on the way
back; the job record, saved as `failed`, is what a person acts on there.

**The free path is first because it is the only refusal that holds regardless of money.** A
workspace with no ceiling still should not pay for a `np.pad`. **The cache is checked before
the ceiling**, because a hit submits nothing and refusing a free reuse for being over budget
would be refusing to spend nothing.

`budget.max_usd` and `budget.warn_at` are read through `cli/config.py`, already the one
reader of `ssc.yaml` — `gen-fal` made it that when `models:` became the second setting.

## Boundaries and contracts

Serves R2.3, R3.1, R3.2, R3.3, R3.4, R3.8, R3.9.

**The total is a file, and two commands may write it at once.** `jobs/` already assumes
concurrent writers and `atomic.replace` already exists for it. But `atomic.replace` makes
each *write* whole; it does not make a read-modify-write atomic, and a running total is
exactly that. So the update takes a lock, and R3.4 is written about losing an update rather
than about corrupting a file — different failures, and only one of them is the one
`atomic.replace` already prevents.

**The lock is an exclusive create, and what it must catch is platform-dependent** (R3.9).
`os.open` with `O_CREAT | O_EXCL` raises `FileExistsError` when the lock file merely exists
on disk, and on Windows `PermissionError` when another *process* is holding it open. Catching
only the first is a lock that works within one process and fails between them — which is the
only case it exists for. One code path rather than a branch on `os.name`, because task 0.12
already paid for a platform-conditional branch that was dead everywhere.

**Nothing is decided while waiting.** Both errors retry until the timeout, and only then is
it asked which happened — a `PermissionError` with no lock file present is reported as an
unwritable directory rather than as a held lock. Deciding that *during* the loop was the
first attempt and it lost the race it was describing: the holder unlinks as it releases, so a
waiter whose open failed microseconds earlier sees no file and concludes there was no
contention. Once waiting is over nothing depends on the answer, so the same question is safe
to ask. The cost is a real permissions failure taking the full timeout to surface; it is an
error path, and a command that occasionally refuses to wait is worse than one that waits ten
seconds before reporting a genuine fault.

**Every idempotency check is made against disk, inside the lock.** `reserve` and `settle`
both decide whether a call has already been counted or priced, and both reload the job record
rather than trusting the caller's copy. Two collecting routes legitimately hold the same job
loaded before either wrote, so a check against an in-memory snapshot passes twice and bills
once — one call counted or priced two times.

**An unpriced call is counted, not costed.** A provider metering by subscription reports no
per-call cost, and recording a zero would make `ssc budget` report a workspace that spent
all month as having spent nothing. So the total carries two numbers — an amount, and a count
of the calls that had no amount — and reports both. It is the shape `job-store` already
chose when it made `cost_usd` nullable, restated one level up.

**The estimate and the actual are different numbers, and both are recorded.** R2.5 refuses
on the estimate because that is all there is before a call, and records the actual
afterwards because that is what was spent. Where a provider offers no estimate there is
nothing to refuse on: the call proceeds and the total catches up after the fact. That is why
R2.2 says "estimated" rather than "cost", and it is honest rather than lax — the alternative
is below.

## Alternatives considered

**Refusing when no estimate is available.** It sounds safer and it makes `gen` unusable
against any provider that does not publish a price, which today is most of them for most
models. It converts a missing number into a broken tool. Reporting the gap (R3.3) keeps the
workspace honest without making it useless.

**Putting the free-path check in the `sprite-*` skills.** The plan rejected this already and
the reason is worth keeping visible: a skill is instructions an agent may not follow, and
this particular failure produces *correct output*. Nobody files a bug about art that came
out fine and cost four dollars.
