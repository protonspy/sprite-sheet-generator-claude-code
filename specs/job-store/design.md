# Job store — design

## What changes

Serves R1.1, R1.2, R1.3, R2.1, R2.2, R3.1 to R3.5.

Two new modules — `cli/jobs.py` for the store and `cli/commands/job.py` for the surface —
and a `Provider` protocol the store calls through.

**The store is `cli/`, not `core/`.** `core/` is pure by this project's rule: arrays in,
arrays out, no IO. A job store is nothing *but* IO and clock, so putting it in `core/` would
either break that rule or produce a pure module with no content. The precedent is
`cli/meta.py`, which owns `meta.json` for the same reason.

**One file per job, named by the job's own id**, under `jobs/` in the workspace. Not one
index file: two commands racing on a single document is a lost write, and the whole premise
here is that a *different* process reads and writes this while another may still be running.
A directory of small files makes every operation touch only the job it is about.

**The write goes through `cli/atomic.py`**, which already does temp-plus-rename and is
already what `meta.json` uses. R1.2 is not a new mechanism, it is the existing one applied
where the ADR says it is load-bearing: a half-written job file after a crash is precisely the
case the store exists to survive.

**Order is the whole point of R1.1.** The record is written, and only then is the provider
called; the returned request id is a second write. Submitting first and recording after is
the shape that loses money — the window between the two is exactly when the process dies, and
what is lost is the id of something already billed.

## Boundaries and contracts

Serves R2.3, R3.6, R3.7, and R1.4.

```python
class Provider(Protocol):
    def status(self, application: str, request_id: str) -> str: ...
    def result(self, application: str, request_id: str) -> dict[str, Any]: ...
    def cancel(self, application: str, request_id: str) -> None: ...
```

Three methods, each taking the `(application, request_id)` pair as plain arguments and
holding no state between calls — which is `adr:0006`'s finding restated as an interface, and
what makes `resume` from a fresh process possible at all. It is also what makes this leaf
testable with no network: the recorded pair is the entire state, so a fake provider is a
dozen lines.

**No provider ships here.** A registry maps a provider name to an implementation and starts
empty; `specs/gen-fal/` registers `fal`. A command that needs one for a name nobody has
registered reports everything the record holds and says why it stopped (R3.7) rather than
failing — the record is still the useful part, and "your build has no fal support" is a
different problem from "your job failed".

**A terminal state is final (R2.3).** `done`, `failed` and `cancelled` are absorbing: a
provider that later says `running` about a job we recorded as `done` is answering about
something we have already collected and paid for, and believing it would re-open a job whose
result is on disk. The store refuses the transition and keeps what it has.

**A malformed job file is reported, not fatal (R1.4).** `list` is how somebody diagnoses a
broken `jobs/`, so refusing to list because one file is corrupt makes the diagnostic tool
unavailable exactly when it is needed. This is the same judgement the code review reached
about `asset_dirs` and layout: enforce on the record somebody addressed, tolerate on the
scan.

## Data

Serves R1.3.

```json
{
  "schema": 1,
  "id": "j-20260803-a1b2c3",
  "provider": "fal",
  "application": "fal-ai/nano-banana-2",
  "request_id": "…",
  "model": "nano-banana-2",
  "arguments": {"prompt": "…", "image_size": "1024x1024"},
  "state": "submitted",
  "cost_usd": null,
  "cache_key": "…",
  "counted": false,
  "history": [{"state": "submitted", "at": "2026-08-03T10:00:00Z"}],
  "error": null
}
```

`cost_usd` is nullable on purpose and `specs/budget-guard/` depends on that: a provider
metering by subscription reports no per-call cost, and a store that modelled cost as a
number would force every such provider to lie with a zero.

`cache_key` and `counted` arrived as deltas, from `specs/gen-fal/` and `specs/budget-guard/`
respectively, and are shown here because a data section that omits half the record is worse
than none — it reads as the whole shape. `cache_key` is carried rather than recomputed at
collection because the key covers the digests of the images sent, which the record
deliberately elides, so a collector deriving it would derive it from less than the submitter
had. `counted` is what keeps one call out of the running total twice when three routes may
collect it (`budget-guard` R3.5); it lives on the job because the alternative is a total that
has to remember every id it ever saw.

`history` rather than a single timestamp, because "when did this become `running`" and "how
long was it queued" are the questions asked after a bad batch, and they cannot be
reconstructed from a mutated field.

## Risks

**The clock.** Every state change stamps a time, and `wait`'s deadline is measured against
one. Both are injected rather than read from `datetime.now()` inside the store, so the tests
do not sleep and do not flake — a store whose test suite is timing-dependent is one nobody
trusts the failures of.
