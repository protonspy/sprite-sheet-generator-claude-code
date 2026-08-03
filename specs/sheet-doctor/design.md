# Sheet doctor — design

## What changes

Serves R1.1–R1.5, R2.1–R2.7, R3.1–R3.5, R4.1–R4.2.

Seven pure detectors under `src/ssc/core/doctor/`, one command over them, and the fixtures
that prove each one.

```
src/ssc/core/doctor/
  finding.py      Check, Severity, Finding, Report — the shapes every detector returns
  masks.py        alpha mask, bounding box, anchor, connected components — shared, tested once
  pixel_grid.py · bleed.py · drift.py · halo.py · palette.py · flicker.py · silhouette.py
src/ssc/cli/commands/doctor.py
tests/fixtures/doctor/     one input carrying each defect, one free of it
```

The detectors are pure — `ndarray` (or a list of them) plus a params dataclass in, a
`Finding` out — because `specs/asset-listing/` has to call the same measurement without a
CLI, and because a detector that can be tested against an 8x8 array is a detector whose
fixture numbers mean something.

**Every check returns a finding, including when it is clean.** A report that omits what it
did not find is indistinguishable from a report where the check never ran, and R1.3 makes
"skipped, and why" a first-class outcome rather than silence.

## Boundaries and contracts

**A finding is a measurement, a severity and a fix.** The `fix` field is the same one
`SscError` already carries, deliberately: a harness that knows what to do with a refusal
knows what to do with a defect.

```json
{
  "check": "halo",
  "status": "defect",
  "measurement": {"semi_transparent_px": 412, "ratio": 0.0063},
  "fix": "ssc tool bgremove --edge-pass"
}
```

`status` is `ok`, `warning`, `defect` or `skipped`. A skipped check carries `reason` and no
measurement; nothing else in the shape changes, so a caller reads one structure.

**`doctor` never repairs and never mutates.** It opens files read-only and writes nothing,
which is why it is the one `tool` command with no `--out`.

**Thresholds are parameters, not truths.** Each detector takes the number that separates
`ok` from `defect` in its params dataclass with a documented default. The defaults come
from the fixtures, and the fixtures are what a change to a default has to be argued
against.

## Data

**Input shapes.** `--in` names either one image or a directory. A directory is read as a
frame set, sorted by filename, which is what `drift` and `flicker` need — they are the two
checks that cannot be computed from a single image and are skipped when given one.
`bleed` is the mirror case: it needs a grid, so it is skipped unless `--cols` and `--rows`
say what the grid is.

| Check | Needs | Skipped when |
|---|---|---|
| `pixel_grid` | one image | never |
| `halo` | one image with alpha | the image has no alpha channel |
| `palette` | one image | never; the off-palette count needs `--palette` |
| `silhouette` | one image with alpha, and `--cell` | no alpha, or no `--cell` |
| `bleed` | a sheet plus `--cols`/`--rows` | the grid was not given |
| `drift` | two or more frames | one image |
| `flicker` | two or more frames | one image |

## Settling `silhouette`

The plan names this check without defining it, and `docs/wiki/game-ready-defects.md` says
plainly that until this spec settles it, nobody should assume a metric. Two readings were
on the table and they catch different failures: **readability of the outline at the size
it is played at**, and **integrity of the alpha mask**.

**Readability is not adopted, and that is the substance of the decision.** Every candidate
number for it — ink coverage, perimeter complexity, how much detail survives a reduction —
is a proxy standing in for a person's judgement about whether a shape reads. The knowledge
base is explicit that a check reporting a number nobody defined is "a judgement wearing a
number's clothes", and it would be the one entry an agent could not act on. The
photorealistic-blob case that reading was meant to catch is not left uncovered: it has no
pixel grid, so `pixel_grid` reports it, and where it needs a human it gets one at the
review gate `specs/sweep-and-review/` exists for.

**Mask integrity is adopted, measured at the target cell.** Two exact counts, on the alpha
mask reduced with nearest neighbour to `--cell`:

- **`holes`** — connected background regions fully enclosed by the body. This is
  background removal that took too much, which pairs `silhouette` with `halo` from the
  opposite side: `halo` is removal leaving too much.
- **`fragments`** — separate opaque regions above a minimum area. A silhouette that broke
  into islands is a body that stopped being one shape.

Reducing to `--cell` first is what keeps the "at the size it is played at" half of the
name honest without importing its judgement: a hole two pixels wide in a 1024px render
that vanishes at 64px was never a defect, and one that survives the reduction is.

**The reduction takes the majority of each source block, not a sample of it.** Nearest
neighbour is the project's rule for resizing an *image*, and it is the wrong tool here:
point sampling makes a one-pixel hole's survival depend on where the sample points
happened to land, and a measurement may not depend on that. A majority over the block is
deterministic and answers the question the check is asking — does this feature still cover
a pixel at the played size. It also cannot violate the invariant the rule exists for: the
output is boolean, so there is no intermediate value to invent. This was found by the test
for it, not by reading the code.

`--cell` is required rather than defaulted, because a default here would silently decide
the project's visual era — a decision `docs/wiki/pixel-snapping.md` places at project
level, not per check.

This is cheap to reverse — one detector, one fixture — so it is settled here rather than in
an ADR. What it costs is recorded above so the next reader can weigh it rather than
rediscover it.

## Alternatives considered

**One number per check versus a structured measurement.** A single float per check would
make a report trivially comparable across runs, and it was rejected: `pixel_grid` has to
say *what* pixel size it detected, not only how far off the grid the image is, because the
detected size is what `snap` is then told to use. A measurement object costs a caller
nothing and carries the value the next command needs.

**Detecting the sheet grid instead of taking `--cols`/`--rows`.** Auto-detection is real
work and it belongs to `specs/frame-recovery/`, which owns grid detection for exactly this
reason. Duplicating it here would give the project two detectors that could disagree, and
the disagreement would surface as a `bleed` number nobody could reproduce.

## Risks

- **`flicker` and motion look alike at the pixel level.** The separation is that
  re-quantization moves a colour a little and motion moves it a lot, which is a threshold,
  and a threshold is a place to be wrong. The fixtures carry both a flickering set and a
  moving one so the number has to distinguish them, rather than the threshold being argued
  in the abstract.
- **`pixel_grid` on art that is not pixel art at all** — a photograph has no grid, and the
  detector will report some pixel size for it. The measurement is reported alongside the
  conformity share precisely so that a nonsense size is visible as a low conformity rather
  than passing as a fact.
