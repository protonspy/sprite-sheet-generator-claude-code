---
name: sprite-style
description: One leg of the sprite relay in docs/wiki/pages/agent-workflow.md — own the project's look. Use it after `sprite-cleanup` has handed over frames that pass `doctor`, when the work is to quantize frames against the project's one `palette.json`, apply the workspace's dither decision, and produce colour variants with `tool recolour`; and when a run resumes with clean frames not yet styled. Owns the palette-lock gate, once per project. Not for repairs (`sprite-cleanup`) and not for the engine handover (`sprite-integrate`).
---

You own the fourth leg of the relay: the project's look. Every asset in a
workspace resolves against one `palette.json`, so two assets generated a week
apart agree. A palette is a project decision, not a per-call argument.

## Commands you run

- `tool style` — quantize frames against the project's locked `palette.json`,
  never ad-hoc colours. With no palette locked yet, `--preset pico8|nes|gameboy|
  sweetie16` locks one into `palette.json` and applies it; once locked, the preset
  is refused and the locked palette is applied as-is. The presets ship in
  `src/ssc/data/`. Locking is the gate below — `tool pixelart` is the ad-hoc
  sibling, for loose PNGs with no workspace; it is not the project-locked path.
- `tool recolour` — map one palette onto another, so a red slime and a blue slime
  are one asset and a colour map rather than two generations. This is the free
  path: a colour map answers what a paid `gen` call would otherwise be asked,
  and the budget guard refuses the paid call for it.
- The dither decision — ordered or Floyd-Steinberg — is recorded under ``style:`` in
  ``ssc.yaml`` (e.g. ``style:\n  dither: ordered``), never a per-call argument. Two
  assets generated a week apart agree because the decision was made once, the way the
  palette was.

Run these through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk. A stage you write
without recording it breaks the leg after you, which is the drift
`tests/cli/test_chain.py` exists to catch.

## Your gate — the palette lock

Once per project, inside this skill, the run stops to lock `palette.json`.
Locking it is the decision: every asset after it inherits the choice silently,
so the cheapest moment to reconsider the palette is before anything is quantized
against it. The gate is held as state in the workspace — a pending one is exit
code `3` and a `review/` directory, never a question asked in conversation. You
do not decide at a gate: you surface the palette and stop.

## What you hand over

Frames quantized against the one palette, recorded as a stage in `meta.json` —
found by stage, never by filename. The next skill, `sprite-integrate`, writes
`dist/index.json` and renders the preview a person approves.