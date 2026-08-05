---
status: accepted
---

# 0012 · Pose rides the onnxruntime runtime, not mediapipe

## Context

The motion-consistency leaf (plan task 10.1) tracks a pose through an animation cycle,
per frame. `docs/stack.md` recorded `mediapipe` as the expected answer while the leaf was
unbuilt, and said the choice earned an ADR when it was built rather than a line that read
like adoption. This is that ADR.

The constraint the rest of M6 put on the table is the one that decides this. `adr:0011`
built a runtime abstraction once — `--device auto|cpu|cuda|directml|coreml`, the
`[cv]`/`[cv-gpu]` extras, the execution provider folded into the cache key — and
`bgremove --model` rides it. Pose tracking depends on 8.3 (provider in the cache key) for
the same reason: a CPU pose and a CUDA pose are two cache entries, not one, because two
providers can differ in the last bit.

`mediapipe` does not ride that runtime. It bundles its own inference framework (Calculator
graph) and its own delegate model, and it does not expose `onnxruntime` execution
providers. Adopting it would mean a second runtime with its own `--device` semantics, a
second cache key story, and a third extra for one leaf — exactly the divergence `adr:0011`
exists to prevent. It is also a heavy dependency (tens of megabytes of framework plus
weights) for a single leaf, which `stack.md` flagged at the time.

## Decision

**Pose runs on `onnxruntime` under the existing `[cv]`/`[cv-gpu]` extras, against an ONNX
model downloaded on first use. No new extra, no second runtime.**

- **The model is MoveNet SinglePose Lightning** (`Xenova/movenet-singlepose-lightning` on
  Hugging Face), 17 COCO keypoints, the smallest model that answers on a CPU box. It is an
  ONNX file, so `onnxruntime.InferenceSession` loads it with whatever provider `--device`
  picks — the same call `bgremove` makes through `rembg`, minus `rembg`.
- **Weights download once to a per-user cache** (`LOCALAPPDATA/ssc/models` on Windows,
  `~/.cache/ssc/models` elsewhere), not per workspace. A one-time cost is not a per-`init`
  cost, and a workspace that re-downloaded on every setup would be the thing this exists to
  prevent.
- **The provider is part of the cache key**, through the same `salt` argument
  `ssc.cli.cache.cache_key` already carries. A pose computed on CPU and one on CUDA are two
  entries; the miss says which provider it was keyed on, so the re-run after switching
  extras reads as a different key rather than a broken cache.
- **The pure core (`ssc.core.posetrack`) takes the model as a callable** returning
  `(17, 3)` keypoints in frame pixels, so it holds the per-frame report and never the
  import. `ssc.cli.cvruntime.pose_model_for` is the one seam that loads the session and
  refuses with the install command when the extra is absent — the same shape as
  `matte_for`, deliberately.

## Consequences

- `mediapipe` is not adopted. `docs/stack.md`'s "expected answer" line was a placeholder
  for this decision, not a decision; it is updated here so the next session reads the
  outcome rather than the expectation.
- The runtime's weight-loading and preprocessing path is not exercised by the suite,
  because the extra is optional by design and the model is injected for tests — the same
  posture `bgremove --model` takes. The MoveNet input contract (192×192, float32 0..1,
  output `[1,1,17,3]` as `y,x,score`) is documented in `cvruntime` against the session's
  own shape, so a model that disagrees is a wrong result, not a silent one.
- A second pose model is a new name in `POSE_MODELS` with a new URL, not a new code path.
  Reversing the choice means swapping that registry entry and re-warming the cache; the
  public surface (`--model`, `--device`, the per-frame report) does not change.
- Pose on pixel-art sprites is approximate: MoveNet was trained on photographs, and a 32px
  character is not a photograph. The number is a measurement an agent carries, not a
  ground truth; `doctor`'s model-free consistency check (plan task 10.2) is the set-level
  number that does not depend on this model's competence.