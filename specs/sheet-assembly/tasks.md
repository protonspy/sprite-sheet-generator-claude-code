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
- [x] 3.3 (Unit) Measure the anchor a packed set shares rather than assuming it, and say when it shares none — R4.4, R4.6

- [x] 3.4 (Unit) Bound every canvas these build, on the result rather than on the flag — R1.6, R3.6, R4.5

## 4 · The commands

- [x] 4.1 (Unit) Build `ssc tool expand` and `ssc tool mirror` — R1.1, R1.5, R2.2, R2.3
- [x] 4.2 (Unit) Build `ssc tool align`, with the onion skin — R3.1, R3.5
- [x] 4.3 (Unit) Build `ssc tool pack`, reporting the cell, the grid and the anchor — R4.4
- [x] 4.4 (Unit) Carry the anchor mode from `align` to `pack`, so the two measure the same thing — R4.6, R4.7
- [x] 4.5 (Unit) Move the recorded anchor with the mirror — R2.4
  _Reason plan task 7.5 adds anchor-moving to mirror; R2.4 needs a task that reaches it_

## 5 · The rest of the transforms, and what they carry

_Reason plans/ssc-completion.md tasks 7.2, 7.3, 7.4, 7.5, 7.6, 7.7 and 7.8 build `rotate`,
`trim` and `offset` beside the `mirror` this spec already owned; R5 and R6 are theirs._

- [x] 5.1 (Unit) Turn a frame by quarter turns and slide one by whole pixels, both placements rather than resamples — R5.1, R5.7
- [x] 5.2 (Unit) Crop a set to the one box covering every frame's opaque pixels, refusing a set with nothing opaque — R5.5, R5.6
- [x] 5.3 (Unit) Build `ssc tool rotate`, `ssc tool trim` and `ssc tool offset`, each refusing the call that would resample or move nothing — R5.2, R5.3, R5.8
- [x] 5.4 (TDD) Move the recorded anchor by the same placement as the frames — R6.1
  _Depends 5.1, 5.2_
- [x] 5.5 (Unit) Report the cell an odd quarter turn stopped matching, and the one it would fit — R5.4
  _Depends 5.3_
- [x] 5.6 (Unit) Move authored hit boxes and hurt boxes by the same placement, dropping a box the canvas lost — R6.2
  _Depends 5.4_
- [x] 5.7 (Unit) Record a transform as its own stage with its command and parameters, refusing where the sidecar cannot be bound — R6.3, R6.4
  _Depends 5.6_
