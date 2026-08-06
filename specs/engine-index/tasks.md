# Engine index — tasks

**What already covers these paths:** `tests/cli/test_kinds.py` covers the profile this leaf
adds `fps` to; `tests/cli/test_listing.py` and `tests/cli/test_media.py` cover walking the
workspace and resolving an asset's stage, which `cli/index.py` does again for every asset at
once; `tests/cli/test_meta.py` covers the record the sidecar sits beside without joining;
`tests/cli/test_workspace.py` covers the paths `dist` joins; `tests/core/test_assemble.py`,
`tests/core/test_atlas.py`, `tests/core/test_ninepatch.py` and `tests/core/test_tile.py`
cover the packers and the guides this leaf calls rather than reimplements;
`tests/core/test_contact.py` covers the contact-sheet geometry `ssc preview` reuses. All were
run green before this work started — 290 passed, 2 skipped.

## 1 · The authored half

- [x] 1.1 (Unit) Read `asset.yaml` into a playback record — frame rate, mode and sections — refusing a file that is not a map, an unknown key and a mode that is not one of the three — R4.1, R4.3
- [x] 1.2 (Unit) Add `fps` to the kind profile and fall back to it where the sidecar declares none, as a delta on `specs/asset-kinds/` — R4.2
- [x] 1.3 (Unit) Keep the sidecar out of `meta.json` and out of `ssc clean`'s reach — R4.4
- [x] 1.4 (TDD) Resolve a named section against a frame count, refusing one whose first or last frame the set does not have — R2.4, R2.5

## 2 · The model

- [x] 2.1 (Unit) Walk the workspace into per-kind groups, resolving each asset's published stage and reporting the ones with no image as skipped — R1.1, R1.2, R1.3, R1.4, R1.5
- [x] 2.2 (Unit) Build a sheet from a frame set — cell, columns, rows, frame count, anchor, and whether the set was aligned — R2.1, R2.2
- [x] 2.3 (Unit) Carry a sheet's playback: frame rate, mode and resolved sections — R2.3
- [x] 2.4 (Unit) Build an atlas for a `bin` kind — a rect and an anchor per asset, with the padding and the extrusion — R3.1
- [x] 2.5 (Unit) Build a tileset for a `grid` kind — tile size, grid, and each tile's id, column and row — R3.2
- [x] 2.6 (Unit) Carry the nine-slice borders on the entries of a kind whose checks name `nineslice` — R3.3

## 3 · dist/ and the formats

- [x] 3.1 (Unit) Emit the `generic` format from the model, and refuse a format ssc does not emit — R5.1, R5.6
- [x] 3.2 (TDD) Emit the `pixi` format — frames by name, animations in playback order, and meta — against a hand-worked sheet and atlas — R5.2
- [x] 3.3 (Unit) Emit the `phaser` JSON Hash format — R5.3
- [x] 3.4 (Unit) Emit the `godot` format — region, margin, speed and loop — R5.4
- [x] 3.5 (Unit) Hold the four formats to one set of image files and one set of rects — R5.5
- [x] 3.6 (Unit) Write the images and `index.json` under `dist/` in one pass, and nowhere else — R1.6, R1.7
- [x] 3.7 (Unit) Make a second run over an unchanged workspace write the same bytes — R1.8
- [x] 3.8 (Unit) Report under `--dry-run` every file the run would write, and write none — R1.9

## 4 · Preview

- [x] 4.1 (TDD) Order a frame set for a playback mode — `loop`, `ping-pong`, `reverse` — and for one named section — R6.1, R6.4
- [x] 4.2 (Unit) Encode the ordered frames as an animated GIF at the declared frame rate — R6.1
- [x] 4.3 (Unit) Render a contact sheet instead, each frame labelled with its index — R6.2
- [x] 4.4 (Unit) Tile a seam-checked kind's asset 2×2 — R6.3
- [x] 4.5 (Unit) `ssc preview` — resolve the asset through `dist/index.json`, refuse when there is none, and write only under `dist/preview/` — R6.5, R6.6
- [x] 4.6 (Unit) Render the index path through the same renderer as tool preview — R6.7
  _Reason plan task 5.3 ships the shared renderer; this task reaches R6.7 so the spec's traceability holds_

## 5 · Wiring

- [x] 5.1 (Unit) Register `ssc index` and `ssc preview`, and give the workspace its `dist` path — R1.7
- [x] 5.2 (Unit) Record `adr:0009-authored-intent-lives-in-a-sidecar`, the glossary terms this leaf coins, and the wiki page for taking a workspace into an engine — R4.1

## 6 · Per-frame data

Delta from `plans/ssc-completion.md` group 3, built there and recorded here.

- [x] 6.1 (Unit) Read hitboxes, hurtboxes and markers from the sidecar's `frames:` block, and validate its length against the published set — R7.1, R7.2
- [x] 6.2 (Unit) Derive the alpha bounding box per frame, and carry the authored block through `tool curate` — refusing one it cannot line up — R7.3, R7.6, R7.7
- [x] 6.3 (Unit) Emit `per_frame` in the `generic` format, and skip an authored block on a kind that does not animate — R7.4, R7.5

## Notes

**1.4, 3.2 and 4.1 are the three that are TDD, and each for its own reason.** A section is a
pair of inclusive frame indices, which is an off-by-one waiting to happen and one no engine
will complain about — it will simply play the wrong frames. `pixi` is the format whose anchor
is a fraction rather than a pixel and whose animation is an ordered list of names rather than
a range, so it is the one where the mapping from the model is a translation rather than a
rename; the other three emitters are checked against it. And the playback order is the shared
algorithm underneath both the emitters and `ssc preview` — `ping-pong` over four frames is
six frames, not eight, and getting that wrong is invisible until somebody watches the
animation stutter at the ends.

**1.4 and 4.1 observed the red; 3.2 did not, and that is a deviation rather than a detail.**
Both of the first two were stubbed to `NotImplementedError`, run, and watched fail before a
line of either was written. The `pixi` emitter was written before its tests, so 3.2 got the
Unit cycle under a `(TDD)` annotation. What was salvaged is the part TDD is actually for: the
assertions are hand-worked from PixiJS's documented `SpritesheetData` and from the constants
at the top of `tests/cli/test_formats.py`, not read off the emitter's output — and that was
checked rather than asserted, by emptying `formats.pixi` and confirming all six of its tests
and four of the shared ones failed. It is recorded here because a `(TDD)` box ticked without
a red is exactly the claim this practice exists to stop anybody making quietly.

**4.1 was built before group 3, out of order.** The Pixi and Godot emitters bake the playback
mode into their frame lists, so `core.preview.order` had to exist before 3.2 could be
written. The alternative was a second ordering inside `formats.py`, which is the divergence
that function exists to prevent.
