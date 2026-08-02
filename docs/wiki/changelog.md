# Wiki changelog

## 2026-08-02 — the wiki opens

Distilled from the `ssc` design document and three video transcripts collected in
`docs/raw/`, which were removed once processed.

- **[[index]]** — entry point.
- **[[game-ready-defects]]** — the eight defects the tool measures: fake pixels, frame
  bleeding, drift, halo, palette drift, flicker, seam, nine-slice breakage. Written first
  because every other page depends on the vocabulary.
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
