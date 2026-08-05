---
autonomy: auto
ci: wait
pr: per-group
worktree: per-group
merge: auto
status: approved
lang: en
checksum: c41b745add210c46b4cd1f2f15fb03eb67cc860760f555f0ab3c175df564e92c
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

- `specs/engine-index/` — shipped, all tasks done: `ssc index --format
  pixi|phaser|godot|generic`, one `dist/index.json` covering every kind: sheets with cell,
  grid, fps, loop and the anchor that stops an engine re-centering the sprite; atlases with
  a rect per entry; tilesets with tile size and ids; nine-slice borders for `ui`. Playback
  is `loop`, `ping-pong` or `reverse`, and one sheet may declare **named sections** — an
  attack's windup, hit and recovery are three ranges of one animation, not three sheets.
  Plus `ssc preview`, which renders a GIF or a contact sheet from what the index declares,
  and a 2×2 tiled preview for `tile` assets. Every other leaf below is a task group here,
  not a spec of its own.

## Out of scope

- Bounds, cross-set normalisation and `tool preview` —
  `plans/sprite-normalisation-gate.md` owns those three. `engine-index` owes the preview
  leaf a delta so `ssc preview` resolves playback out of the index rather than growing a
  second renderer; that delta is written there.
- M1 through M3. Shipped, closed, and reopened only as a delta a leaf here forces.
- A second generation provider. `gen-fal` is the only paid path in this plan.
- An engine plugin or runtime library. `ssc` emits data an engine reads; it ships no
  importer for one.
- Training, fine-tuning or hosting a model. M6 runs inference on weights it downloads.

## Tasks

- [x] 1.1 (Unit) Settle in `docs/glossary.md` the vocabulary the nine leaves inherit —
      section, playback, marker, hitbox, hurtbox, preset, dither, recolour, device,
      execution provider — and the synonyms each one displaces
- [x] 1.2 (Unit) Record as an ADR that `dist/index.json` is a versioned contract with one
      internal model behind per-engine emitters, since an engine reading it makes the shape
      expensive to change and three leaves write into it
- [x] 1.3 (Unit) Record as an ADR the `[cv]` and `[cv-gpu]` packaging split — which
      `onnxruntime` build each installs, why detection is independent of the installed
      runtime, and that the execution provider is part of the cache key
- [x] 1.4 (Unit) Distil into `docs/wiki/pages/` what the workspace-binding rounds cost —
      a platform-conditional hardening needs the other platform run before the PR, and a
      guard that cannot work has to refuse rather than report success — and clear the three
      `wiki.changelog-desync` findings standing in `docs/wiki/changelog.md`
- [x] 2.1 (Unit) Prove the chain end to end on a fixture: base image, poses, pixel art,
      sheet, `doctor`, `dist/index.json` — one test that goes red when any leaf's contract
      drifts, which is the failure no leaf's own suite can see
- [x] 2.2 (Unit) Write the agent workflow the six skills drive as a `docs/wiki/pages/` page
      reachable from `index.md`, naming which skill owns which step and where each gate falls
      _Depends 2.1_

### M4 — the harness · what an agent and an engine read

- [x] 3.1 (Unit) Read hit boxes, hurt boxes and named markers (footstep, spawn, cancel
      window) from the sidecar's `frames:` block, which `src/ssc/cli/sidecar.py` refuses
      today, and validate its length against the asset's frame count
- [x] 3.2 (Unit) Derive the alpha bounding box per frame with no authoring at all, and carry
      authored boxes and markers through curation so a dropped or reordered frame cannot
      silently shift them
- [x] 3.3 (Unit) Emit boxes and markers into `dist/index.json` behind the index's `schema`,
      carrying the authored values only — `ssc` never invents damage or knockback — and write
      the matching delta into the engine-index spec on the same branch
      _Depends 3.1, 3.2_
- [x] 4.1 (Unit) Write `sprite-cleanup`, `sprite-animation` and `sprite-style` under
      `.claude/skills/`, each naming the commands it runs, the gate it stops at and what it
      hands to the next skill
- [x] 4.2 (Unit) Write `sprite-character`, `sprite-resource` and `sprite-integrate` the same
      way, the last one ending at `dist/index.json`

### M5 — style and derivation

- [x] 5.1 (Unit) `ssc tool style` against a project-locked `palette.json`, with the presets
      pico8, nes, gameboy and sweetie16 shipped in `src/ssc/data/`
- [x] 5.2 (Unit) Ordered and Floyd-Steinberg dithering as a project decision recorded in the
      workspace, never a per-call argument, so two assets generated a week apart agree
