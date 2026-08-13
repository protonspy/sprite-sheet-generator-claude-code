# CLAUDE.md

## The project

This workspace is built by `ssc`, the sprite sheet generator. It turns AI-generated art
into game-ready 2D assets: real pixels on a real grid, aligned frames, a transparent
background, metadata an engine can read. The art arrives with defects — fake pixels,
frame bleeding, drift, halos, palette drift, flicker, seams — and each one is **measured**,
then **repaired** with the command that fixes it. Never a judgement about whether art
"looks right": read the numbers and run the named command.

## The domain

- **Asset** — one piece of work, at `assets/<kind>/<key>/`, with `meta.json` recording
  each file's stage, class (`source` / `derived` / `output`) and provenance. A file's
  three-digit prefix orders a chain; a stage name is its address.
- **Kind** — the profile behind an asset: cell size, anchor, frame rate, applicable
  `doctor` checks, generation template. The package ships `character`, `icon`, `tile`,
  `ui`, `banner`, `map`, `background` and `box-art`, and **a kind is a profile rather than
  a closed set** — a project declares its own under `kinds:` in `ssc.yaml`, or overrides
  one field of a built-in and inherits the rest. `ssc kind list` is what this workspace
  actually has; `ssc kind show <name>` says where each field came from.
- **The run** — a run goes from nothing to `dist/index.json`, one recorded stage at a
  time: anchor → directions/cycles → cleanup → style → integrate. Four per-type skills
  (`sprite-sheet`, `sprite-icons`, `sprite-tilemap`, `sprite-ui`) each drive a whole run
  end to end for one kind of creation; `ssc tool doctor` measures at each point.
- **Two rules of the trade**: every resize is **nearest neighbour** — one bilinear resize
  undoes the pixel pipeline; and a hard guide (a nine-patch line) sits **on the pixel
  grid**, never inside a block.

## Measuring — `ssc tool doctor`

It takes no asset argument. `--in` is a file or a directory of frames and is repeatable;
the first set is what gets measured, and the rest are the asset's other animations, which
only the cross-set `scale` check looks at. `--kind` runs the checks that kind's profile
declares.

```
ssc tool doctor --in assets/character/hero/030-cut/
ssc tool doctor --in .../walk/ --in .../idle/ --kind character
```

Every check reports, including the ones that found nothing and the ones that did not run:
a report that omits what it did not measure is indistinguishable from a clean one. Nine
checks are always on. **`seam` and `nineslice` have to be asked for** — with `--check
seam`, `--check nineslice`, or by naming a `--kind` whose profile declares them — and they
report `skipped` otherwise, which does **not** mean clean.

The `fix` on a finding is the command to run. It is the authority; this table is a map:

| Check | What it means | Fix |
|---|---|---|
| `pixel_grid` | fake pixels — art that only looks pixelated | `ssc tool snap` |
| `bleed` | a frame carrying its neighbour's pixels | `ssc tool cut --mode islands` |
| `drift` | frames of one cycle not on one anchor | `ssc tool align --anchor feet` |
| `halo` | a ring of the key colour around the cut-out | `ssc tool bgremove --edge-pass` |
| `palette` | more colours than the project allows | `ssc tool pixelart --colors` |
| `flicker` | a still region changing between frames | `ssc tool pixelart`, one palette for the set |
| `silhouette` | holes, or the subject in fragments | `ssc tool bgremove --tol` |
| `consistency` | the shape wandering across the set | `ssc tool align --anchor feet` |
| `scale` | the asset's sets drawn at different sizes | `ssc tool normalise` |
| `seam` | a tile that does not meet itself — **opt-in** | `ssc tool tile` |
| `nineslice` | a panel whose guides an engine cannot stretch — **opt-in** | `ssc tool ninepatch` |

`consistency` and `scale` need more than one thing to compare — two frames, and two sets —
and skip rather than fail on less. `consistency` reports a number and calls it a defect
only where `--min-consistency` gave it a line to fall below.

## Driving `ssc`

`tool` commands are local, free, synchronous; `gen` commands bill the provider. Every
command emits **one JSON object** on stdout. Exit codes: `0` ok, `1` error, `2` invalid
usage, `3` a gate is pending. `--dry-run` writes nothing. Nothing overwrites — a mistake
is `git checkout`.

