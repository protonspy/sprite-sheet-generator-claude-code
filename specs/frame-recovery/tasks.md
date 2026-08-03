# Frame recovery — tasks

**What already covers these paths:** `tests/core/test_bgremove.py` covers `key_mask` and
`reachable_from_border`, which the chroma mode reuses rather than reimplementing —
`background-removal` is this leaf's dependency for exactly that reason. `tests/core/doctor/test_checks.py`
covers `label_regions`/`region_areas` behind the islands mode, and `check_bleed`, which takes
a grid as a parameter and must keep agreeing with what this leaf detects.
`tests/cli/test_frames.py` covers the frame-set IO and the ceilings, and `tests/cli/test_meta.py`
covers the record both bindings write. All were run green before this work started.

## 1 · Finding the pieces

- [x] 1.1 (Unit) Cut a given grid into rectangles, ordered top to bottom then left to right — R1.1, R1.8
- [x] 1.2 (Unit) Take pieces by chroma bounding box and by connected island — R1.4, R1.5
- [x] 1.3 (Unit) Discard a piece below `--min-size` or past `--max-aspect` — R1.6, R1.7
- [x] 1.4 (Unit) Bound the pieces a mask and a grid may produce, and take the bounding boxes in one pass — R1.9, R1.10

## 2 · Detecting a grid

- [x] 2.1 (TDD) Detect columns, rows, cell, margin and spacing from the projection profiles — R1.2, R2.1, R2.2, R2.3
- [x] 2.3 (Unit) Refuse a layout that is not regular — R2.4
- [x] 2.2 (Unit) Refuse rather than guess when no grid is there — R1.3

## 3 · The two bindings

- [x] 3.1 (Unit) Build `ssc tool cut`: the pieces as the frames of one animation — R3.1, R3.5
- [x] 3.2 (Unit) Build `ssc tool slice`: each piece its own asset with its own key — R3.2
- [x] 3.3 (Unit) Record into the named asset, write plain files to a named path, and require exactly one of the two — R3.3, R3.4, R3.6
- [x] 3.4 (Unit) Put the third route to an asset directory behind the same containment guard as the other two — R3.7

## 4 · Curating

- [x] 4.1 (Unit) Measure how far a frame is from the one before it, keeping the first always — R4.2, R4.4
- [x] 4.2 (Unit) Build `ssc tool curate`: report the redundant frames, and drop them when asked — R4.1, R4.3
