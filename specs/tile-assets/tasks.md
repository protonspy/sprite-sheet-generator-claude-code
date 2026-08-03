# Tile assets — tasks

**What already covers these paths:** `tests/core/doctor/test_checks.py` and
`tests/cli/test_doctor.py` cover the seven checks, the skipped-with-a-reason contract and
the report's shape — `seam` joins that report. `tests/cli/test_atlas_commands.py` and
`tests/cli/test_recover_commands.py` cover `tool pack` in both layouts, including the ids
R3.1 reuses. All were run green before this work started.

## 1 · Closing the wrap

- [x] 1.1 (Unit) Copy the first column and row onto the last, and report which edges changed and how many pixels — R1.1, R1.3
- [x] 1.2 (Unit) Mirror the tile about both axes under `--mode mirror` — R1.2
- [x] 1.3 (Unit) Refuse an input smaller than two pixels on a side — R1.4

## 2 · Measuring it

- [x] 2.1 (TDD) Measure `seam` as the wrap difference over the image's own interior adjacency, on both axes — R2.1
- [x] 2.2 (Unit) Name `ssc tool tile` as the fix, and skip with a reason where the input is too small — R2.2, R2.3

## 3 · The commands

- [x] 3.1 (Unit) `ssc tool tile` over one image or a set, writing a new file per input — R1.1, R1.5
- [x] 3.2 (Unit) Run `seam` from `doctor --check seam` and from a kind whose profile declares it, and report it skipped otherwise — R2.4
- [x] 3.3 (Unit) Report the tile size and one id per tile when a grid-layout kind is packed, refusing a set of unequal tiles — R3.1, R3.2

## Notes

**One task is TDD, and it is the measurement rather than the fix.** Closing the wrap is two
slice assignments whose correctness is readable; the check is a ratio whose scale was chosen
rather than derived, and the failure mode is a threshold that reports every flat tile as
broken or every noisy one as clean. The test says what the number *means* — a tile that
already wraps scores about 1, one with a hard discontinuity scores far above it — before the
threshold exists to be tuned against a fixture.

**The red was observed, and it changed the fixture rather than the threshold.** 2.1 first
failed on `ImportError`, then — with a working check — on a tile of uniform per-pixel noise
with a hard black edge, which it called clean. That is the metric being right about a
pathological input: noise is maximally discontinuous everywhere, so nothing in it can be
unusual. The fixture became a blocky texture, which is what `snap` and `pixelart` actually
produce, and the limitation is written down in `design.md` so nobody later "fixes" the
threshold against noise.
