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

- **R1.1** (MODIFIED) The `ssc` CLI shall give every kind a cell size, an anchor mode, whether it animates, a frame rate, an atlas layout, the `doctor` checks that apply to it, a generation template, whether its assets are layered, and the model it generates each media with — see `specs/parallax-layers/`, `specs/model-registry/` and `specs/engine-index/` for the last three.
- **R1.2** (MODIFIED) The `ssc` CLI shall ship built-in profiles for `character`, `icon`, `tile`, `ui`, `banner`, `map`, `background` and `box-art`.

> **`box-art` added by `specs/gen-fal/`'s prompt templates, and it is the first built-in that
> is not a game asset.** It is the roster and character-select illustration: painterly, at
> portrait size, keeping its own setting rather than a chroma key, because it is never cut
> out. Its `checks` are empty because none of them apply — every check `doctor` ships
> measures a property of a pixel-art sprite, and a rendered illustration is none of those.
>
> **What that buys today is less than the field promises, and the gap is worth naming rather
> than discovering.** R1.1 says `checks` is "the `doctor` checks that apply to" a kind.
> `doctor` reads it to decide whether `seam` and `nineslice` run, and nothing else — the
> other seven run whatever the kind says. So `checks=()` opts `box-art` out of two checks and
> does not stop `pixel_grid` reporting a painterly portrait as off-grid. This is not
> `box-art`'s to fix: `banner`'s `checks=("palette",)` does not suppress `pixel_grid` either,
> and closing it means changing what `doctor` does for every kind, which is `sheet-doctor`'s
> and needs its own delta.
>
> `docs/wiki/anchor-and-directions.md` is equally clear that box art must not then be fed
> back as a sprite reference; that is a rule for the caller, and nothing in the profile
> enforces it.

> **`fps` added by `specs/engine-index/` R4.2, and it is a default rather than the answer.**
> A frame rate is authored per animation in that asset's `asset.yaml`; the profile's is what
> an asset that declares none plays at. It is on the profile rather than as one project-wide
> setting for the reason every other field is: a project's icons and its characters do not
> animate at one speed, and a consumer must not have to branch on the kind's name to find
> that out.
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