`ssc --help` and `ssc tool --help` list everything. The commands that carry a run:

- **`ssc run <address>`** drives the pipeline for an asset and stops at the next decision.
  **`ssc status <address>`** says where it got to and what runs next. Start with `status`.
- **`ssc gate`** is what exit `3` means. A gate is a decision reserved for a human, held as
  state in the workspace: `ssc gate list`, `ssc gate open`, then `approve` or `reject`.
  **You do not decide at a gate** — surface it and wait. Nothing past it runs until it is
  settled.
- **`ssc job`** owns paid work that outlived its command. `gen` with `--no-wait` submits
  and returns; the result is collected with `ssc job status`, `wait` or `resume`, and
  `ssc job list` finds one you lost. A job submitted and never collected was paid for and
  thrown away.
- **`ssc asset new`** creates the asset, **`ssc index`** builds `dist/`, **`ssc preview`**
  renders what the index declares, **`ssc budget`** reports what was spent, and
  **`ssc clean`** deletes derived files only.

## Choosing a model

`ssc model list` names every model, the media it makes, which one is the default and which
have a published price. `ssc model show <id>` gives one model's options with their types and
ranges, plus the provider's own price text. That text is **indicative** — it is the sentence
the provider published, not a quote, and `ssc` parses no number out of it. What a run cost
is what `ssc budget` recorded.

Defaults, used when neither `ssc.yaml` nor the kind names a model:

- **image** — `openai/gpt-image-2`
- **video** — `xai/grok-imagine-video/image-to-video`

Four options move what a call costs, and they are the four to decide **before** spending:

- `--count` — multiplies it outright. Four images cost four times one.
- `--size` — a larger tier costs more, and past the kind's cell size it buys nothing: the
  frame is downsampled to the grid anyway.
- `--quality` — where the model has one. The steepest lever on GPT Image 2, which bills by
  token and defaults to `high`.
- `--seconds` — video only, and video is priced per second of output.

Match them to the work rather than to a habit:

- **The frame everything else derives from** — the anchor — is the one to pay properly for:
  one image, the quality up, the size the kind asks for. A wrong anchor wastes every paid
  call after it.
- **Choosing between candidates** is the opposite call: raise `--count`, drop `--quality`
  and the size tier. You are judging a composition, not shipping pixels; regenerate the one
  you picked at full quality. `ssc tool sweep` runs that comparison across a `tool`
  parameter for nothing.
- **Anything a `tool` command can do is not a paid call.** `tool recolour` makes a variant,
  `tool style` restyles. Reaching for `gen` where a `tool` exists is the commonest way to
  pay for something this workspace already had.
- **Video costs by the second.** Generate the shortest clip that shows the cycle and loop
  it, rather than a long one to cut down.

### Background removal — three paths, and only one of them bills

1. `ssc tool bgremove` keys on chroma. Local, free, deterministic, microseconds. Wants a
   flat backdrop.
2. `ssc tool bgremove --model birefnet` — or `rembg`. **Also local and also free**, under
   the `[cv]` extra, on whatever `--device` resolves to. Wants no flat backdrop.
3. `ssc gen bgremove` is the hosted one and the only one that costs. It runs
   `fal-ai/birefnet/v2` — **the same model as path 2**, with no published price.

So reach for `gen bgremove` only where the `[cv]` extra is not installed and cannot be.
`ssc info` says what this machine can run.

### `--opt` is for what no core option covers

`--count`, `--size`, `--quality`, `--seconds`, `--seed` and `--format` are the core options,
and each maps onto whatever the chosen model calls that field. **A core option silently wins
over an `--opt` naming the same field** — `--opt duration=5` is `--seconds 5` written the way
that can be overwritten. Use `--opt` for fields no concept covers:

```
ssc gen video --seconds 5 --opt resolution=720p
```

A model that maps no `--size` — the three image-to-video models other than the default do
not — still takes its own fields this way, checked against its schema. `ssc model show <id>`
lists what each accepts.

## Skills — `.claude/skills/`

The runs the harness drives live here: `sprite-sheet`, `sprite-icons`, `sprite-tilemap`,
`sprite-ui`. Each owns the whole run for one kind of creation — an animated sheet, a set
of icons, a tile set, a stretchable panel. When one of those is next, open its `SKILL.md`
and follow it.
