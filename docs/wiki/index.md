# ssc — knowledge base

Why AI-generated art is not game-ready, and what has to happen to it before an engine
can read it. The plan that turns this into work is `plans/ssc-pipeline.md`; these pages
hold the reasoning behind it.

## Start here

- [[game-ready-defects]] — the defects this tool exists to measure and repair, and which
  of them `doctor` checks. Every other page assumes this vocabulary.
- [[agent-workflow]] — the runs the skills drive, from an empty asset to
  `dist/index.json`, and the four gates where they stop for a person.

## Producing the art

- [[anchor-and-directions]] — the one image everything else derives from, why it must be
  a neutral pose, and how the other three directions come from it.
- [[reference-boards]] — the checkerboard and the pose board: two images that discipline
  a model, and why they are generated rather than downloaded.
- [[generating-animations]] — pose board for idle and attack, video for walk cycles, and
  why that split is not a preference.
- [[model-parameters]] — what the eight endpoints actually accept, the one model that takes
  a size in pixels, and the three options that earned a name of their own.
- [[prompt-templates]] — the frame a caller's words go into, why one kind is not one
  template, and the eight named slots a template may carry.

## Repairing it

- [[pixel-snapping]] — recovering real pixels from fake ones, and why it happens twice.
- [[frame-normalisation]] — recovering frames, locking the anchor, and repacking.
- [[sprite-normalisation-gate]] — the six-step gate from `tool bounds` through `tool
  preview`, where `doctor`'s `scale` check reads between the leaves, and why it stops being
  one command.

## Handing it over

- [[into-an-engine]] — what `ssc index` writes into `dist/`, where playback is authored, and
  what the Pixi, Phaser and Godot formats can and cannot say.

## Building the tool

- [[workspace-binding]] — why a checked path is not a safe path, what the Windows fallback
  does and does not buy, and the two verification habits four review rounds paid for.

## Context

- [[prior-art]] — what already exists, what was adopted, what was refused and why.
