---
autonomy: auto
ci: wait
---

# Background removal — requirements

## Purpose

`ssc tool bgremove` takes a background out by chroma key: local, free, deterministic, and
usable on a directory of loose PNGs with no workspace. It is the free path to a transparent
background — `gen bgremove` (a hosted model) and `tool bgremove --model` (a local one) are
later leaves, and both cost something this one does not.

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

## R4 · Reporting

- **R4.1** When it removes a background, the `ssc` CLI shall report how many pixels it made transparent and how many it left opaque.

## Out of scope

- **Removing a background by model.** `--model birefnet|rembg` under the `[cv]` extra is
  `specs/cv-background-removal/`, and `gen bgremove` over a hosted model is
  `specs/gen-fal/`. This leaf is the chroma path, which needs neither a download nor a key.
- **Choosing the key for the caller.** Detecting which colour the background *is* would be
  a guess, and a wrong guess eats the character. The key is given, and `green` is a default
  rather than an inference.
- **Soft alpha.** R3.1 is deliberate and not a simplification: a feathered edge is `halo`,
  which `doctor` reports as a defect. A tool whose output failed the project's own detector
  would be the wrong kind of clever.
