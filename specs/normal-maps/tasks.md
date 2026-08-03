# Normal maps — tasks

**What already covers these paths:** `tests/cli/test_convert.py` covers the `--in`/`--out`
command shape this joins, including how a set is read and written; `tests/cli/test_frames.py`
covers the reader and the refusal for an input that is neither a file nor a directory. Both
were run green before this work started.

## 1 · The map

- [x] 1.1 (Unit) Build the height field from luminance, filling transparent pixels from their nearest opaque neighbour — R1.2, R1.4
- [x] 1.2 (TDD) Turn slopes into unit normals and encode them, flat where the input is transparent — R1.1, R1.4, R1.6
- [x] 1.3 (Unit) Scale the slope by `--strength`, refusing a value outside its range — R1.3

## 2 · The convention

- [x] 2.1 (Unit) Report the convention encoded, and encode the other one under `--flip-y` — R2.1, R2.2

## 3 · The command

- [x] 3.1 (Unit) `ssc tool normal` over one image or a set, writing a new file per input — R1.1, R1.5

## Notes

**One task is TDD, and it is the encoding.** A normal map that is wrong is not visibly wrong:
it is a plausible lavender image either way, and the defect only appears as light falling
from the wrong side in an engine nobody runs during this work. The properties — every encoded
vector is unit length, a flat region encodes to exactly the flat normal, a slope in one
direction encodes to the opposite side of centre from the same slope reversed — are what a
test can hold that an eye cannot.

**The red was observed on 1.2** — `ImportError` before `core/normal.py` existed. The
property that mattered turned out to be the sign one: `test_a_slope_and_its_reverse_land_on
_opposite_sides_of_centre` is what a reversed gradient would fail, and a reversed gradient is
the defect nobody sees until an engine lights the sprite from the wrong side.
