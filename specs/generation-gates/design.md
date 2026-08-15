# Generation gates — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R2.1, R2.2, R2.3, R2.4, R3.1, R3.2, R4.1, R4.2.

`src/ssc/cli/steps.py` grows a second registry beside the free one. `Paid` is to a `gen`
verb what `Runnable` is to a `tool` command: a name, the parameters it takes with a reader
each, and how to turn them into a `gen.Ask`. Two tables rather than one, because what they
hold is not the same shape — a `Runnable` takes frames and returns frames, and a paid step
takes a description and returns a bill — and the module's own docstring is amended to say
so, since it currently states that everything in it is free.

`declared` stops refusing a paid command outright. It refuses one that declares no gate
(R1.2), with the same code and a fix naming the gate, and reads the params through the paid
registry where it does declare one (R2.3).

`src/ssc/cli/commands/run.py` grows one branch. **For a free step the gate opens after the
work; for a paid step it opens before.** That inversion is the whole leaf, and `adr:0014`
argues it: every other gate asks about output that exists, and a paid step's output is the
thing that costs. So the loop builds the call without submitting it — `gen.build` touches no
network, which is what makes `--dry-run` possible and is what makes this possible too —
opens the gate carrying the model and `budget.estimate_for`'s number (R1.4), and stops. The
next `ssc run` finds the gate approved and submits.

`ssc gate list` reports the standing approvals beside the gates (R4.1). The ADR asks for it
by name: an approved default on a topic that generates is a standing authorisation to spend,
and it has to be visible in one place a person goes and looks at.

## Boundaries and contracts

A paid step goes through `gen.run`, which is the same path a hand-typed call takes: the same
job record before submission, the same reservation, the same cache, the same `source` file
in the asset. Nothing here re-implements any of it, so R3.1 and R3.2 are inherited rather
than built — `budget.reserve` raises to refuse, and the run stops with nothing submitted.

The recorded stage is the step's own `stage:`, so a paid step chains like every other: the
step after it reads what it produced.

The requirement in `specs/gates-and-resume/` that refuses a paid step is folded in the same
branch, from a refusal into a condition. Its text stays true for the case it still covers.

## Data

A paid step declares its call in `params:`, a flat map like every other step:

```yaml
- stage: anchor
  command: gen image
  gate: does this read as the character?
  params:
    prompt: a frost warden in rime-blue plate
    board: true
    quality: high
    var.name: Kael
```

`var.<name>` is how a template variable travels in a flat map. The prefix is a namespace
rather than a new syntax: `gen.parse_variables` still decides what a variable may be called,
so the closed vocabulary is not restated here.

## Alternatives considered

**Running the paid step and gating the result.** Rejected, and this is the decision the
whole leaf turns on: the money is spent by the time that gate opens, which is the one thing
a gate in front of a paid call exists to prevent. A gate on the *result* is a legitimate and
different thing — it is what the next step declares.

**One registry with a `paid` flag.** Rejected: the two entries share a name and nothing else
— different parameters, different return, different execution path — and a table whose rows
mean two things is read wrongly by the third person to touch it.

## What an approval is bound to

**A gate records the call it was shown** — `Gate.authorises`, holding `Call.key()`, which is
already the digest of the resolved call, its images and its model. The next run rebuilds the
call from `ssc.yaml` and compares; a mismatch puts the question again instead of submitting.
Without that, an approval is bound to nothing but the asset and the stage, and `ssc.yaml` is
re-read every run: between `gate approve` and the next `ssc run` the model, the prompt or
`count` can change — by a pull, by a shared workspace, by anything — and the call goes out
under a signature given for something else. This is the one place in `ssc` where a
time-of-check gap costs money rather than an error message.

That field is why `gates.SCHEMA` goes to 2. Reading stays tolerant of 1: a record written
before the field existed is still a true record of a decision, it simply authorises nothing,
and only a paid step asks the question. Refusing them would make every gate in every existing
workspace unreadable to buy nothing.

**A standing approval is checked back to its origin.** `adr:0014` allows a topic to be
adopted, and this narrows *where the adoption may come from*: `defaults.json` is a file in
the workspace like any other, so one arriving with a cloned repository would be a standing
authorisation to spend that nobody here ever gave. The gate it names has to be present and
approved, which is a fact about this workspace rather than about a file somebody shipped.

## Risks

**A pipeline that generates can spend a workspace's budget while nobody is watching, once a
topic has a standing approval.** That is the blast radius `adr:0014` names, and it is
deliberate rather than overlooked: the mitigation is that the authorisation is recorded in
one place and R4.1 makes that place readable. What this leaf must not do is make it
invisible, and the reporting requirement is there for that reason rather than for symmetry.
