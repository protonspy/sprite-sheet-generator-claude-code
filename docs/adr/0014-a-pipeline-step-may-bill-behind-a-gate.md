---
status: accepted
---

# 0014 · A pipeline step may bill, behind a gate and a reservation

## Context

`specs/gates-and-resume/` R4.9 refuses outright: if a step would bill, `ssc run` refuses
before executing anything. That was the right call when it was written, and the spec says
why in its own Out of scope — a chainer that submits paid calls unattended is the failure
`specs/budget-guard/` exists to prevent one layer down, and nothing then described a
generating pipeline, so inventing one would have bound a leaf that did not yet exist.

`plans/authoring-controls.md` is that leaf arriving. The workflow it serves is a chain of
paid calls with human judgement between them: a box art nobody approved is a concept the
rest of the character is wrongly derived from, and an anchor image nobody approved is
every later paid call wasted. Keeping R4.9 as an absolute refusal means the operator types
every `gen` call by hand and `ssc run` covers only the free tail of the pipeline — which is
the part that needed a chainer least.

The alternative considered was a flag: `ssc run --allow-paid`. It was rejected because it
moves the decision to whoever typed the command and leaves no record of it. A gate is
already this project's answer to "a human has to decide" — held as state in the workspace,
auditable, and readable by a session that did not open it — and a flag would be a second
answer to the same question.

## Decision

A step may bill. R4.9 changes from a refusal to a condition, and two things stand in front
of the money, both of which already exist:

1. **A gate**, opened before the call is submitted and not after it. Every other gate in
   `ssc` is opened once a step has produced its output; a paid step is the one case where
   that is too late, because the output is what costs. The gate names the step, the model
   and the estimated price.
2. **A reservation** against the workspace budget, taken by `specs/budget-guard/` exactly
   as it is for a hand-typed `gen` call. The gate governs whether a human wants it; the
   budget governs whether the workspace can afford it. Neither substitutes for the other.

An approval may be adopted for the topic, which is the existing R3 mechanism: a project
that has decided it trusts unattended generation of, say, direction frames records that
once rather than answering the same question per asset.

## Consequences

`ssc run` becomes able to carry a character from an approved anchor image to a packed sheet
without an operator between the steps, which is what the harness skills were written
against.

R4.9 is superseded by a delta in `specs/gates-and-resume/`, not by an edit to this record.
The refusal it states is still correct for a workspace that declares no gate on a paid step:
the condition is the gate's presence, so a pipeline that names a paid step and no gate is
refused for the same reason as before.

The blast radius of a mistake goes up. A rejected gate now costs nothing, but an approved
default on a topic that generates is a standing authorisation to spend, and it is recorded
in one place a person has to go and look at. `ssc gate list` is that place, and
`specs/generation-gates/` owes it a way to see which approvals are standing.

Nothing here lets a paid step run without a record. `specs/job-store/` already writes a job
file before a call is considered made, and `adr:0005-a-job-always-exists` is the rule that
survives this change unaltered.
