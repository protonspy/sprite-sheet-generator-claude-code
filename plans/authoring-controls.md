---
autonomy: auto
ci: wait
lang: en
pr: per-group
worktree: per-group
---

# Authoring controls

Six leaves giving an author — and the harness that runs on their behalf — control over
what a generation looks like, what it derives from, and where the result is cut. The
through-line is that a paid call stops being a fixed pixel-art prompt and becomes a
decision somebody made, recorded and approved before the money is spent.

## Why

`ssc` today generates one look and only one: pixel art is written into every prompt
template in `src/ssc/data/templates.json`, so a project that wants hand-painted or vector
art has no surface to ask for it. The generation step accepts a single reference image and
nothing states what happens when there is none. And the pipeline that chains all of this
refuses paid steps outright — `specs/gates-and-resume/` R4.9 — because when that leaf was
written nothing described a generating pipeline, and its Out of scope says so explicitly:
the decision "was not one this leaf had the material to take". This plan is that material.
Done is when the harness picks a style rather than inheriting one, a generation can be
anchored to references the caller supplies, an unreferenced generation produces a concept
piece a human approves before anything derives from it, and `ssc run` can carry a paid step
because a gate and a budget stand in front of it. `ssc tool crop` rides along: it is the
framing primitive the local half has been missing next to `trim`, `expand` and `offset`.

## Paths

- `src/ssc/core/crop.py`, `src/ssc/cli/commands/crop.py` — the framing command
- `src/ssc/cli/gen.py`, `src/ssc/cli/commands/gen.py` — style, references, box art
- `src/ssc/data/templates.json`, `src/ssc/data/styles.json` — the prompt surface
- `src/ssc/cli/gates.py`, `src/ssc/cli/steps.py`, `src/ssc/cli/commands/run.py` — the gates
- `src/ssc/cli/commands/video.py`, `src/ssc/core/` — taking a clip apart into frames
- `src/ssc/data/skills/` — the shipped harness skills that pick a style and read a gate
- `docs/glossary.md`, `docs/adr/` — numbering continues at `0014`
- `tests/core/`, `tests/cli/`, `tests/fixtures/`

## References

- `specs/frame-cropping/` — `ssc tool crop`: an explicit box, an aspect ratio with a
  gravity, and an inset, over one image or a directory of frames. One box shared by every
  frame or a box computed per frame, because the first preserves alignment and the second
  destroys it. The local half of what `gen expand` does remotely, and the inverse of
  `tool expand`.
- `specs/generation-style/` — `gen image --style`, taking a name from a shipped set
  (`pixel-art`, `vector`, `hand-painted`, `3d-render`, `flat`) or free text passed through
  to the model. The kind profile carries the default and the harness overrides it per call.
  The prompt templates stop baking pixel art into every generation, which is what makes
  every other look reachable at all. A style is not only words: `pixel-art` is words plus
  the checkerboard `tool board checker` already generates, and a style that carries an
  attachment is why this leaf and the next are one plan.
- `specs/reference-images/` — more than one reference on `gen image`. The payload already
  models an array (`src/ssc/cli/gen.py` around the image-field placeholder); the CLI takes
  one path and one `--from-stage`. Covers what a model that accepts a single image does
  when several are given, and what each reference is *for* — identity, palette, pose. Two
  references at once is the ordinary case, not the exotic one: an anchor image and a
  checkerboard is how every direction after the first is generated. Also covers where a
  reference must not go — a board sent to a video model is merged into the subject.
- `specs/box-art/` — the concept piece. When a generation has no reference, `ssc` produces
  an approval image first, in concept-art fidelity and never in pixel art, and the pixel art
  is derived from it afterwards by `tool pixelart`. When a reference *is* supplied, this
  step does not happen.
- `specs/generation-gates/` — a gate in front of a paid step, which is the delta
  `specs/gates-and-resume/` R4.9 has been waiting for: what `ssc run` may bill, what it must
  ask first, and how that composes with the reservation `specs/budget-guard/` already takes.
  Carries the box-art approval gate as its first subject.
- `specs/clip-sampling/` — turning a generated clip into a frame set. `gen video` submits
  the call and `ssc video` lists what came back, but nothing takes a clip apart: a walk cycle
  arrives as four seconds and eighty to a hundred and twenty frames, and a sheet needs eight
  to twelve spanning exactly one cycle. Covers frame extraction, finding where a cycle closes,
  and sampling across it — the one part of the reference workflow with no surface at all.

## Out of scope

- **A second generation provider.** `specs/gen-fal/` remains the only paid path; a style
  name resolves against the models already in the registry.
- **Judging whether a style came out right.** `doctor` measures defects against a kind's
  checks. "Does this read as hand-painted" is a gate, which is the whole reason box art is
  one.
- **Retiring `tool style`.** It keeps its meaning — quantizing a frame set against
  `palette.json` — and `--style` on `gen image` is a second, deliberately overlapping name
  that `docs/glossary.md` disambiguates by scope. Recorded as such rather than renamed.
- **Interactive cropping.** `tool crop` takes numbers. Choosing them by eye is a person
  with an image viewer, or a `sweep`.
- **Reopening M1 through M3 of `plans/ssc-completion.md`**, except as a delta a leaf here
  forces — `gen-fal`, `gates-and-resume` and `budget-guard` each owe one.

## Tasks

- [x] 1.1 (Unit) Settle the vocabulary this plan introduces in docs/glossary.md — style,
      box art, reference image, paid step — and record style as scoped rather than
      unique
- [x] 1.2 (Unit) Record an ADR for a pipeline step that bills, naming what stands in
      front of the money
  _Depends 1.1_
- [x] 1.3 (Unit) Add a wiki page for box art and the style axis, and record in
      generating-animations why box art is not passed as a reference to the anchor

## Done when

- `ssc tool crop` cuts by box, by aspect with a gravity, and by inset, over an image or a
  frame set, with the shared-box and per-frame choice explicit on the command line
- `ssc gen image --style` reaches every shipped style name and arbitrary free text, and no
  prompt template names pixel art unless the style asked for it
- `ssc gen image` accepts more than one reference, and reports what it did with them against
  a model that takes only one
- A generation with no reference stops at a box-art gate, and the pixel art that follows is
  derived from the approved image rather than generated again
- `ssc run` carries a paid step only behind a gate and a budget reservation, and
  `specs/gates-and-resume/` carries the delta that says so
- A generated clip becomes a frame set of a stated size spanning one cycle, and that set
  goes through `tool normalise` and `tool pack` like any other
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` and `npx @protonspy/scc validate` all
  exit `0`, and every task above is ticked
