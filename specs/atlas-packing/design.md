# Atlas packing — design

## What changes

Serves R1.1, R1.2, R1.3, R1.5, R2.1, R2.2, R2.4, R3.1.

A new pure module, `core/atlas.py`, and a `--atlas` mode on the existing `tool pack`.

`core.atlas.place()` takes the entries' sizes and returns where each one goes; nothing else
in it touches pixels. `core.atlas.draw()` takes the placement and the images and writes the
atlas — one `np.ndarray` slice assignment per entry, and one per extruded edge. The split is
the same one this codebase already makes between `plan_alignment` and the move it plans:
the arithmetic is what the tests are about, and it is testable against integers with no
images at all.

`cli/commands/recover.py`'s `pack_sheet` grows `--atlas`, `--padding`, `--extrude`,
`--width` and `--kind`. Without `--atlas` it is exactly the command that exists today, cell
grid and all — the two layouts are one command because they answer the same question
("assemble this set into one image") and a caller choosing between them is choosing a
layout, not a tool.

**The shelf, not a skyline.** Entries are sorted by height descending, id ascending, and
laid left to right on shelves as tall as the first entry on each. It wastes the space above
a short entry on a tall shelf, and that is the trade taken deliberately: a skyline or
MaxRects packer is a few hundred lines whose correctness is not readable, and this leaf's
inputs are icons and map pieces — sets of tens, mostly of similar height, where the shelf's
waste is small and its determinism is free. R1.5 falls out of the sort rather than being
arranged for.

**Sorted by size, addressed by name.** The placement order is by height because that is what
packs well; the *id* is the source filename's stem, so an entry keeps its name when the set
changes around it. Position and identity are deliberately not the same thing here, and that
is the difference from the cell grid, where the index *is* the identity.

**The width is a power of two; the height is whatever was used.** A power-of-two width is
free to give and some engines still want it; padding the height to match would waste up to
half the file for nothing this project needs. The default width is the smallest power of two
that both fits the widest entry and leaves the packed height no greater than itself, which
lands on a roughly square atlas without asking. `--width` overrides it, and an entry that
does not fit that width is R1.6's refusal rather than a silent widening.

## Boundaries and contracts

Serves R1.6, R2.3, R3.2.

`core/atlas.py` is pure, per `.claude/rules/project.md`: `ndarray` in, `ndarray` out, and
`ValueError` for a refusal. The three refusals — an entry that does not fit, an extrude
wider than the padding, a duplicate id — are raised there and translated to `UsageError` in
`cli/`, the same way `CanvasTooLarge` already is.

`MAX_CANVAS` from `core/assemble.py` bounds the atlas, imported rather than redefined. It is
the same reason that constant exists: `--width` multiplied by a computed height is another
value that multiplies into an allocation.

The kind is read through `kinds.resolve`, and only two of its fields are consulted:
`atlas_layout` picks bin or grid, and `animates` is R3.2's refusal. Nothing here reads
`cell` — an atlas has no cell, and taking one from the profile would produce a grid pack
wearing an atlas' name.

## Data

Serves R1.2, R2.4.

One new shape, reported per entry and carried into `dist/index.json` by
`specs/engine-index/` later:

```json
{ "id": "sword", "rect": {"x": 0, "y": 0, "width": 24, "height": 32},
  "anchor": {"x": 12, "y": 31} }
```

The rectangle is the entry's own pixels. Padding is not in it, and neither is the extrusion —
an engine drawing the extruded border draws a smear of the edge pixel, which is exactly the
artefact extrusion exists to keep *out* of the sampled area (R2.4).

The anchor is per entry and relative to the entry's own rectangle, not to the atlas.
Different-sized entries cannot share one anchor, which is the whole reason they are not a
cell grid; and an anchor in atlas coordinates would change every time the packing changed,
which would make R1.3's stable id pointless.

## Risks

**Extrusion is invisible in review.** An off-by-one that extrudes from the wrong row, or
writes one pixel into a neighbour's rectangle, looks correct in any viewer and produces a
wrong-coloured seam at runtime on some GPUs and not others. It is why R2.2 and R2.3 are
built TDD, and why the test asserts the extruded pixels *equal the border they came from*
rather than merely being non-transparent.
