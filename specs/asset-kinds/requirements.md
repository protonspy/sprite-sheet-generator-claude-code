---
autonomy: auto
ci: wait
---

# Asset kinds — requirements

## Purpose

A kind is what makes an asset mean something. `workspace-foundation` records the name; this
leaf is the profile behind it — cell, anchor, whether it animates, atlas layout, which
`doctor` checks apply, which generation template to use.

It is a **profile and not a closed enum**, which is the hard-to-reverse part and has its own
record: `adr:0008-a-kind-is-a-profile-not-an-enum`. The rest of M2 consumes this, so it is
first.

## R1 · What a profile is

- **R1.1** (MODIFIED) The `ssc` CLI shall give every kind a cell size, an anchor mode, whether it animates, an atlas layout, the `doctor` checks that apply to it, a generation template, and whether its assets are layered — see `specs/parallax-layers/` for that last field.
- **R1.2** (MODIFIED) The `ssc` CLI shall ship built-in profiles for `character`, `icon`, `tile`, `ui`, `banner`, `map` and `background`.
- **R1.3** Where `ssc.yaml` declares a kind, the `ssc` CLI shall use that declaration.
- **R1.4** Where a declared kind names a built-in, the `ssc` CLI shall use the declared value for each field it states and the built-in's for each it does not.
- **R1.5** If a declared kind states a field the profile does not have, or a value the field cannot take, then the `ssc` CLI shall exit `1` and name the kind and the field.

## R2 · Discovering them

- **R2.1** When `ssc kind list` runs, the `ssc` CLI shall report every kind available, built-in and declared.
- **R2.2** When `ssc kind show <name>` runs, the `ssc` CLI shall report that kind's resolved profile.
- **R2.3** When it reports a resolved profile, the `ssc` CLI shall report for each field whether it came from the built-in or from `ssc.yaml`.
- **R2.4** If the named kind is neither built-in nor declared, then the `ssc` CLI shall exit `2` and report the kinds there are.

## R3 · Using them

- **R3.1** Where a command needs a kind's profile, the `ssc` CLI shall read it rather than deciding from the kind's name.
- **R3.2** Where `ssc asset new` is given a kind, the `ssc` CLI shall accept any kind that resolves and refuse one that does not.

## Out of scope

- **What the other fields do.** This leaf declares the atlas layout, the applicable checks
  and the template, and reads them back. Packing an atlas is `specs/atlas-packing/`, the
  `seam` and `nineslice` checks are `tile-assets` and `ui-assets`, and the template is
  `specs/gen-fal/`. A field nobody consumes yet is still declared here, because the leaves
  that consume it must not each invent its name.
- **`background` as N layers.** `specs/parallax-layers/` is a kind whose asset is not one
  image, and it needs more than a profile field.
