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

- [x] 2.1 (Unit) Measure `pixel_grid`: detect the pixel size, then the share of pixels differing from their own cell's dominant colour — R2.1
- [x] 2.2 (Unit) Measure `halo` as the count of pixels whose alpha is neither 0 nor 255 — R2.4
- [x] 2.3 (Unit) Measure `palette` as distinct opaque colours, the pixels outside a given palette, and a colour budget — R2.5
- [x] 2.4 (Unit) Measure `silhouette` on the mask reduced to `--cell`: enclosed background regions, and separate opaque regions — R2.7
- [x] 2.5 (Unit) Measure `seam` per axis as the wrap difference over the image's own neighbouring-line difference, added as `specs/tile-assets/`'s delta — R2.8
- [x] 2.6 (Unit) Measure `nineslice` per stretched region along its own stretch axis, added as `specs/ui-assets/` delta — R2.9

## 3 · The checks that need more than one image

- [x] 3.1 (Unit) Measure `drift` as the largest distance from a frame's anchor to the set's median anchor — R2.3
- [x] 3.2 (Unit) Measure `flicker` as small colour changes at unchanged alpha between adjacent frames, told apart from motion — R2.6
- [x] 3.3 (Unit) Measure `bleed` as the count of cells whose content touches a shared boundary, keying on chroma where there is no alpha — R2.2, R3.6
- [x] 3.4 (Unit) Measure consistency across frames — R2.10
  _Reason plan task 10.2 ships the consistency check; this task reaches R2.10 so the spec's traceability holds_
- [x] 3.5 (Unit) Measure scale across the sets of one asset — R2.11
  _Reason plan task 4.3 ships the scale check; this task reaches R2.11 so the spec's traceability holds_

## 4 · The command

- [x] 4.1 (Unit) Read `--in` as one image or a directory of frames, refuse anything else, and refuse an input or a cell past its ceiling — R3.1, R3.5, R3.7
- [x] 4.2 (Unit) Run every applicable check and skip the rest with their reason — R1.1, R1.3, R3.2, R3.3
- [x] 4.3 (Unit) Report the findings as one object and exit `0` whether or not anything was found — R3.4

## 5 · The fixtures that prove it

- [x] 5.1 (Unit) Build and measure a fixture carrying each defect and a clean counterpart, for each of the seven checks — R4.1, R4.2

## Notes

**Five tasks were planned `(TDD)` and were built `(Unit)`, and the labels now say so.**
The detectors were written before their tests. The annotation is the authoritative
record of which cycle ran, so leaving `(TDD)` on the checklist with the truth in a
footnote would have been the checklist lying. They are relabelled.

What was done instead is worth keeping, because it recovered most of the value: the
tests were written from `requirements.md` rather than from the code, and then the five
detectors' bodies were replaced with `raise NotImplementedError` and the suite re-run.
Every assertion failed, which is the part of red that carries meaning — a test that
still passes with the behaviour absent is testing nothing. Restoring the bodies turned
up **two real defects**: `drift` measured the centre of the bounding box, so a swinging
arm read as the character sliding; and `silhouette` reduced the mask by point sampling,
so whether a one-pixel hole survived depended on where the samples landed. Both are
fixed, and both are recorded in `design.md`.

The risk the `(TDD)` plan was hedging against was real and it partly landed. That is an
argument for keeping the order next time, not for relabelling after the fact — which is
why this note stays.

**Why five were planned TDD: this leaf is a measuring instrument.** Every later leaf is
judged against these numbers, so a detector that is confidently wrong is worse than one
that is missing — `doctor` being right is the precondition for "measure, don't guess"
meaning anything here. `pixel_grid`, `silhouette`, `drift`, `flicker` and `bleed` are
the five whose correctness is not obvious from reading them.

**Task 2.4 settles a question the plan left open.** `silhouette` had no metric;
`design.md` adopts mask integrity at the target cell and rejects outline readability, and
says what that costs. Worth surfacing before it lands: it is the one decision here that
closes off an option rather than implementing one.

**Task 5.1 is last and it is not a formality.** The fixtures are the asset — `doctor` is
validated against those exact numbers and everything downstream depends on `doctor` being
right, so they are never regenerated to make a test pass.
