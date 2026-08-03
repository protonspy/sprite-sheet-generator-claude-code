# Background removal — tasks

**What already covers these paths:** `tests/core/doctor/test_checks.py` covers `check_halo`,
which names this command's `--edge-pass` as its fix and so is the test that would notice the
flag being renamed, and it covers `label_regions`/`region_areas`, which the flood and the
despeckle both reuse. `tests/cli/test_frames.py` covers the frame-set reading, the output
refusal and the set ceiling this command inherits, and `tests/cli/test_convert.py` covers the
module the command is added to. All were run green before this work started.

## 1 · The key

- [x] 1.1 (Unit) Resolve the key from a preset or a hex colour, refusing anything else — R1.1, R1.2, R1.4
- [x] 1.2 (Unit) Mark the pixels within tolerance of the key — R1.3

## 2 · What becomes transparent

- [x] 2.1 (Unit) Keep only the key-coloured region reachable from the border, and the global alternative — R2.1, R2.2
- [x] 2.2 (Unit) Despeckle, then trim, in that order — R3.3, R3.4

## 3 · The edge

- [x] 3.1 (Unit) Write alpha as 0 or 255 and nothing between — R3.1
- [x] 3.2 (Unit) Take the key's cast out of the pixels bordering the transparent region — R3.2

## 4 · The command

- [x] 4.1 (Unit) Build `ssc tool bgremove` over a frame set, defaulting to flood, reporting what it removed — R2.3, R4.1
