---
name: sprite-integrate
description: The last leg of the sprite relay in docs/wiki/pages/agent-workflow.md — own the engine handover. Use it after `sprite-style` has handed over frames quantized against the palette, when the work is to write `dist/index.json` with `ssc index` and render the preview with `ssc preview`; and when a run resumes with styled frames not yet indexed. Ends the run at `dist/index.json`. Owns the preview gate. Not for styling (`sprite-style`) and not for any earlier leg.
---

You own the last leg of the relay: the handover to an engine. Everything before
this produced frames; you produce the one file an engine reads and the preview a
person approves. The run ends here, at `dist/index.json`.

## Commands you run

- `ssc index` — write `dist/index.json`. One index covers every kind: sheets
  with cell, grid, fps, loop and the anchor that stops an engine re-centering the
  sprite; atlases with a rect per entry; tilesets with tile size and ids; and
  nine-slice borders for `ui`. Playback is `loop`, `ping-pong` or `reverse`, and
  one sheet may declare named sections. Authored intent — playback, sections,
  markers, hitboxes and hurtboxes — travels in the sidecar; the index reads both
  the stages and the sidecar.
- `ssc preview <address>` — render what the index declares: a GIF of the
  animation, a labelled contact sheet, or a 2×2 tile preview. `--section`
  renders one named section. The preview resolves playback out of the index
  rather than growing a second renderer, so what a person approves is exactly
  what an engine will load.

The index reads stages by name from `meta.json`, never by filename — a stage
some earlier skill wrote without recording it breaks here, which is the drift
`tests/cli/test_chain.py` exists to catch. See `docs/wiki/pages/into-an-engine.md`
for the contract `dist/index.json` carries and why it is versioned.

## Your gate — the preview

The run stops at the end of this skill. `ssc preview` renders from `dist/`, so
what is being approved is exactly what an engine will load — the cheapest
moment to catch a sheet that looks wrong is after the index that produces it
exists. The gate is held as state in the workspace — a pending one is exit code
`3` and a `review/` directory, never a question asked in conversation. You do
not decide at a gate: you surface the preview and stop.

## What you hand over

`dist/index.json`, and the preview a person approves. This is the end of the
relay — there is no next skill.