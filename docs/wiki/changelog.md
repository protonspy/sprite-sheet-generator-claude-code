# Wiki changelog

## 2026-08-13 — three video models, and the price the provider publishes

`specs/model-pricing/`: Grok Imagine Video 1.5, Kling 2.5 Turbo Pro and Seedance 2.5 join
the registry, all image-to-video, none of them the default — the default for `video` stays
Grok Imagine Video and the default for `image` stays GPT Image 2. Every entry gains the
price text the provider published, with the day it was read; nothing parses a number out of
it, because the five models bill in five different shapes and a parser over prose is wrong
silently. `ssc model show` reports the text with a caveat naming it indicative, `ssc model
list` says which rows have one, and `ssc budget` stays the only record of what a run cost.
`scripts/fetch_model_schemas.py` — named by `CLAUDE.md` and `core.json` since before it
existed — now exists, and reads both provider documents without credentials. The shipped
instruction files and the four `sprite-*` skills gained the choice itself: which model a
step reaches for, and what to set when the work is one icon rather than a forty-frame sheet.

- **[[model-parameters]]** — the endpoint table grows to thirteen; new sections on the
  published price and on why the three added models take no `--size`.

## 2026-08-12 — four endpoints, a size in pixels, and options with names

`specs/model-options/`: GPT Image 2 and Grok Imagine Image join the registry, each with its
`/edit` twin; GPT Image 2 becomes the model a workspace reaches for by default, which is what
lets a freshly created one generate at all. `count`, `quality` and `format` become core options
with flags of their own rather than things a caller had to know `--opt` could carry, and a kind
may default them. Every image a call produced is filed, where `--count 4` used to bill four and
keep one.

- **[[model-parameters]]** — rewritten. Eight endpoints instead of four; the default model and
  why it lives in the package rather than in `ssc.yaml`; GPT Image 2 taking a size in explicit
  pixels, with its real bounds stated in the field's description rather than in the schema; the
  three newly-named options, what `--count` costs, and the asymmetry between an option a caller
  named and one a kind defaulted.

## 2026-08-05 — the gate that holds between one asset's animations

`plans/sprite-normalisation-gate.md`: three leaves — `tool bounds`, `tool normalise`,
`tool preview` — and the `scale` check on `tool doctor` that ties them. The cross-set
instability that survives every within-set repair gets a number, a fix, and a six-step
gate that runs by a person.

- **[[sprite-normalisation-gate]]** — new. The six steps as one ordered sequence: `tool
  bounds` measures each frame, `tool doctor` repairs one set, `tool doctor` with repeated
  `--in` measures across sets, `tool normalise` resamples and aligns them, `tool doctor`
  confirms `scale` at `0`, and `tool preview` renders what a number cannot catch. Each
  step carries its exact command and flags, what `doctor` reports between them, and the
  one failure mode it is there to catch.
- `index.md` — links the new page under "Repairing it".
- `docs/glossary.md` — **frame set**, **visible height**, **baseline**, **centre
  column** and **scale** settled, the vocabulary the gate measures with. `visible height`
  is the alpha box's height, never the canvas; `scale` is its disagreement across one
  asset's sets, with `tool normalise` as its fix.

## 2026-08-05 — the skills ship with the CLI

Task 4.3 of `plans/ssc-completion.md`: the six `sprite-*` skills are a template `ssc`
installs, not files a project copies. They live in `src/ssc/data/skills/` and `ssc init`
writes them into the workspace's `.claude/skills/`.

- **[[agent-workflow]]** — says where the skills come from: shipped in the package,
  written out by `ssc init`, skippable with `--no-skills`, and never overwriting a skill
  a project has edited.

## 2026-08-05 — the project-locked palette gets its own command

Tasks 5.1 and 5.2 of `plans/ssc-completion.md`: `tool style` reads the workspace's locked
`palette.json`, where the page had been naming `tool pixelart` for that path; dither is a
workspace decision under `style:` in `ssc.yaml`, never a per-call flag.

- **[[agent-workflow]]** — the `sprite-style` row now names `tool style` against the
  locked `palette.json`. `tool pixelart` is the ad-hoc sibling for loose PNGs with no
  workspace, not the project-locked path the relay runs.

## 2026-08-05 — the index carries what a frame deals, receives and does

Group 3 of `plans/ssc-completion.md`: per-frame data, end to end — sidecar to index.

- **[[into-an-engine]]** — "What the index does not carry" became "What travels per
  frame": the sidecar's `frames:` block, the derived `bounds`, `per_frame` in `generic`
  only, and curation carrying entries past a drop. The old section promised this work to
  `specs/frame-metadata/`, which was never written — the delta landed in
  `specs/engine-index/` R7 instead.

## 2026-08-05 — the run, named end to end

Group 2 of `plans/ssc-completion.md`: the chain is proven by one test, and the workflow
that drives it is now a page rather than an assumption.

- **[[agent-workflow]]** — new. The relay the six skills own, which commands each runs,
  what each hands the next, and the four gates — anchor image, curated frames, palette
  lock, preview — as the only places the run stops. Written before the skills themselves
  so that group 4 implements a page rather than the page transcribing an implementation.
- `index.md` — links the new page under "Start here".
- `tests/cli/test_chain.py` — not a page, but the page cites it: one fixture-driven test
  from a faked generation through cut, pipeline, `doctor` and `ssc index`, red when any
  leaf's contract with the next drifts.

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
