---
autonomy: auto
ci: wait
---

# Job store — requirements

## Purpose

Everything under `gen` is paid at submission and collected later, which means the process
that spent the money can die before it gets anything back — a crash, a timeout, a closed
laptop, a session that ran out of context. The result is sitting on the provider's side,
already billed, addressable only by an id. This feature is the disk that id lives on: one
file per job, written before the call is made, and a set of commands that let a *different*
process ask about, collect, or cancel work it never submitted.

See `adr:0005-a-job-always-exists` for why there is no synchronous path that skips this, and
`adr:0006-job-store-rides-the-fal-client-handle-surface` for the provider capability it
assumes.

## R1 · The record

- **R1.1** The `ssc` CLI shall write a job's record to disk before the provider call it describes is made.
- **R1.2** The `ssc` CLI shall write a job record atomically, leaving either the previous record or the new one after an interrupted write.
- **R1.3** The `ssc` CLI shall record, for each job, its own id, the provider, the application, the provider's request id, the arguments as resolved, the model, its state, its cost, and when it entered each state it has been in.
- **R1.4** If a file under the jobs directory cannot be read as a job record, then the `ssc` CLI shall report that file and continue with the others.
- **R1.5** The `ssc` CLI shall replace a credential-shaped argument with `***` before writing a job record, as well as before reporting one.
- **R1.6** (ADDED) Where a producer stores what a job returns, the `ssc` CLI shall record the key it will be stored under, as part of that job's record.
- **R1.7** (ADDED) The `ssc` CLI shall record, for each job, whether that call has already been counted against what the workspace has spent.

> **R1.6, added by `specs/gen-fal/`.** A job says what was paid for; the key the result is
> kept under is part of that, and it cannot be derived later. The key covers the inputs to
> the call — for `gen`, the digests of the images sent — and the record deliberately elides
> those to stay readable, so a collector reconstructing the key would be working from less
> than the submitter had. Without it, `gen --no-wait` followed by `gen collect` files the
> result and caches nothing, and the next identical call is billed for bytes already on
> disk. Nullable, and for the same reason `cost_usd` is: the store does not know what a
> cache is, and a producer that keys nothing leaves it unset.
>
> **R1.7, added by `specs/budget-guard/`.** A result is collected by three routes — `gen`
> waiting for it, `gen collect` after `--no-wait`, and `job resume` from the record alone —
> and the money moved exactly once whichever ran. Counting on one route left the other two
> invisible to the ceiling; counting on all three would bill one call three times. The flag
> belongs on the job because the alternative is a running total that has to remember every
> id it ever saw, and the job is the record that already knows.

## R2 · The states

- **R2.1** The `ssc` CLI shall hold each job in exactly one of `submitted`, `running`, `done`, `failed` and `cancelled`.
- **R2.2** When a provider reports a job's state, the `ssc` CLI shall record that state and the moment it was recorded.
- **R2.3** If a state change would move a job out of `done`, `failed` or `cancelled`, then the `ssc` CLI shall refuse it and keep the record it has.

## R3 · The commands

- **R3.1** The `ssc` CLI shall list every job with its state, most recently submitted first.
- **R3.2** When `ssc job status` runs against a job that is not finished, the `ssc` CLI shall ask the provider and record what it says.
- **R3.3** When `ssc job wait` runs, the `ssc` CLI shall keep asking until the job finishes or a given deadline passes, and shall say which of the two happened.
- **R3.4** When `ssc job cancel` runs, the `ssc` CLI shall ask the provider to cancel and shall record the outcome.
- **R3.5** When `ssc job resume` runs, the `ssc` CLI shall collect a finished job's result using only what the record holds.
- **R3.6** If a command names a job that does not exist, then the `ssc` CLI shall exit `2` and say so.
- **R3.7** Where no provider is available for a job's provider name, the `ssc` CLI shall report what it has on disk and say why it could go no further.

## Out of scope

**Submitting anything.** No provider ships here, and nothing in this leaf spends money. The
store is built and tested against a provider interface; `specs/gen-fal/` supplies the first
implementation of it. That order is deliberate — the job is the contract and generation is
one producer of it.

**Deleting old jobs.** `jobs/` accumulates, and a retention policy is a decision about
somebody's disk that nobody has asked for yet. `ssc clean` deliberately does not touch it:
its rule is that it deletes `derived` files, and a job record is neither derived nor an
asset.
