# Parallax layers — tasks

**What already covers these paths:** `tests/cli/test_kinds.py` covers profile resolution,
the built-in table and the refusal for an unknown field — all of which the `layered` field
and the `background` built-in join. `tests/cli/test_frames.py` covers reading a directory as
an ordered set, which is where the layer order comes from. Both were run green before this
work started.

## 1 · The kind

- [x] 1.1 (Unit) Add `layered` to the profile and `background` to the built-ins, as a delta against `asset-kinds` — R1.1, R1.2

## 2 · The stack

- [x] 2.1 (Unit) Report the layers in order with their files and scroll factors — R2.1, R2.2
- [x] 2.2 (Unit) Derive a factor per layer from its position when none is given — R2.3
- [x] 2.3 (Unit) Refuse a factor outside zero to one, layers of differing size, and a count that does not match — R2.4, R2.5, R2.6

## Notes

**No task here is TDD, and that is the annotation being used rather than skipped.** There is
no algorithm in this leaf: no pixel is read, no geometry is computed, and the arithmetic is
one division. The risk that mandates TDD — money, a complex algorithm, a hypothesis — is
absent, and writing a failing test for "the layers come back in the order they went in"
first would be ceremony rather than evidence.
