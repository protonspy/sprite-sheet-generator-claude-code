---
autonomy: auto
ci: wait
---

# Background removal — requirements

## Purpose

`ssc tool bgremove` takes a background out by chroma key: local, free, deterministic, and
usable on a directory of loose PNGs with no workspace. The key is the cheap path — it needs
a flat backdrop and answers in microseconds. `--model` (R5) is the same command over a
local model: also free, and paid for in a download and in seconds a frame instead. Only
`gen bgremove`, over a hosted model, bills.

Two things make it more than a colour comparison. **A green gem inside a character is not
the background**, so matching every pixel of the key colour is the wrong default; only
background reachable from the border is. And **alpha in pixel art is binary** — a
half-transparent fringe is the `halo` defect `doctor` already measures, and it already names
`ssc tool bgremove --edge-pass` as the fix, so this leaf owes exactly that flag under exactly
that name.

## R1 · The key

- **R1.1** The `ssc` CLI shall accept the key as a 6-digit hex colour or as one of the presets `green` and `magenta`.
- **R1.2** Where no key is given, the `ssc` CLI shall use `green`.
- **R1.3** The `ssc` CLI shall treat a pixel as key-coloured when its distance from the key is within the given tolerance.
- **R1.4** If the key is neither a preset nor a 6-digit hex colour, then the `ssc` CLI shall change nothing and exit `2`.

## R2 · What becomes transparent

- **R2.1** Where `--mode flood` is given, the `ssc` CLI shall make transparent only the key-coloured region reachable from the image border.
- **R2.2** Where `--mode global` is given, the `ssc` CLI shall make transparent every key-coloured pixel.
- **R2.3** The `ssc` CLI shall use `flood` unless `global` is asked for.

## R3 · The edge

- **R3.1** The `ssc` CLI shall give every pixel it writes an alpha of either 0 or 255.
- **R3.2** Where `--edge-pass` is given, the `ssc` CLI shall remove the key colour's contribution from the pixels bordering the transparent region.
- **R3.3** Where `--edge-trim` is given, the `ssc` CLI shall shrink the opaque region by that many pixels.
- **R3.4** Where `--despeckle` is given, the `ssc` CLI shall make transparent every opaque group smaller than that many pixels.
- **R3.5** If `--edge-trim` is past the trim ceiling, then the `ssc` CLI shall change nothing and exit `2`.

## R4 · Reporting

- **R4.1** When it removes a background, the `ssc` CLI shall report how many pixels it made transparent and how many it left opaque.

## R5 · Removing a background by model

- **R5.1** (ADDED) Where `--model birefnet` or `--model rembg` is given, the `ssc` CLI shall cut the subject out with that model instead of by chroma key.
- **R5.2** (ADDED) If the `[cv]` extra is not installed, then the `ssc` CLI shall change nothing and shall refuse with the command that installs it.
- **R5.3** (ADDED) When it cuts a frame out with a model, the `ssc` CLI shall give every pixel it writes an alpha of either 0 or 255, as R3.1 requires of the chroma path.
- **R5.4** (ADDED) Where `--edge-trim` or `--despeckle` is given with `--model`, the `ssc` CLI shall apply them to the model's matte as it applies them to the key's.
- **R5.5** (ADDED) Where `--device` is given, the `ssc` CLI shall run the model on that device, and shall report the execution provider it ran on.
- **R5.6** (ADDED) While the command is standing in a workspace, the `ssc` CLI shall reuse a cached matte keyed on the frame, the flags and the execution provider.
- **R5.7** (ADDED) The `ssc` CLI shall remove by chroma key unless `--model` is given.

## Out of scope

- **Removing a background over a hosted model.** `gen bgremove` bills and returns a job,
  and `specs/gen-fal/` owns it. `--model` here is local and free: it costs a download
  rather than a credential, which is why both live under `tool`.
- **Choosing the key for the caller.** Detecting which colour the background *is* would be
  a guess, and a wrong guess eats the character. The key is given, and `green` is a default
  rather than an inference.
- **Soft alpha.** R3.1 is deliberate and not a simplification: a feathered edge is `halo`,
  which `doctor` reports as a defect. A tool whose output failed the project's own detector
  would be the wrong kind of clever.
