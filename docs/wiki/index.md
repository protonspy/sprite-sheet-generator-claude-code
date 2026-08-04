# ssc — knowledge base

Why AI-generated art is not game-ready, and what has to happen to it before an engine
can read it. The plan that turns this into work is `plans/ssc-pipeline.md`; these pages
hold the reasoning behind it.

## Start here

- [[game-ready-defects]] — the defects this tool exists to measure and repair, and which
  of them `doctor` checks. Every other page assumes this vocabulary.

## Producing the art

- [[anchor-and-directions]] — the one image everything else derives from, why it must be
  a neutral pose, and how the other three directions come from it.
- [[reference-boards]] — the checkerboard and the pose board: two images that discipline
  a model, and why they are generated rather than downloaded.
- [[generating-animations]] — pose board for idle and attack, video for walk cycles, and
  why that split is not a preference.
- [[model-parameters]] — what the four named models actually accept, why none of them
  takes a size in pixels, and what that costs the layout.
- [[prompt-templates]] — the frame a caller's words go into, why one kind is not one
  template, and the eight named slots a template may carry.

## Repairing it

- [[pixel-snapping]] — recovering real pixels from fake ones, and why it happens twice.
- [[frame-normalisation]] — recovering frames, locking the anchor, and repacking.

## Handing it over

- [[into-an-engine]] — what `ssc index` writes into `dist/`, where playback is authored, and
  what the Pixi, Phaser and Godot formats can and cannot say.

## Context

- [[prior-art]] — what already exists, what was adopted, what was refused and why.
