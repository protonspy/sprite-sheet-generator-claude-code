---
autonomy: auto
ci: wait
---

# Gates and resume — requirements

## Purpose

A gate is a decision reserved for a human, held as state in the workspace rather than asked
in conversation. `ssc gate` is the surface over that state; `ssc run` and `ssc status` are
what read it — a pipeline that stops at the next outstanding decision and, after any session
dies, works out from disk alone where it had got to.

The conversational alternative is what this exists to refuse. An agent that asks "does this
look right?" mid-run has taken a decision nobody can audit, that no second session can find,
and that is lost the moment the context is compacted.

## R1 · The gate record

- **R1.1** The `ssc` CLI shall hold a gate as a record in the workspace naming its subject, its topic, the question being asked, and where the material to look at is.
- **R1.2** The `ssc` CLI shall record a gate as `pending`, `approved` or `rejected`, and shall record each move with the time it happened.
- **R1.3** If a gate has already been decided, then the `ssc` CLI shall refuse to decide it again, reporting the decision it carries.
- **R1.4** If a gate record cannot be read, then the `ssc` CLI shall report it as unreadable and list the rest.

## R2 · Asking and deciding

- **R2.1** When a gate is opened, the `ssc` CLI shall write it as pending and exit `3`.
- **R2.2** If a pending gate already exists for that subject and topic, then the `ssc` CLI shall report the existing gate rather than open a second, and exit `3`.
- **R2.3** The `ssc` CLI shall never read from standard input, and shall report a pending decision only as an exit code and a record.
- **R2.4** When a gate is approved, the `ssc` CLI shall record the decision and, where one was named, which choice was taken.
- **R2.5** When a gate is rejected, the `ssc` CLI shall record the refusal and the reason given.
- **R2.6** The `ssc` CLI shall report every gate with its state when they are listed, and shall exit `0`.

## R3 · An approval as an inheritable default

- **R3.1** Where an approval is marked as a default, the `ssc` CLI shall record that decision as the default for the gate's topic.
- **R3.2** When a gate is opened for a topic that has a recorded default, the `ssc` CLI shall open it already approved, carrying that default's decision and naming where it was inherited from.
- **R3.3** Where a gate was opened against a recorded default, the `ssc` CLI shall not exit `3`.

## R4 · Running a pipeline, and resuming one

- **R4.1** The `ssc` CLI shall execute the steps the workspace declares for an asset, in the order declared.
- **R4.2** The `ssc` CLI shall skip a step whose output stage the asset already records, so a run that is started again continues from disk rather than from the beginning.
- **R4.3** When a step declares a gate, the `ssc` CLI shall open that gate once the step has produced its output, and stop.
- **R4.4** While the gate for a step is approved, the `ssc` CLI shall continue past it.
- **R4.5** While the gate for a step is rejected, the `ssc` CLI shall stop and report the rejection.
- **R4.6** The `ssc` CLI shall report each step as done, blocked or outstanding, and name the step that would run next.
- **R4.7** If the workspace declares no pipeline, then the `ssc` CLI shall refuse to run or report one, naming where a pipeline is declared.
- **R4.8** If a step names a command that cannot be run, then the `ssc` CLI shall refuse before executing any step.
- **R4.9** If a step would bill, then the `ssc` CLI shall refuse, naming the command that performs it.

## Out of scope

**Paid steps.** R4.9 refuses them outright. `run` is unattended by construction — that is the
point of resuming from disk — and an unattended chainer that submits paid calls is what
`specs/budget-guard/` was written to prevent one layer down. A pipeline that generates is a
decision this leaf does not have the material to take: nothing in the plan describes one, and
inventing it here would bind the leaf that eventually does.

**A gate on anything but a step.** Gates are opened by `run` at a declared step, and by hand.
Nothing else opens one.
