---
autonomy: auto
ci: wait
---

# Budget guard — requirements

## Purpose

Nothing in `ssc` spends money without being asked, and this is where "being asked" is
defined. Three things, in the order they matter: whether a free command produces the same
result — asked by the expensive command itself, before anything else — then a ceiling the
workspace declares that every `gen` is refused against, then a running total of what was
actually spent.

`specs/gen-fal/` hands this leaf a job record carrying `cost_usd` and the resolved call.
This leaf never submits anything. It decides whether a submission may happen, and records
what it cost once it has.

## R1 · The free path

- **R1.1** If a deterministic command produces the same result as a paid call, then the `ssc` CLI shall refuse that call and name the command that produces it.
- **R1.2** Where a deterministic command may produce the same result but cannot be shown to, the `ssc` CLI shall report it as an alternative and shall proceed.
- **R1.3** The `ssc` CLI shall decide both from what the caller asked for, and not from an option that turns the check off.
- **R1.4** While `--dry-run` is given, the `ssc` CLI shall report any free command that covers or may cover the call.
- **R1.5** When the caller asks `gen image` for a colour variant of an existing stage, then the `ssc` CLI shall refuse the call and name `ssc tool recolour`.

> **R1.5 is exact (R1.1), not reported (R1.2).** A colour variant of a `tool style`
> output is flat-coloured regions, and a colour map reproduces what a model would
> redraw, so paying for it buys a `recolour` the caller already has the data to run. The
> asymmetry caveat that makes mirroring inexact does not apply: swapping red for blue does
> not discover a pauldron. The signal is `--var recolor=<stage>` naming the stage to map
> from, the structured way `direction=East` names mirroring — and the refusal names the
> stage, so the caller builds the colour map against the right input.

> **R1.2 exists because the plan and the wiki disagree, and the disagreement is real.**
> `plans/ssc-pipeline.md` gives two free-path cases and says of both that "the deterministic
> command is not an approximation of the paid one — it is the same result". That holds for
> padding a flat-chroma border: `np.pad` with the key colour *is* what the outpaint would
> have produced. It does not hold for the other case.
> `docs/wiki/anchor-and-directions.md` records that mirroring West to get East "breaks on
> asymmetry — a book held under one arm, a sheath, a scar, a pauldron on one shoulder" — and
> that the breakage is not visible at a glance.
>
> Refusing on that would be refusing a call the caller was right to make, and R1.3 leaves no
> flag to escape with. Detecting the asymmetry is a vision problem this project does not
> take on. So exact equivalence refuses and likely equivalence reports, and which case a
> given free command falls into is stated where that command is taught, not guessed here.

## R2 · The ceiling

- **R2.1** The `ssc` CLI shall read a spending ceiling and a warning threshold from `ssc.yaml`.
- **R2.2** If the running total has reached the ceiling, then the `ssc` CLI shall refuse the call, report both amounts, and submit nothing.
- **R2.3** If a call's estimated cost would carry the running total past the ceiling, then the `ssc` CLI shall refuse the call, report both amounts, and submit nothing.
- **R2.4** While the running total is past the warning threshold and under the ceiling, the `ssc` CLI shall report that it is and shall proceed.
- **R2.5** Where no ceiling is declared, the `ssc` CLI shall refuse no call for cost.
- **R2.6** The `ssc` CLI shall refuse on an estimate before a call and shall record the actual cost after it.

> **R2.2 and R2.3 are two requirements because only one of them works today.** No provider
> in the registry publishes a per-call price, and this leaf ships no price table — see *Out
> of scope*. So the estimate is usually absent, and a ceiling written only against an
> estimate would never refuse anything: a feature that reports a number and enforces
> nothing.
>
> R2.2 needs no estimate. It asks whether the money already spent has reached the ceiling,
> which is answerable from the total alone, and it is what actually stops a run. R2.3 is the
> tighter check for the day a provider does publish a price, and it is specified now so that
> arriving prices change a number rather than a design.

## R3 · The total

- **R3.1** The `ssc` CLI shall keep a running total of what a workspace has spent, and shall report it.
- **R3.2** When a paid call is submitted, the `ssc` CLI shall add that call to the running total.
- **R3.3** If a provider reports no cost for a call, then the `ssc` CLI shall count that call as unpriced and shall report how many unpriced calls the total omits.
- **R3.4** The `ssc` CLI shall apply an update to the running total without losing an update made concurrently.
- **R3.5** The `ssc` CLI shall add a given call to the running total no more than once.
- **R3.6** If a spending ceiling or a running total cannot be read as a finite, non-negative amount, then the `ssc` CLI shall refuse the call rather than proceed.
- **R3.7** When a provider reports what a submitted call cost, the `ssc` CLI shall add that amount to the running total without counting the call a second time.
- **R3.8** (ADDED) The `ssc` CLI shall decide a call against the ceiling and record that call in the running total as one indivisible step, before the call is submitted.
- **R3.9** (ADDED) While another process holds the running total, the `ssc` CLI shall wait for it rather than fail, and shall not mistake a directory it cannot write for a total another process is holding.

