# UI assets — tasks

**What already covers these paths:** `tests/core/doctor/test_checks.py` and
`tests/cli/test_doctor.py` cover the check contract `nineslice` joins, including
skipped-with-a-reason and the `--check` route `seam` established; `tests/core/test_atlas.py`
and `tests/cli/test_tile_commands.py` cover the id-and-rect reporting `tool states` follows;
`detect_pixel_size`, which R1.2 snaps to, is covered in `tests/core/doctor/test_checks.py`.
All were run green before this work started.

## 1 · The guides

- [x] 1.1 (Unit) Derive guides from the art's pixel size, and snap given ones onto it — R1.2, R1.3
- [x] 1.2 (Unit) Report the four guides and the nine region sizes — R1.1, R1.5
- [x] 1.3 (Unit) Refuse a guide outside the image, or two on one axis that meet or cross — R1.4

## 2 · The check

- [x] 2.1 (TDD) Measure `nineslice` as the variation within each stretched region along the axis it stretches on — R2.1
- [x] 2.2 (Unit) Name `ssc tool ninepatch` as the fix, and skip with a reason where no guides were given — R2.2, R2.4
- [x] 2.3 (Unit) Run `nineslice` only where it was asked for, and report it skipped otherwise — R2.3

## 3 · States

- [x] 3.1 (Unit) `ssc tool states` — one sheet in a fixed order, each state's name and rectangle — R3.1
- [x] 3.2 (Unit) Refuse an unknown state name and a set of differing sizes, naming what it found — R3.2, R3.3

## Notes

**One task is TDD, and it is the measurement again.** The guides are arithmetic a reader can
check; `nineslice` is a number whose meaning has to be decided before it can be implemented,
and the failure mode is a threshold that calls every panel broken or every panel fine. What
the test pins is the meaning: a region uniform along the axis it stretches on scores zero,
and one that changes along that axis scores above the threshold — regardless of how busy the
art is in the direction it does not stretch.

**The red on 2.1 was an `ImportError`, and the design decision it forced came first.** The
number had to mean something before it could fail usefully: writing
`test_busy_art_across_the_stretch_axis_is_not_a_defect` and
`test_a_corner_may_be_anything_because_a_corner_never_stretches` is what settled that the
check measures *per region, along that region's own axis* rather than variance over the whole
image — which the obvious implementation would have done, and which would have called every
decorated panel broken.
