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
- [x] 2.2 (Unit) Despeckle, then trim, in that order, and clamp a trim that cannot matter — R3.3, R3.4, R3.5

## 3 · The edge

- [x] 3.1 (Unit) Write alpha as 0 or 255 and nothing between — R3.1
- [x] 3.2 (Unit) Take the key's cast out of the pixels bordering the transparent region — R3.2

## 4 · The command

- [x] 4.1 (Unit) Build `ssc tool bgremove` over a frame set, defaulting to flood, reporting what it removed — R2.3, R4.1

## 5 · The model path

_Reason plans/ssc-completion.md tasks 9.1 and 9.2 add `--model` beside the key; R5 is
theirs, and the chroma path above is unchanged by it._

- [x] 5.1 (Unit) Apply a model's matte to a frame, binary and with the same despeckle and trim the key path runs — R5.3, R5.4
- [x] 5.2 (Unit) Load a model under the `[cv]` extra on the resolved device, refusing an absent extra with the install command — R5.1, R5.2, R5.5
  _Depends 5.1_
- [x] 5.3 (Unit) Reuse a cached matte keyed on the frame, the flags and the execution provider — R5.6
  _Depends 5.2_
- [x] 5.4 (Unit) Carry `--model` and `--device` on the command, leaving the key as the default — R5.7
  _Depends 5.2_