> **R3.8 is what R2.2 and R3.4 each assumed the other covered.** R2.2 says a call is refused
> once the ceiling is reached; R3.4 says an update is not lost. Both held, and the ceiling
> still did not: the check read the total in one critical section and the count wrote it in
> another, with the paid call in between. Every concurrent `gen` cleared the same stale
> figure, so five calls against a ceiling with room for one all submitted. A lock around the
> write cannot see this, because the decision was already taken outside it.
>
> Stated as its own requirement rather than folded into R2.2 because it is a claim about
> *when* the decision and the record happen relative to the call, which is exactly what an
> implementation satisfying both R2.2 and R3.4 was free to get wrong.
>
> **R3.9 is the same lesson as task 0.12, arriving in a different module.** The lock is an
> exclusive create; `FileExistsError` is what it raises when the file exists, and
> `PermissionError` is what Windows raises when another process is *holding* it. Catching
> only the first produced a lock that worked in every single-process test and lost updates
> between real processes — the case it exists for.
>
> **The second clause is there because the first fix for the first clause broke it.** Telling
> a holder apart from an unwritable directory by asking whether the lock file exists *at the
> moment the open failed* races the holder: it unlinks as it releases, so a waiter that lost
> by microseconds sees no file, decides there was no contention, and fails outright. That is
> the breach this requirement exists to prevent, reintroduced by its own remedy, and it
> showed up as a flaky suite rather than a red one. So nothing is decided while waiting —
> both errors are retried, and which of the two happened is settled only once the timeout has
> expired and the answer no longer changes anything. An unwritable directory therefore costs
> the full timeout before it is reported, which is the price of a distinction that cannot be
> drawn race-free while it still matters.
>
> **R3.6 needed a second door closed.** The `NaN` fix left `document.get(name) or 0.0` in
> place, which swaps every *falsy* value for the default before anything can object:
> `"spent_usd": ""` read as zero, so a workspace five dollars into a five dollar ceiling
> enforced against nothing, while `"abc"` was correctly refused. `false` is the same hole
> once more — `float(False)` is `0.0` and `isinstance(True, int)` is true, so a bool walks
> through every numeric check Python offers. Absent and null are the two ways a record says
> nothing; everything else is a value that must be accepted or refused, never defaulted.

> **R3.2 was rewritten twice, and the second review is why.** It first said "when a provider
> reports what a call cost", which the implementation honoured by counting inside the one
> branch of `gen.run` that waits — so `--no-wait` submitted billed work the ceiling never
> saw. Rewriting it around *collection* closed that permanently-invisible case and left a
> reachable one: a caller looping `--no-wait` and never collecting still spent without the
> total moving, because nothing had collected anything.
>
> So the event is **submission**. The money is committed the moment `jobs.submit` returns,
> whatever happens afterwards, and that is the only moment every paid call passes through.
> A call is counted there with no amount, because at submission there is no amount to know;
> R3.7 folds the real figure in later without counting the call again. R3.5 is what keeps
> three collecting routes from billing one call three times, and the flag making it
> idempotent lives on the job (`job-store` R1.7).
>
> **R3.6 exists because the guard failed open.** `NaN` walks past a negativity check —
> `nan < 0` is `False` — and then every comparison against it is `False` too, so a single
> `.nan` in `ssc.yaml`, or a `NaN` token in `budget.json` which `json.loads` accepts by
> extension, silently disabled the ceiling for ever with no error anywhere. A control that
> cannot be evaluated has to refuse, not permit.

## Out of scope

**A price list.** No table of what each model charges ships here. A hard-coded price is
wrong the week a model is repriced, and wrong in the direction that spends money. R2.2
refuses on what is known; where nothing is known there is nothing to refuse on, and R3.3 is
what keeps that visible instead of letting it look like zero.

**Per-provider metering rules.** A provider billing by subscription reports no per-call
cost and must not be made to lie with a zero — that is R3.3's whole reason — but the shape
of a second provider's meter is guesswork until there is a second provider.

**Retry.** What a transient network error does belongs to `specs/gen-fal/`. A retry is not
a second purchase and must not touch this total; a retry that submitted twice would be a
defect there rather than a policy here.

**Refusing a call for being slow, large, or unwise.** This leaf refuses for exactly two
reasons: a free command does the same thing, or the money is not there.
