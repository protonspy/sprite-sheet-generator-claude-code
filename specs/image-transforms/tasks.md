# Image transforms — tasks

**What already covers these paths:** `tests/core/test_assemble.py` covers `flip` and the
anchor that `pack` records; `tests/cli/test_recover_commands.py` covers `tool mirror` end to
end; `tests/test_no_other_resampler.py` is the invariant R1.3 exists to keep, and it fails
the suite on any resampler this work might reach for. Run all three before starting.

## 1 · The transforms

- [ ] 1.1 (Unit) Mirror about either axis, defaulting to the vertical one so every existing call keeps its meaning — R1.1, R1.4
- [ ] 1.2 (Unit) `ssc tool rotate` by one, two or three quarter turns, refusing any other angle with the resampler as the stated reason — R1.2, R1.3, R1.4
- [ ] 1.3 (Unit) `ssc tool trim` to one box covering every frame's opaque pixels, never a box per frame — R1.5
- [ ] 1.4 (Unit) `ssc tool offset` by a whole number of pixels on either axis — R1.6

## 2 · What travels with the pixels

- [ ] 2.1 (TDD) Move the recorded anchor by the same transform as the frames — R2.1
- [ ] 2.2 (Unit) Report the dimensions an odd quarter turn produced and the cell they stopped matching — R2.4
- [ ] 2.3 (Unit) Record the transform in the written file's provenance — R2.3
- [ ] 2.4 (Unit) Move per-frame boxes and markers by the same transform — R2.2

## Notes

**Why this is worth a command at all: the flip is the saving.** East is a horizontal flip of
West, and flipping is free where generating is not — `docs/wiki/anchor-and-directions.md`
records it and `specs/budget-guard/` R3.1 turns it into a refusal, so `gen image` asked for
an East anchor that West already covers answers with `tool mirror` instead of billing. That
half already exists. What this spec adds is the other axis and the quarter turn, which
nothing offers today and which `tile` and `map` work needs.

**2.1 is the TDD task, and it is one line of arithmetic.** Mirroring moves a pixel at `x` to
`width - 1 - x`. Drop the `- 1` and every sprite sits one pixel off — which does not look
like an error, it looks like a character that jitters when it turns, and it is invisible
until someone zooms in. Small, exact, high cost of being wrong: the trigger is risk, not
size.

**2.4 cannot be finished before `specs/frame-metadata/` exists.** The requirement is written
here anyway, because the transform is where per-frame boxes rot silently — a mirrored frame
with an unmirrored hurt box is a character that takes damage on the wrong side. Leaving R2.2
out would mean that leaf lands and someone has to remember this command exists. Ticking 2.4
waits for it; the rest of this spec does not.

**`trim` and `offset` are here to stop being implicit.** Both already happen — inside `align`
and inside `pack` — and the plan's own complaint about `expand` applies word for word: an
implicit operation writes no `meta.json` entry, so it cannot be reproduced or debugged. Making
them commands does not add behaviour, it makes behaviour that already runs visible in a
lineage.

**Nothing here is implemented.** This spec is a map: it was written to record the decisions
while they were in hand, and the order it lands in relative to M4 is the plan's to say.
