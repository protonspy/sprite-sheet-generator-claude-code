---
autonomy: auto
ci: wait
pr: per-group
worktree: per-group
merge: manual
status: draft
lang: en
---

# ssc — harness, style and vision

Nine leaves in three milestones, taking `ssc` from a set of primitives an operator drives by hand to a pipeline an agent runs end to end. Each leaf is deliverable on its own; together they close the distance between a finished asset and a running game.

## Why

The deterministic core, every asset kind and the paid generation path are built and closed — `plans/archive/ssc-pipeline.md` is that record. What is missing is everything on either side of a finished asset. Nothing is emitted that an engine reads, so the last step is still a human transcribing numbers. No harness skill exists, so a person types every command in the chain. A palette is a per-command argument rather than a project decision, so two assets generated a week apart drift apart, and a colour variant costs a paid call that a colour map would have made free. And every model-backed command the roadmap names is unimplemented, with no answer yet for where inference runs. Done is when an agent starts from a base image and finishes at `dist/index.json`, stopping only at the human gates.

## Paths

- `src/ssc/core/` — one module per leaf's implementation
- `src/ssc/cli/commands/` — one module per command
- `src/ssc/data/` — shipped kind profiles, palette presets, model registry fallback
- `.claude/skills/` — the six harness skills
- `tests/core/`, `tests/cli/`, `tests/fixtures/`
- `docs/adr/` — numbering continues at `0009`

## References

### M4 — the harness · what an agent and an engine read

- `specs/engine-index/` — `ssc index --format pixi|phaser|godot|generic`, one
  `dist/index.json` covering every kind: sheets with cell, grid, fps, loop and the anchor
  that stops an engine re-centering the sprite; atlases with a rect per entry; tilesets
  with tile size and ids; nine-slice borders for `ui`. Playback is `loop`, `ping-pong` or
  `reverse`, and one sheet may declare **named sections** — an attack's windup, hit and
  recovery are three ranges of one animation, not three sheets. Plus `ssc preview`, which
  renders a GIF or a contact sheet from what the index declares, and a 2×2 tiled preview
  for `tile` assets.
- `specs/frame-metadata/` — per-frame boxes and markers: an alpha bounding box `ssc`
  derives for free, hit and hurt boxes authored in a sidecar, and named markers on a frame
  (footstep, spawn, cancel window). Validated against the frame count so a curated frame
  cannot silently shift them, and emitted into the index. `ssc` carries these values; it
  never invents damage or knockback.
- `specs/sprite-skills/` — the six harness skills: `sprite-cleanup`, `sprite-animation`,
  `sprite-style`, `sprite-character`, `sprite-resource`, `sprite-integrate`.

### M5 — style and derivation

- `specs/style-and-palette/` — `ssc tool style`, the project-locked `palette.json`, named
  presets (pico8, nes, gameboy, sweetie16), ordered or Floyd-Steinberg dithering as a
  project decision, and palette coherence across every asset. Plus `ssc tool recolour`,
  mapping one palette onto another: a red slime and a blue slime are one asset and a colour
  map, not two generations. Same economics as `mirror`, so it belongs in the free path
  `budget-guard` refuses against.
- `specs/asset-derivation/` — `ssc asset new <key> --extends <parent>` and the
  `<asset>.yaml` behind it: it inherits the recipe (kind, pixel_size, palette, cell, frame
  counts, fps, the parent's anchors as a generation reference), never the pixels.
- `specs/image-transforms/` — mirror about either axis, rotation by a quarter turn, `trim`
  to one box across a frame set, and `offset` by a whole number of pixels, each moving the
  recorded anchor with the pixels. Already specified: eight tasks ready, nothing implemented.

### M6 — computer vision · the `[cv]` extra

- `specs/cv-runtime/` — where inference runs: `--device auto|cpu|cuda|directml|coreml`, the
  `[cv]` and `[cv-gpu]` extras that install the matching `onnxruntime` build, and the
  execution provider folded into the cache key. `auto` picks the best available; a device
  named explicitly fails loudly rather than falling back. **Hardware detection is
  independent of the installed runtime**: `ssc info` reports the GPUs present and the
  providers usable, and a capable GPU under a CPU-only install returns the gap as a
  structured hint carrying the exact install command.
- `specs/cv-background-removal/` — `ssc tool bgremove --model birefnet|rembg` under the
  `[cv]` extra, degrading cleanly with an actionable message when the extra is absent.
- `specs/cv-motion-consistency/` — pose tracking through an animation cycle and a
  consistency embedding across frames.

## Out of scope

- `specs/frame-bounds/`, `specs/set-normalisation/`, `specs/frame-preview/` —
  `plans/sprite-normalisation-gate.md` owns those three. `engine-index` owes `frame-preview`
  a delta so `ssc preview` resolves playback out of the index rather than growing a second
  renderer; that delta is written there.
- M1 through M3. Shipped, closed, and reopened only as a delta a leaf here forces.
- A second generation provider. `gen-fal` is the only paid path in this plan.
- An engine plugin or runtime library. `ssc` emits data an engine reads; it ships no
  importer for one.
- Training, fine-tuning or hosting a model. M6 runs inference on weights it downloads.

## Tasks

- [ ] 1.1 (Unit) Settle in `docs/glossary.md` the vocabulary the nine leaves inherit —
      section, playback, marker, hitbox, hurtbox, preset, dither, recolour, device,
      execution provider — and the synonyms each one displaces
- [ ] 1.2 (Unit) Record as an ADR that `dist/index.json` is a versioned contract with one
      internal model behind per-engine emitters, since an engine reading it makes the shape
      expensive to change and three leaves write into it
- [ ] 1.3 (Unit) Record as an ADR the `[cv]` and `[cv-gpu]` packaging split — which
      `onnxruntime` build each installs, why detection is independent of the installed
      runtime, and that the execution provider is part of the cache key
- [ ] 1.4 (Unit) Distil into `docs/wiki/pages/` what the workspace-binding rounds cost —
      a platform-conditional hardening needs the other platform run before the PR, and a
      guard that cannot work has to refuse rather than report success — and clear the three
      `wiki.changelog-desync` findings standing in `docs/wiki/changelog.md`
- [ ] 2.1 (Unit) Prove the chain end to end on a fixture: base image, poses, pixel art,
      sheet, `doctor`, `dist/index.json` — one test that goes red when any leaf's contract
      drifts, which is the failure no leaf's own suite can see
- [ ] 2.2 (Unit) Write the agent workflow the six skills drive as a `docs/wiki/pages/` page
      reachable from `index.md`, naming which skill owns which step and where each gate falls
      _Depends 2.1_

## Done when

- `ssc index --format pixi|phaser|godot|generic` writes `dist/index.json`, and `ssc preview`
  renders a GIF or a contact sheet from what that file declares
- Every asset in a workspace resolves against one `palette.json`, and `ssc tool recolour`
  produces a variant with no paid call
- `ssc info` reports the GPUs present and the providers usable, and installing the `[cv]`
  extra is the only step between a CPU box and a model-backed `bgremove`
- The six harness skills carry a run from a base image to the index, stopping only at gates
- `scc validate` exits 0, and every spec this plan references reports all tasks done
