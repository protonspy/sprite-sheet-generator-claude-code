# doctor fixtures

These files have **measured** defects. `doctor` is validated against these exact numbers,
and everything downstream depends on `doctor` being right — so a fixture is never
regenerated to make a test pass. If a number changes, a detector changed, and that is the
thing to look at. `build.py` documents how each one was constructed; it is not a step in
any workflow.

All of them are the same 8x8 body, blocked up 4x to 32x32, except the bleed pair.

| Fixture | Defect | Measured |
|---|---|---|
| `pixel-grid-clean.png` | none | `pixel_size` 4, `off_grid_ratio` 0.0 |
| `pixel-grid-defect.png` | bicubic upscale, every block edge a ramp | `pixel_size` 1, `off_grid_ratio` 1.0 |
| `halo-clean.png` | none | 0 semi-transparent px |
| `halo-defect.png` | feathered alpha edge | 40 semi-transparent px |
| `palette-clean.png` | none | 3 colours |
| `palette-defect.png` | an unquantized ramp across the body | 48 colours |
| `silhouette-clean.png` | none | 0 holes, 1 fragment |
| `silhouette-holes.png` | 4x4 punched through the body | 1 hole, 1 fragment |
| `silhouette-split.png` | a 4px column cut, body in two | 0 holes, 2 fragments |
| `bleed-clean.png` | none | 0 cells touching a shared boundary |
| `bleed-defect.png` | an arm crossing into the next cell | 2 cells |
| `drift-clean/` | none | `max_drift_px` 0.0 |
| `drift-defect/` | frame 2 slid 3px sideways | `max_drift_px` 3.0, worst frame 2 |
| `flicker-clean/` | none | 0 flickering px |
| `flicker-defect/` | frame 2 re-quantized by 6 over the whole body | 384 px, worst pair 1 |

**Two of these prove the checks tell each other apart**, which is the part worth keeping:
`drift-defect/` must not read as flicker (a 3px slide is motion, a large colour change at
every edge), and `flicker-defect/` must not read as drift (nothing moved). Both are
asserted in `tests/core/doctor/test_fixtures.py`.

The silhouette pair is split in two because a hole and a split are two different failures
with two different numbers. Both cuts are four source columns wide so they survive the
reduction to an 8x8 cell — a two-column cut vanishes there, which is the check working
rather than failing.
