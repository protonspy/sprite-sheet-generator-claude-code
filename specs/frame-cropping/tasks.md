# Frame cropping — tasks

**What already covers these paths:** `tests/core/test_recover.py` covers `crop` and its
refusal of a rectangle that is not wholly inside the image; `tests/cli/test_frames.py`
covers reading a file or a directory as a set and the all-or-nothing write;
`tests/cli/test_recover_commands.py` covers the `--in`/`--out`/`--asset` shape this joins,
including the recorded stage, the moved authored boxes and the reported anchor. All three
were run green before this work started.

## 1 · The rectangle

- [x] 1.1 (TDD) Fit the largest rectangle of a stated ratio inside a canvas and position it by gravity — R1.4, R1.7
- [x] 1.2 (Unit) Take a canvas down by an inset given as one number or as four — R1.5, R1.7

## 2 · The command

- [x] 2.1 (Unit) `ssc tool crop` over one image or a set, cutting a stated box and refusing one that is not wholly inside a frame — R1.1, R1.3, R1.6
  _Depends 1.1, 1.2_
- [x] 2.2 (Unit) Require exactly one way of stating the box, and exactly one destination — R1.2, R3.1
  _Depends 2.1_
- [x] 2.3 (Unit) One rectangle for the set, one per frame under `--per-frame`, and the refusals that flag carries — R2.1, R2.2, R2.3, R3.5
  _Depends 2.1_
- [x] 2.4 (Unit) Report the rectangle cut and the size produced — R2.4
  _Depends 2.1_

## 3 · Into the asset

- [x] 3.1 (Unit) Record the frames as the `crop` stage, moving the authored boxes and reporting the moved anchor — R3.2, R3.3, R3.4
  _Depends 2.1_

## Notes

**One task is TDD, and it is the aspect fit.** A crop placed a pixel off is still a crop:
it looks right, and the damage surfaces later as a sprite that jitters against its anchor
once the set is packed. The red was observed on 1.1 — `ModuleNotFoundError: No module
named 'ssc.core.crop'` — and the properties that mattered were the ones an eye cannot
check: the fitted rectangle stays inside the canvas, one of its sides always equals the
canvas, and opposite gravities land against opposite edges.

**R3.5 was added while building 2.3**, once `--per-frame` met `transform_into_asset`,
which takes one move for the whole sidecar. An anchor is one point for the set for the
same reason, so the refusal covers both.
