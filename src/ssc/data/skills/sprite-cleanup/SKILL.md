---
name: sprite-cleanup
description: One leg of the sprite relay in docs/wiki/pages/agent-workflow.md — own the repairs that make frames clean. Use it after `sprite-animation` has handed over a curated frame set, when the work is to snap frames to the pixel grid, align them to the anchor, and measure the result with `doctor`; and when a run resumes with frames staged but not yet measured. Not for generation or curation (`sprite-animation`) and not for quantization against a palette (`sprite-style`).
---

You own the third leg of the relay: the repairs that turn a curated frame set into
frames a style pass can quantize and an engine can load. Everything you do is a
measurement, not a taste call — you act on what `doctor` reports.

## Commands you run

- `tool snap` — recover the real pixel grid from art that only looks like pixel
  art. Run it when the frames came in at a scale that smeared the grid.
- `tool align` — lock every frame of a set to one anchor, so a sprite does not
  jitter between frames. The anchor is `sprite-character`'s recorded value; you
  do not pick a new one.
- `tool doctor` — measure the frames and report defects: pixel grid, flicker,
  and the rest of the `docs/wiki/pages/game-ready-defects.md` set. A defect is a
  measurement, not a failure: each names its fix, and you apply the fix it names.

Run these through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk. A stage you write
without recording it breaks the leg after you, which is the drift
`tests/cli/test_chain.py` exists to catch.

## Your gate — none

Cleanup runs to a measurement, not a decision. You stop only when `doctor` is
clean, or when you hit a defect you cannot repair — and that is not a gate, it
is a hand-back: name the defect and the fix you tried, and stop. The four gates
the relay stops at (anchor, curated frame set, palette lock, preview) are
elsewhere; none of them is yours. See `docs/wiki/pages/frame-normalisation.md`
for the repair sequence and why each step is deterministic.

## What you hand over

Frames that pass `doctor`, recorded as a stage in `meta.json` — found by stage,
never by filename. The next skill, `sprite-style`, quantizes those frames against
the project's one palette. If a defect could not be repaired, hand over the
named defect instead, so the run stops on a person rather than silently
carrying a broken frame into the palette lock.