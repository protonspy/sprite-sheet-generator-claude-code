---
autonomy: auto
ci: wait
lang: en
---

# Box art — requirements

## Purpose

Two decisions sit in front of the first paid call of a character: what the character *is*,
and how it is drawn. `specs/generation-style/` made the second one askable. This is the
first: a concept piece at full fidelity, generated so a person can look at one image and
say *yes, that is the wizard* before any money is spent deriving four directions and five
animations from a silhouette nobody signed off on. It exists only where there is nothing to
derive from — a caller who already has art has answered the question box art asks — and the
sprite is derived from it afterwards rather than generated again. A game can show it, which
is the second reason it is a stage of the asset rather than a throwaway.

## R1 · The concept piece

- **R1.1** When `ssc gen boxart` runs, the `ssc` CLI shall generate one approval image for the asset and record it as a stage of that asset.
- **R1.2** The `ssc` CLI shall generate it with the `box-art` prompt template, whatever template the asset's kind names.
- **R1.3** The `ssc` CLI shall generate it at the cell the `box-art` kind declares, whatever cell the asset's own kind declares.
- **R1.4** The `ssc` CLI shall generate it at concept-art fidelity, and never in the style the asset is drawn in.
- **R1.5** The `ssc` CLI shall report which command derives the sprite from what it produced.

## R2 · Only where there is nothing to derive from

- **R2.1** If a reference image is given to `ssc gen boxart`, then the `ssc` CLI shall refuse the call, because a caller holding art has already answered the question box art asks.
- **R2.2** If the asset already holds box art, then the `ssc` CLI shall refuse rather than generate a second piece.

## R3 · Where box art must not go

- **R3.1** If box art is named as the image a sprite is generated from, then the `ssc` CLI shall refuse the call and name what to do with it instead.
- **R3.2** Where a generation transforms box art into box art rather than into a sprite, the `ssc` CLI shall allow it.

## Out of scope

**The approval itself.** Box art is generated for a person to look at, and holding that
decision as state in the workspace is a gate — `specs/generation-gates/`, which carries the
box-art gate as its first subject. This leaf produces the image and records it; nothing here
stops the next command running.

**Deriving the sprite.** `ssc tool pixelart` already converts art of any origin into pixel
art, and pointing at it is all this leaf does. A second conversion path that only box art
can use would be the copy that drifts.

**Generating box art for a kind that is not a character.** Nothing refuses it — the command
takes any asset — but the templates, the cell and the whole argument are about a character,
and a tile with a concept piece is a caller doing something this leaf did not design for.
