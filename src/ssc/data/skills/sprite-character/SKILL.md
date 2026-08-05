---
name: sprite-character
description: One leg of the sprite relay in docs/wiki/pages/agent-workflow.md — own the anchor image everything derives from. Use it at the start of a run whose asset animates (a character, a creature, anything with directions and cycles), when the work is to generate the one anchor image against the kind's template, strip its background, and record it; and when a run resumes with no anchor staged yet. Owns the anchor-image gate. Not for non-animating kinds (`sprite-resource`) and not for poses or cycles (`sprite-animation`).
---

You own the first leg of the relay: the one anchor image every direction and
every animation of a character derives from. A wrong anchor is every later paid
call wasted, so the cheapest moment to reject it is before anything derives
from it — that gate is yours.

## Commands you run

- `asset new <key> --kind character` — create the asset of the right kind. The
  kind's profile carries the cell size, frame counts and fps; you do not invent
  them.
- `gen image` — the paid call that produces the anchor, run against the kind's
  template. This is the step that bills, and it is the step a wrong anchor
  wastes, which is why the gate below comes before `sprite-animation`.
- `tool bgremove` — strip the background. The free, deterministic path is the
  chroma-key `tool bgremove`; the model-backed `--model` path under the `[cv]`
  extra is there when the background is not a clean chroma. Prefer the free one
  when it works.
- Record the anchor as a stage in `meta.json`. The neutral-pose discipline of
  `docs/wiki/pages/anchor-and-directions.md` is the rule: the anchor is the one
  frame every direction derives from, and its recorded value is what `tool align`
  later locks the cycle to.

Run these through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the leg after you, which
is the drift `tests/cli/test_chain.py` exists to catch.

## Your gate — the anchor image

The run stops at the end of this skill. Every direction and every animation
derives from this one image, so a wrong one is every later paid call wasted. The
gate is held as state in the workspace — a pending one is exit code `3` and a
`review/` directory, never a question asked in conversation. You do not decide
at a gate: you surface the anchor and stop.

## What you hand over

One approved anchor image, keyed and recorded as a stage in `meta.json` — found
by stage, never by filename. The next skill, `sprite-animation`, generates poses
and cycles from it.