# Gates and resume — design

## What changes

Serves R1.1, R2.1, R4.1, R4.2.

- **`cli/gates.py`** — the record, its states, and the defaults file. Modelled directly on
  `cli/jobs.py`: one file per gate, never an index, because the premise is that another
  process may be running while this one reads. Validate-on-read, the same shape.
- **`cli/steps.py`** — the pipeline: what a declared step is, reading `pipeline:` out of
  `ssc.yaml`, and the **registry of runnable commands** — shared with `specs/sweep-and-review/`,
  which sweeps the same registry's parameters.
- **`cli/commands/gate.py`** — `ssc gate list|open|approve|reject`.
- **`cli/commands/run.py`** — `ssc run` and `ssc status`.

## Boundaries and contracts

**Exit `3` means a human decision is outstanding, and only that.** `errors.GatePending`
has existed since `workspace-foundation` with no raiser; this leaf is what raises it. The
split that matters: `run` and `gate open` exit `3` because they *cannot proceed*; `gate
list` and `status` exit `0` because they are queries and they succeeded. A query that
exited `3` for reporting a pending gate would make "I could not tell you" and "I told you,
and the answer is pending" the same value.

**`run` executes only what `steps.py` can run, and that is free by construction.** R4.9's
refusal is not a check bolted on — the registry holds free `tool` commands and nothing
else, so a step naming `gen image` fails R4.8's "cannot be run" first. The named refusal
exists so the message says *why* rather than "unknown command".

## Data

One file per gate, under `gates/` beside `jobs/`:

```
gates/
  <subject>.<topic>.json
  defaults.json
```

A gate carries `schema`, `id`, `subject`, `topic`, `question`, `material` (the path to look
at — a `review/<key>/` from `sweep`, usually), `state`, `choice`, `why`, `inherited_from`
and `history[]`. The id is `<subject>.<topic>`, which is what makes R2.2 a file-existence
question rather than a scan.

`defaults.json` maps a topic to `{choice, from, at}`. It is one file rather than a field on
each gate because a default is a property of the workspace, not of any one gate, and the
gate that established it may later be deleted.

The pipeline, in `ssc.yaml`:

```yaml
pipeline:
  - stage: nobg
    command: bgremove
    params: {tol: 60, mode: flood}
  - stage: pixels
    command: pixelart
    params: {colors: 16}
    gate: does the palette read at 1x?
```

`stage` is the output stage recorded in the asset's `meta.json`, and it is the whole resume
mechanism: R4.2 asks whether the asset already records that stage, which is a question
about disk and needs no run log. A step's `gate:` is the question asked once the step has
produced its output.

Resuming is therefore not state this leaf keeps. `meta.json` already addresses files by
stage rather than by numbered prefix (`workspace-foundation` R2.4, R3.3) — a decision taken
for a different reason, and this is what it buys.

**Where a step's frames land: `frames/<stage>/`.** Every command in the registry takes a
frame set and returns one, so each step produces N files that are one stage. There was no
settled place for that: `tool cut` records the set it produces as the single stage `frames`
with path `frames`, and `workspace-foundation` R2.5 allows exactly one subdirectory inside
an asset. A second top-level directory per stage would break R2.5; nesting under the
directory that requirement already permits does not, and `check_layout` — which inspects the
asset root's subdirectories — is satisfied unchanged. `read_frames` filters by image suffix,
so a `frames/` holding both files and stage directories reads the same as before. This is
recorded as a delta on that spec rather than left implicit, because the next leaf to produce
a set needs to find the answer rather than invent a second one.

## Alternatives considered

**A run log recording where the run got to.** The obvious design, and wrong here: it is a
second record of a fact `meta.json` already holds, and the two disagree the moment somebody
deletes a derived file or `ssc clean` runs. Reading the stages back is slower and cannot go
stale. `routing.md`'s "one source of truth per item", applied to a pipeline.

**A gate as a field on the asset's `meta.json`.** Rejected: `meta.json` records what each
file *is*, and `clean` reads it. A pending decision is neither a file nor derived from one,
and putting it there would make an approval something `clean` could reason about. Same
argument `adr:0005` makes for `jobs/` being outside the asset.

**One gates index instead of a file per gate.** Rejected for `jobs.py`'s reason, restated:
two commands racing on one document is a lost write, and this leaf's entire premise is that
a second process may be running.

## Risks

**R4.2 makes a stage's presence mean "this step is done", and nothing verifies it was done
*by that step*.** An asset with a hand-written `nobg` stage will have that step skipped.
That is the correct behaviour — a stage is the address, and a person who put a file there
meant it — but it means a mis-declared pipeline silently skips work rather than failing, so
`status` reporting per-step state (R4.6) is what makes it visible.
