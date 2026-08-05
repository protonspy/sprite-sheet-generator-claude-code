---
name: sprite-resource
description: One leg of the sprite relay in docs/wiki/pages/agent-workflow.md — own the kinds that do not animate. Use it at the start of a run whose asset is a tile, an icon, or a ui element, when the work is to generate the source against the kind's profile, close a tile's wrap with `tool tile`, or report a panel's stretch guides with `tool ninepatch`; and when a run resumes with a resource source not yet handed to style. Not for anything that animates (`sprite-character` → `sprite-animation`) and not for quantization (`sprite-style`).
---

You own the first leg of the relay for the kinds that do not animate: tile,
icon, and ui. These have no anchor-per-direction and no cycle, so they take a
shorter path — source, then style, then integrate — and skip the gates that
exist only for motion.

## Commands you run

- `asset new <key> --kind <tile|icon|ui>` — create the asset. The kind's profile
  carries the dimensions and constraints; you do not invent them.
- `gen image` — the paid call that produces the source, run against the kind's
  template. This is the one billable step on this path.
- `tool tile` — close a tile's wrap so it meets itself on every side. Run it for
  `tile` assets before any style pass; a tile that does not wrap is a tile that
  shows seams.
- `tool ninepatch` — report the guides an engine stretches a `ui` panel by. Run
  it for `ui` assets that scale; the guides are the contract the engine reads.
- `tool bgremove` — strip the background where the source has one, the same free
  chroma-key path as `sprite-character`.

Run these through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory. A stage you write without recording it breaks the leg after you, which
is the drift `tests/cli/test_chain.py` exists to catch.

## Your gate — none

The relay's four gates (anchor, curated frame set, palette lock, preview) are
for motion and for the look; none of them is on this path. A resource does not
stop for approval here — it flows through to `sprite-style`'s palette lock and
`sprite-integrate`'s preview, which is where a person sees it. The source stands
in for the anchor in the sense that everything later derives from it, so a wrong
source wastes the same way a wrong anchor does; the difference is there is no
gate held as state for it.

## What you hand over

Approved sources, recorded as a stage in `meta.json` — found by stage, never by
filename — ready for the next skill, `sprite-style`, to quantize against the
project's one palette.