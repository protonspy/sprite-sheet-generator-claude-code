# Wiki changelog

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
- **[[index]]** — links the new page under "Producing the art".
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
- **[[index]]** — dropped the defect count, which was wrong and would go stale again on
  the next check added.

## 2026-08-02 — the wiki opens

Distilled from the `ssc` design document and three video transcripts collected in
`docs/raw/`, which were removed once processed.

- **[[index]]** — entry point.
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
