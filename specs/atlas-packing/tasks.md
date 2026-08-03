# Atlas packing — tasks

**What already covers these paths:** `tests/cli/test_recover_commands.py` covers `tool pack`
end to end — the cell grid, `--cols`, `--cell`, the anchor it reports and the refusals it
raises — and that command is the one growing `--atlas`. `tests/core/test_assemble.py` covers
`pack`, `MAX_CANVAS` and `CanvasTooLarge`, which this reuses; `tests/cli/test_kinds.py`
covers profile resolution, which R3.1 reads. All were run green before this work started.

## 1 · Placing

- [x] 1.1 (TDD) Place a set of sizes on shelves — sorted by height then id, no two rectangles overlapping, none outside the atlas — R1.1, R1.5
- [x] 1.2 (Unit) Choose the default width: the smallest power of two that fits the widest entry and keeps the packed height no greater than itself — R1.1
- [x] 1.3 (Unit) Refuse an entry that does not fit the atlas' width, naming it — R1.6
- [x] 1.4 (Unit) Bound the set before the width search runs, and sort it once for the whole search — R1.7

## 2 · The gap

- [x] 2.1 (TDD) Hold `--padding` between every pair of rectangles and at the atlas edge — R2.1
- [x] 2.2 (TDD) Extrude each entry's border outwards, repeating the border pixel and never writing past the padding — R2.2, R2.3
- [x] 2.3 (Unit) Report the rectangle as the entry's own pixels, excluding the extrusion — R2.4
- [x] 2.4 (Unit) Give each refusal its own type, so an out-of-range gap and an over-wide extrusion carry different fixes — R2.5

## 3 · Drawing and identity

- [x] 3.1 (Unit) Draw the placement — one slice per entry, no resample — and report id, rect and anchor per entry — R1.1, R1.2
- [x] 3.2 (Unit) Derive an id from the source filename and refuse a collision, naming both files — R1.3, R1.4

## 4 · The command

- [x] 4.1 (Unit) `ssc tool pack --atlas` with `--padding`, `--extrude` and `--width`, translating each core refusal to its own code and fix — R1.6, R2.3
- [x] 4.2 (Unit) Read the layout from `--kind`'s profile, and refuse an atlas of a kind that animates — R3.1, R3.2

## Notes

**Two tasks are TDD, and both for the same reason: the defect is invisible in the output.**
An overlap in the packing and an off-by-one in the extrusion both produce an atlas that
looks right in a viewer and is wrong on a GPU — a neighbour's pixels sampled at an entry's
edge, at some filtering settings and not others. Writing the assertion first is what forces
it to be about the property (*no two rectangles intersect*, *the extruded pixel equals the
border it came from*) rather than about the numbers one particular run produced.

**The red was observed on all three, and 2.1 caught the defect it was written for.** 1.1 and
2.2 failed on `ImportError` before `core/atlas.py` existed. 2.1 then failed against a
working packer: growing every entry by `padding` on all four sides is the obvious box model,
and it leaves *twice* the requested gap between neighbours while satisfying every
"is there a gap" assertion. The pen starts at `padding` and each entry advances by its own
width plus one gap.
