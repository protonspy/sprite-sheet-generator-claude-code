# Sheet doctor — tasks

**What already covers these paths:** nothing measures an image yet. `tests/core/test_resize.py`
covers `ssc.core.resize`, which every detector reducing a mask will call, and
`tests/test_no_other_resampler.py` fails if one of them reaches for another resampler —
both run before and after this work. The CLI contract tests (`tests/cli/test_main.py`,
`test_output.py`, `test_errors.py`) cover the `Result`/`SscError` plumbing `doctor` plugs
into and must stay green.

## 1 · The shape of a finding

- [x] 1.1 (Unit) Define `Check`, `Finding` and `Report` — measurement, status, fix, and the skipped-with-a-reason case — R1.2, R1.3, R1.4, R1.5
- [x] 1.2 (Unit) Build the mask helpers every detector needs: alpha mask, bounding box, anchor, connected components — R2.3, R2.7

## 2 · The single-image checks

- [x] 2.1 (TDD) Measure `pixel_grid`: detect the pixel size, then the share of pixels differing from their own cell's dominant colour — R2.1
- [x] 2.2 (Unit) Measure `halo` as the count of pixels whose alpha is neither 0 nor 255 — R2.4
- [x] 2.3 (Unit) Measure `palette` as distinct opaque colours, plus the pixels outside a given palette — R2.5
- [x] 2.4 (TDD) Measure `silhouette` on the mask reduced to `--cell`: enclosed background regions, and separate opaque regions — R2.7

## 3 · The checks that need more than one image

- [x] 3.1 (TDD) Measure `drift` as the largest distance from a frame's anchor to the set's median anchor — R2.3
- [x] 3.2 (TDD) Measure `flicker` as small colour changes at unchanged alpha between adjacent frames, told apart from motion — R2.6
- [x] 3.3 (TDD) Measure `bleed` as the count of cells whose content touches a shared boundary — R2.2

## 4 · The command

- [x] 4.1 (Unit) Read `--in` as one image or a directory of frames, and refuse anything else — R3.1, R3.5
- [x] 4.2 (Unit) Run every applicable check and skip the rest with their reason — R1.1, R1.3, R3.2, R3.3
- [x] 4.3 (Unit) Report the findings as one object and exit `0` whether or not anything was found — R3.4

## 5 · The fixtures that prove it

- [x] 5.1 (Unit) Build and measure a fixture carrying each defect and a clean counterpart, for each of the seven checks — R4.1, R4.2

## Notes

**How the red was observed on the five TDD tasks, and where the order was not kept.** The
detectors were written before their tests, which is not TDD, and pretending otherwise
would be worse than saying it. What was done instead: the tests were written from
`requirements.md` rather than from the code, then the five detectors' bodies were replaced
with `raise NotImplementedError` and the suite run — every assertion failed, which is the
part of red that carries the meaning, since a test that passes with the behaviour absent
is testing nothing. Restoring the bodies then turned up **two real defects the tests
caught**: `drift` measured the centre of the bounding box, so a swinging arm read as the
character sliding; and `silhouette` reduced the mask by point sampling, so whether a
one-pixel hole survived depended on where the samples landed. Both are fixed and both are
recorded in `design.md`.

**Five of twelve tasks are TDD, which is high, and the reason is that this leaf is a
measuring instrument.** Every later leaf is judged against these numbers, so a detector
that is confidently wrong is worse than one that is missing — `doctor` being right is the
precondition for "measure, don't guess" meaning anything here. `pixel_grid`, `silhouette`,
`drift`, `flicker` and `bleed` are the five whose correctness is not obvious from reading
them. `halo` and `palette` are counts over an array, and are Unit.

**Task 2.4 settles a question the plan left open.** `silhouette` had no metric;
`design.md` adopts mask integrity at the target cell and rejects outline readability, and
says what that costs. Worth surfacing before it lands: it is the one decision here that
closes off an option rather than implementing one.

**Task 5.1 is last and it is not a formality.** The fixtures are the asset — `doctor` is
validated against those exact numbers and everything downstream depends on `doctor` being
right, so they are never regenerated to make a test pass.
