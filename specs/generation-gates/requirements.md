---
autonomy: auto
ci: wait
lang: en
---

# Generation gates — requirements

## Purpose

`ssc run` refuses a step that bills. That was right when it was written — an unattended
chainer submitting paid calls is what `budget-guard` exists to prevent one layer down, and
nothing then described a generating pipeline — and the cost is that an operator types every
`gen` call by hand while `ssc run` covers only the free tail. `adr:0014` reverses it: a step
may bill, with a gate opened *before* the call and a budget reservation behind it. This is
that decision built. It is for the workflow the harness skills were written against — a
chain of paid calls with human judgement between them, where a box art nobody approved is a
concept the rest of the character is wrongly derived from.

## R1 · A step may bill, behind a gate

- **R1.1** Where a pipeline step names a command that bills and declares a gate, the `ssc` CLI shall run that step.
- **R1.2** If a step names a command that bills and declares no gate, then the `ssc` CLI shall refuse before running anything, naming the gate it needs.
- **R1.3** The `ssc` CLI shall open a paid step's gate before the call is submitted, and shall submit nothing while it is pending.
- **R1.4** The `ssc` CLI shall name in that gate the step, the model that would run and what the call is estimated to cost.
- **R1.5** While a paid step's gate is approved, the `ssc` CLI shall submit the call and record what came back.
- **R1.6** If a paid step's gate is rejected, then the `ssc` CLI shall stop with nothing submitted.
- **R1.7** The `ssc` CLI shall record in a paid step's gate which call the question was asked about.
- **R1.8** If the call a paid step now resolves to is not the one its approved gate names, then the `ssc` CLI shall put the question again rather than submit.

## R2 · What a paid step declares

- **R2.1** The `ssc` CLI shall accept, on a paid step, the parameters that decide what is generated and what it costs.
- **R2.2** Where a paid step names a stage to derive from, the `ssc` CLI shall send that stage as a reference to the call.
- **R2.3** If a paid step declares a parameter its command does not take, then the `ssc` CLI shall refuse before running anything.
- **R2.4** The `ssc` CLI shall report a paid step's resolved call before it is submitted, when asked for a dry run.

## R3 · Money

- **R3.1** The `ssc` CLI shall reserve a paid step's estimated cost against the workspace budget exactly as it does for a hand-typed call.
- **R3.2** If the budget refuses the reservation, then the `ssc` CLI shall stop with nothing submitted.

## R4 · Standing approvals

- **R4.1** The `ssc` CLI shall report which topics this workspace has a standing approval for, and which gate each came from.
- **R4.2** Where a topic has a standing approval, the `ssc` CLI shall say so when reporting a gate that inherited it.
- **R4.3** If a standing approval names a gate this workspace does not hold as approved, then the `ssc` CLI shall not let a paid step inherit it.

## Out of scope

**`gen expand` and `gen bgremove` as steps.** Both transform a subject image rather than
generating from a description, which makes their input the previous stage rather than
something the step declares — the shape the free registry already has. Folding them in means
answering which stage is the subject in a chain that may not have produced one yet, and this
leaf has no example that needs it. They stay refused, by the same rule R1.2 states.

**A flag that allows paid steps.** `adr:0014` rejected `ssc run --allow-paid`: it moves the
decision to whoever typed the command and leaves no record. A gate is already this project's
answer to "a human has to decide".

**Judging what came back.** The gate in front of a paid step asks whether to spend. Whether
the result is any good is a separate decision, and it is the gate the *next* step declares.
