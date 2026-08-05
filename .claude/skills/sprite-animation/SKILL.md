---
name: sprite-animation
description: One leg of the sprite relay in docs/wiki/pages/agent-workflow.md — own the poses and the cycle. Use it after `sprite-character` has handed over an approved anchor image, when the work is to produce a curated frame set for one animation; and when a run resumes and the next stage after the anchor is a pose sheet or a walk cycle. Not for non-animating kinds (tile, icon, ui), which are `sprite-resource`, and not for the repairs after curation, which are `sprite-cleanup`.
---

You own the second leg of the relay: getting from one anchor image to a curated
frame set per animation. The anchor is settled and approved before you start —
that gate is `sprite-character`'s, not yours.

## Commands you run

- `tool board poses` — lay out an empty grid of cells declaring the frame
  layout the generation step fills. The cell size comes from the kind's profile;
  you do not invent it.
- `gen image` — the paid call that fills a pose sheet. Run it against the kind's
  template, with the anchor as the reference (`--ref` / `--from-stage`). This is
  the step that bills; a wrong anchor wastes it, which is why the anchor gate
  comes first.
- `gen video` — a walk cycle, where the motion is continuous and a video model
  is the right shape. Same reference discipline as `gen image`.
- `tool cut` — take a generated sheet apart into one frame per pose. `--grid`
  matches the board you laid out.
- `tool curate` — report which frames say nothing new, and drop them when asked.
  Curation is a measurement, not a taste call: a frame `curate` flags is a
  duplicate the set can lose.

Run these through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from memory.
A stage you write without recording it breaks the leg after you, which is the
drift `tests/cli/test_chain.py` exists to catch.

## Your gate — the curated frame set

The run stops at the end of this skill. The paid calls have happened by now;
what is being judged is whether the motion reads, which no `doctor` check can
measure. The gate is held as state in the workspace — a pending one is exit code
`3` and a `review/` directory, never a question asked in conversation. You do
not decide at a gate: you surface the curated set and stop.

See `docs/wiki/pages/generating-animations.md` for the neutral-pose discipline and
the cycle conventions, and `docs/wiki/pages/anchor-and-directions.md` for how the
anchor constrains every direction.

## What you hand over

A curated frame set per animation, recorded as a stage in `meta.json` — found by
stage, never by filename. The next skill, `sprite-cleanup`, repairs and measures
those frames.