# Wiki changelog

## 2026-08-05 — what the binding rounds cost, and the vocabulary M4 through M6 inherit

Group 1 of `plans/ssc-completion.md`: settle the words and the decisions the nine remaining
leaves inherit, before any of them is built.

- **[[workspace-binding]]** — new. Why a checked path is not a safe path, what the Windows
  identity fallback does and does not buy against a descriptor, and the two habits four
  review rounds paid for: a platform-conditional hardening is unverified until the other
  platform has run it, and a guard that cannot prove it works has to refuse rather than
  report success.
- **[[into-an-engine]]** — moved into `pages/`, where pages live. No change to the text.
- `index.md` — links the new page under a new "Building the tool" heading.
- `docs/glossary.md` — **marker**, **hitbox**, **hurtbox**, **palette**, **preset**,
  **recolour**, **device** and **execution provider** settled, before the leaves that use
  them are built. An execution provider is said in full: a provider alone is the generation
  provider.
- `adr:0010-the-index-is-a-versioned-contract-behind-per-engine-emitters` — an engine reads
  `dist/index.json`, so its shape is other people's code; one internal model, pure emitters,
  and `schema` versions the shape rather than `ssc`.
- `adr:0011-two-extras-for-onnxruntime-and-detection-that-ignores-them` — `onnxruntime` and
  `onnxruntime-gpu` publish the same import name, so the split is two extras and not a flag;
  hardware detection reads the machine rather than the installed runtime, because the CPU-only
  install is exactly the one that has to be told about the GPU.
- Earlier entries linked `[[index]]`, which is `docs/wiki/index.md` and not a page. They name
  the file instead.

## 2026-08-04 — the handover, and where authored values live

`specs/engine-index/` built `ssc index` and `ssc preview`, which is the first part of this
project that writes something an engine reads rather than something a later step repairs.

- **[[into-an-engine]]** — new. What each kind becomes in `dist/`, why the index is built
  rather than recorded, and the one thing the three engine formats cannot say: a playback
  mode. It is baked into the frame order instead, which is why a six-frame ping-pong
  animation appears with ten entries.
- **`index.md`** — links the new page under a new "Handing it over" heading.
- `docs/glossary.md` — **index**, **sidecar**, **tileset**, **playback mode** and
  **section** settled, before the JSON fields that use them shipped.
- `adr:0009-authored-intent-lives-in-a-sidecar` — a frame rate is a decision, not
  provenance, so it does not go in the file `ssc clean` reads to decide what to delete.

## 2026-08-03 — silhouette gets a metric

`specs/sheet-doctor/` closed the one gap this page named as open.

- **[[game-ready-defects]]** — `silhouette` is mask integrity at the target cell: holes
  the body encloses, and fragments the body broke into. Outline readability was the other
  reading and was rejected, with why. The page no longer tells the reader to assume no
  metric, because there is one.

## 2026-08-02 — what the models accept, and one banned synonym

Task 0.7 of `plans/ssc-pipeline.md` read the four named models' schemas off Fal's
published OpenAPI documents rather than transcribing them.

- **[[model-parameters]]** — new. The endpoint ids, the fact that the schemas are
  machine-readable, and the finding the plan needed: none of the three image paths takes a
  size in pixels, and GPT Image 1.5 offers exactly three shapes, so a 6:1 pose board is
  unrepresentable rather than merely awkward. Also that `seed` is absent from GPT Image
  1.5, that it can return alpha directly, and that BiRefNet is six models behind one
  endpoint.
- **`index.md`** — links the new page under "Producing the art".
- **[[prior-art]]** — "sprite sheets" became "sheets"; `docs/glossary.md` now settles
  **sheet** as the canonical term.

## 2026-08-02 — review corrections

A review against `plans/ssc-pipeline.md` found the defect vocabulary had drifted from the
plan on its first day.

- **[[game-ready-defects]]** — `silhouette` was missing entirely, though the plan names it
  as one of doctor's seven checks; added, with the fact that its metric is still unsettled
  stated rather than invented. `broken cycles` was in the plan's defect list and on no
  page; added, marked as the one defect measured by the loop score rather than by
  `doctor`. `seam` and `nineslice` were presented as current checks when they arrive with
  the tile and UI kinds; marked as such.
- **`index.md`** — dropped the defect count, which was wrong and would go stale again on
  the next check added.

## 2026-08-02 — the wiki opens

Distilled from the `ssc` design document and three video transcripts collected in
`docs/raw/`, which were removed once processed.

- **`index.md`** — entry point.
- **[[game-ready-defects]]** — the defect vocabulary: fake pixels, frame bleeding, drift,
  halo, palette drift, flicker, silhouette loss, seam, nine-slice breakage, broken cycles.
  Written first because every other page depends on the vocabulary.
- **[[anchor-and-directions]]** — anchor discipline, the neutral-pose rule, generating
  the other three directions, and where mirroring West to East breaks.
- **[[reference-boards]]** — checkerboard and pose board, why they are not
  interchangeable, why they are generated rather than downloaded, and why neither goes
  near a video model.
- **[[generating-animations]]** — image generation for idle and attack, video for walk
  cycles, per-action frame counts, and clip length as a per-model fact rather than a
  setting.
- **[[pixel-snapping]]** — the snapping algorithm, nearest neighbour as an invariant, why
  it runs twice, and pixel size as a project-wide decision.
- **[[frame-normalisation]]** — recovering frames by bounding box, curating, snapping
  each frame, anchoring the feet, keying the background, packing.
- **[[prior-art]]** — spritefusion-pixel-snapper adopted, proper-pixel-art refused,
  Sorceress read closely, 3D→2D out of scope.
- **[[prompt-templates]]** — the frame a caller's words go into: one kind is not one
  template, the eight named slots and why the vocabulary is closed, the asymmetry between
  a missing slot and a spare one, chroma on every sprite template and deliberately not on
  `box-art`, and the base animation template against the walk cycle.