- [x] 5.3 (Unit) `ssc tool recolour`, mapping one palette onto another, so a red slime and a
      blue slime are one asset and a colour map rather than two generations
      _Depends 5.1_
- [x] 5.4 (Unit) Carry `recolour` into the free path the budget guard refuses against: a paid
      call a colour map answers is refused the way `mirror` is already refused, with the
      matching delta written into the budget-guard spec
      _Depends 5.3_
- [x] 6.1 (Unit) `ssc asset new <key> --extends <parent>` and the `<asset>.yaml` behind it,
      inheriting the recipe — kind, pixel_size, palette, cell, frame counts, fps — and never
      the pixels
- [x] 6.2 (Unit) Carry the parent's anchors as a generation reference, and record the parent
      in the child's provenance so a derived asset says what it derived from
      _Depends 6.1_
- [x] 6.3 (Unit) If the parent is missing or the chain is cyclic, refuse with the chain walked
      so far rather than resolving a partial recipe
      _Depends 6.1_
- [x] 7.1 (Unit) Mirror about either axis, defaulting to the vertical one so every existing
      call keeps its meaning
- [x] 7.2 (Unit) `ssc tool rotate` by one, two or three quarter turns, refusing any other
      angle with the resampler as the stated reason — `tests/test_no_other_resampler.py` is
      the invariant this keeps
- [x] 7.3 (Unit) `ssc tool trim` to one box covering every frame's opaque pixels, never a box
      per frame
- [x] 7.4 (Unit) `ssc tool offset` by a whole number of pixels on either axis
- [x] 7.5 (TDD) Move the recorded anchor by the same transform as the frames — mirroring maps
      `x` to `width - 1 - x`, and dropping the `- 1` is a sprite that jitters when it turns
      _Depends 7.1, 7.2, 7.3, 7.4_
- [x] 7.6 (Unit) Report the dimensions an odd quarter turn produced and the cell they stopped
      matching
      _Depends 7.2_
- [x] 7.7 (Unit) Record the transform in the written file's provenance, so `trim` and `offset`
      stop being implicit steps inside `align` and `pack`
- [x] 7.8 (Unit) Move per-frame boxes and markers by the same transform — a mirrored frame
      with an unmirrored hurt box takes damage on the wrong side
      _Depends 3.1, 7.5_

### M6 — computer vision · the `[cv]` extra

- [x] 8.1 (Unit) `--device auto|cpu|cuda|directml|coreml`: `auto` picks the best provider
      available, a device named explicitly fails loudly rather than falling back
- [x] 8.2 (Unit) The `[cv]` and `[cv-gpu]` extras installing the matching `onnxruntime` build
      per `adr:0011`, recorded in `docs/stack.md`
- [x] 8.3 (Unit) Fold the execution provider into the cache key, so a CPU result and a CUDA
      result are not the same entry
      _Depends 8.1_
- [x] 8.4 (Unit) `ssc info` reports the GPUs present and the providers usable independently of
      the installed runtime, and returns a capable GPU under a CPU-only install as a
      structured hint carrying the exact install command
      _Depends 8.2_
- [x] 9.1 (Unit) `ssc tool bgremove --model birefnet|rembg` under the `[cv]` extra, beside the
      hosted `gen bgremove` path, with the matching delta written into the background-removal
      spec
      _Depends 8.3_
- [x] 9.2 (Unit) If the `[cv]` extra is absent, then the command refuses with the install
      command rather than a traceback
      _Depends 9.1_
- [x] 10.1 (Unit) Pose tracking through an animation cycle, reported per frame
      _Depends 8.3_
- [x] 10.2 (Unit) A consistency embedding across the frames of a set, as a number `doctor` can
      carry as a check
      _Depends 10.1_
- [x] 4.3 (Unit) Ship the six skills as templates inside the package and have `ssc init`
      write them into the workspace's `.claude/skills/`, so a game project installs the
      relay from the CLI rather than copying files out of this repository
  _Reason the skills are templates ssc installs, not files a user copies; ssc init is where a workspace gets them_

## Done when

- `ssc index --format pixi|phaser|godot|generic` writes `dist/index.json`, and `ssc preview`
  renders a GIF or a contact sheet from what that file declares
- Every asset in a workspace resolves against one `palette.json`, and `ssc tool recolour`
  produces a variant with no paid call
- `ssc info` reports the GPUs present and the providers usable, and installing the `[cv]`
  extra is the only step between a CPU box and a model-backed `bgremove`
- The six harness skills carry a run from a base image to the index, stopping only at gates
- `scc validate` exits 0, every task above is ticked, and `specs/engine-index/` still reports
  all tasks done
