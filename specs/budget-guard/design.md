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
ceiling          ← R2.2, on the estimate
credential, job, submit
record the cost  ← R3.2, once the provider says what it was
```

**The free path is first because it is the only refusal that holds regardless of money.** A
workspace with no ceiling still should not pay for a `np.pad`. **The cache is checked before
the ceiling**, because a hit submits nothing and refusing a free reuse for being over budget
would be refusing to spend nothing.

`budget.max_usd` and `budget.warn_at` are read through `cli/config.py`, already the one
reader of `ssc.yaml` — `gen-fal` made it that when `models:` became the second setting.

## Boundaries and contracts

Serves R2.3, R3.1, R3.2, R3.3, R3.4.

**The total is a file, and two commands may write it at once.** `jobs/` already assumes
concurrent writers and `atomic.replace` already exists for it. But `atomic.replace` makes
each *write* whole; it does not make a read-modify-write atomic, and a running total is
exactly that. So the update takes a lock, and R3.4 is written about losing an update rather
than about corrupting a file — different failures, and only one of them is the one
`atomic.replace` already prevents.

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
