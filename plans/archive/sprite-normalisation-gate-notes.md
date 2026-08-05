# Sprite normalisation gate — sections moved out of the plan

These were in `plans/sprite-normalisation-gate.md` before it moved to the v2 contract, where a plan is a
header and a checklist. Nothing here was changed; it was moved so it could be read,
split into ADRs under `docs/adr/`, or deleted deliberately.

## What already holds

The gate's first two steps are shipped and are not work here. Steps 3 to 6 are, in part or
whole.

| Gate step | Where it lives |
|---|---|
| 1 · Recover frames | `ssc tool cut` / `slice` / `curate` — grid, chroma box, connected components, plus grid auto-detection. `specs/frame-recovery/` |
| 2 · Remove BG | `ssc tool bgremove` — chroma, `flood` by default from the border, `--edge-pass`, `--despeckle`. `specs/background-removal/` |
| 3 · Measure bounds | Nothing addressable. `doctor` and `align` each compute a mask and a bounding box internally; no command reports one. |
| 4 · Height correction | Nothing. `core.resize` is the nearest-neighbour primitive and no command decides a factor from a measurement. |
| 5 · Anchor + pad | Within one set only — `tool align --anchor feet\|bottom\|centre`, `tool expand`, `tool pack`. Across the sets of one asset, nothing. |
| 6 · Rebuild + verify | `tool pack` and `tool pack --atlas` ship. No GIF, no contact sheet: `ssc preview` is named in `specs/engine-index/` and renders from an index that does not exist yet at this point in the pipeline. |
| Failure modes | `drift` and `halo` are `doctor` checks. Inconsistent scale and a frame size that disagrees with the cell are measured by nothing. |


## Notes

**Order is forced, and it is a chain rather than a fan-out.** `frame-bounds` first: it is
the measurement, and both other leaves are written against its output. `set-normalisation`
second — it consumes those numbers and it is where the gate's actual new capability is.
`frame-preview` last, and independent enough of the second that it could run in a parallel
session if someone wants one; it needs nothing from `normalise` except frames.

**`normalise` is not a pipeline command and must not become one.** It normalises the sets of
one asset and stops. Chaining recover → bgremove → bounds → normalise → pack → doctor →
preview is `ssc run`'s job, which is `specs/gates-and-resume/`, and putting a second chainer
under `tool` would give the project two things that sequence commands and no rule for which
one a caller reaches for. What this plan owes the sequence is task 2.1: written down, not
executed by a command.

**The scale factor is the decision this plan cannot pre-empt, and it probably owes an ADR.**
Nearest neighbour is the only resampler (`workspace-foundation` R4.4, enforced by
`tests/test_no_other_resampler.py`), and matching a walk cycle that is 41 pixels tall to an
idle that is 44 needs a factor of 0.93 — which nearest neighbour applies by dropping rows,
destroying exactly the pixel discipline `snap` exists to protect. The three honest answers
are: refuse any factor that is not a whole ratio and report the discrepancy; scale to the
nearest whole ratio and report how far short it fell; or crop and re-anchor instead of
scaling, on the grounds that a three-pixel disagreement is usually a pose rather than a
scale. Which one wins is `set-normalisation`'s to settle with the fixtures in front of it,
and it is hard to reverse once the index carries the result — so it is an ADR, not a
paragraph in `design.md`.

**Two commands will be called `preview`, and that is deliberate.** `ssc tool preview` takes
files and returns files, like every other `tool`; `ssc preview` resolves an asset through
the workspace and reads its playback out of the index. Same verb at two altitudes, the same
split as `tool doctor` against `image show`'s embedded `doctor`. The rule that keeps it
honest is that only one of them renders anything.

**What this plan deliberately does not touch.** `specs/frame-metadata/` stays in M4: the
per-frame alpha box `frame-bounds` produces is the thing that leaf assumed it would derive
for free, and hit boxes, hurt boxes and markers are authored data with nothing to do with
normalisation. `specs/image-transforms/`'s `trim` is adjacent and stays separate — it trims
a set to one box and moves the anchor, and its own scope note already refuses to re-align or
resize afterwards, which is this plan's work rather than its.

**Fixtures.** The `scale` check needs the same treatment as the other seven: a fixture set
of two animations of one character differing by a measured number of pixels in visible
height, and one pair free of it. `.claude/rules/project.md` already forbids regenerating
fixtures with measured defects — these join that set the moment they exist.
