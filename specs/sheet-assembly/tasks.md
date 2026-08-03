# Sheet assembly — tasks

**What already covers these paths:** `tests/core/doctor/test_checks.py` and the mask helpers
cover `anchor`, which `align` reuses rather than redefining — it is the test that would
notice the two drifting apart. `tests/core/test_resize.py` and `tests/test_no_other_resampler.py`
cover the invariant this leaf must not break, and none of these four operations resamples at
all. `tests/cli/test_frames.py` covers the frame-set IO and `tests/cli/test_recover_commands.py`
covers the module these commands join. All were run green before this work started.

## 1 · Moving one frame

- [x] 1.1 (Unit) Pad a frame to a size or by a margin, filled or transparent, placed by anchor — R1.1, R1.2, R1.3, R1.4, R1.5
- [x] 1.2 (Unit) Flip a frame horizontally — R2.1

## 2 · Moving a set onto one anchor

- [x] 2.1 (TDD) Find the canvas and the offsets that put every frame's anchor on one pixel — R3.2, R3.3
- [x] 2.2 (Unit) Leave an empty frame where it is, and report it — R3.4

## 3 · The sheet

- [x] 3.1 (Unit) Lay a set out in equal cells, refusing a frame that does not fit — R4.1, R4.2, R4.3

## 4 · The commands

- [x] 4.1 (Unit) Build `ssc tool expand` and `ssc tool mirror` — R1.1, R1.5, R2.2
- [x] 4.2 (Unit) Build `ssc tool align`, with the onion skin — R3.1, R3.5
- [x] 4.3 (Unit) Build `ssc tool pack`, reporting the cell, the grid and the anchor — R4.4
