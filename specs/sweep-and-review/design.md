# Sweep and review — design

## What changes

Serves R1.1, R1.5, R2.1, R4.1.

Three new modules, and one extraction from an existing one.

- **`core/contact.py`** — pure. Given a list of `ndarray | None` and a label per cell, it
  lays them out on one canvas and returns an `ndarray`. Serves R3.1–R3.5.
- **`cli/sweep.py`** — the parameter grammar (R1.3), the cross product (R1.2) and the
  ceiling (R1.4).
- **`cli/steps.py`** — the **registry of runnable commands** (R1.5, R1.6, R1.7): per
  command, the parameters it takes, how each is parsed and the bound it is checked against.
  It lives here rather than in `sweep.py` because `specs/gates-and-resume/`'s `ssc run`
  executes the same registry — a sweep varies a step's parameters and a pipeline runs one
  with parameters fixed, and those are two readings of one table. Two tables would let the
  parameter you swept stop being the parameter the pipeline runs.
- **`cli/commands/sweep.py`** — `ssc tool sweep`: reads the input, walks the variants,
  measures each with `doctor`, writes the review directory (R4.1–R4.5).
- **`cli/commands/convert.py`** — the per-frame work inside `pixelart` and `bgremove` is
  lifted into two module-level functions that both the command and the registry call.

The extraction is the load-bearing part. A registry that reimplemented "what `bgremove`
does to a frame" would be a second implementation of an already-shipped command, free to
drift from it — and a sweep whose variants do not match what the command would produce is
worse than no sweep, because the whole point is to choose a parameter you will then pass to
that command. One implementation, two callers.

## Boundaries and contracts

**`sweep` is under `tool`, so it is free and needs no workspace** (workspace-foundation
R1.6). It takes `--in`/`--out` like every other `tool` command. R4.2's `review/<key>/`
default is what happens *when a workspace is there and a key was named* — an extra
convenience over the general form, never a requirement for one.

That is also the seam to `specs/gates-and-resume/`: the gate reads a review directory and
does not care how it was produced. `sweep` imports nothing from the gate, and the gate
imports nothing from `sweep`. Their coupling is the directory layout below, which is why
the two leaves ship in one PR and not one module.

## Data

The review directory:

```
review/<key>/
  sweep.json          the report — command, input, range, and every variant
  contact.png         one image, every variant, labelled
  variants/
    00_tol-40/…       whatever the command wrote, under a directory named for the point
    01_tol-60/…
```

`sweep.json` carries `schema`, `command`, `input`, `parameters`, `ceiling`, `fewest_defects`
and `variants[]`; each variant carries `index`, `name`, `parameters`, `path`, `status`
(`ok` or `failed`), `reason` where it failed, and the whole `doctor` report where it did
not. The `doctor` report is embedded rather than pointed at: a review directory that has
been zipped and sent to somebody is the case this serves, and a report split across files
is one that arrives half-missing.

A variant's directory name is `<index>_<parameter>-<value>`, index first so an `ls` sorts
the way the sweep ran. The index is what makes it unique — two points of a float range can
round to the same label, and a name that collides silently overwrites a variant.

## Alternatives considered

**Shelling out to `ssc tool bgremove` per variant, instead of the registry.** It would have
kept one implementation with no extraction, and it is what a shell script would do. Rejected
on two counts: it makes the sweep's cost a process spawn per variant, where a 24-point
sweep re-imports numpy and Pillow 24 times; and it puts the CLI's argument parsing in the
middle of a loop that has already parsed those arguments, so a refusal from a variant
arrives as a parsed-back JSON error rather than as the `SscError` it was. The registry
costs an extraction and buys direct calls into `core`.

**A `--vary` per parameter against one combined `--range` string.** Repeatable `--vary
name=values` won: it is the shape `--opt key=value` already established in
`specs/model-registry/`, and a combined string would need its own separator hierarchy for
something that is a list of pairs.

**Ranking the variants by defect count and writing the winner back.** Refused, and R2.3 is
the narrowed form. `doctor` is a set of measurements and its defect count is not a quality
score — a `bgremove --tol 255` that keys the entire frame reports no halo, no bleed and no
palette defect, because there is nothing left to be wrong. Sorting on that number and
acting on the result would automate exactly the judgement the review directory exists to
put in front of a person.

## Risks

**The contact sheet is the artefact a person actually looks at, and it is the one part with
no measurement behind it.** If the layout is wrong — cells misaligned, a label over the
art, a variant silently missing — the sweep is still green and the human decision is taken
on a bad picture. That is why R3.3 forbids resampling (a scaled contact sheet hides the
sub-pixel differences the sweep exists to reveal, and would need `core.resize`, which is
the invariant this project guards hardest) and why the layout task is TDD.
