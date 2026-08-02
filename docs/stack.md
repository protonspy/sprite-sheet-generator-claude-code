# Stack

Every adopted technology, and the one line that earned it its place. Anything installed
and not listed here is an undecided dependency.

## Language and packaging

- **Python** — the core of the product is image processing and CV; that ecosystem is
  Python. Go was considered and rejected: ONNX inference there needs cgo, which destroys
  the static binary that was its only real advantage.
- **uv** — isolated install and execution without a global environment, which is what
  keeps the distribution story tolerable now that a single binary is off the table.

## Core

- **numpy** — every image is an RGBA `uint8` array; all pure transformations are array
  operations.
- **Pillow** — image IO and the nearest-neighbour resize, which is the only resampler
  this project permits.
- **opencv-python-headless** — connected components, morphology, flood fill, Sobel.
  Headless because nothing here opens a window, and the GUI build drags in system
  libraries that break in CI.
- **click** — the CLI. Command groups map cleanly onto the `gen` / `tool` / `image` /
  `video` / `job` / `gate` split, where the verb carries the guarantee.
- **pydantic** — the JSON contracts are the product's public interface; they are
  validated, not hand-serialised.
- **pyyaml** — `ssc.yaml` and the per-asset recipe files.
- **wasmtime** — runs the vendored pixel snapper as a WASI module, so no Rust toolchain
  and no per-platform binaries at runtime.
- **httpx** — HTTP for anything the provider client does not cover.
- **fal-client** — the generation provider. Chosen for `submit` → `get_handle(app,
  request_id)` → `status`/`result`/`cancel`, which is what lets a job survive the death
  of the process that started it.

## Optional extras

- **`[cv]`: onnxruntime, rembg / BiRefNet** — model-based background removal that runs
  locally and costs nothing per call.
- **`[cv-gpu]`: onnxruntime-gpu** — a separate distribution rather than a runtime flag,
  which is why the extras split instead of taking a switch.
- **mediapipe** — pose tracking through an animation cycle. Not yet adopted; listed here
  as the expected choice so the decision is visible before it is made.

## Development

- **pytest** — the suite, and golden tests over small arrays for each pure core function.
- **ruff** — lint and format in one tool, fast enough to run per task.
- **mypy** — checks `src/`. The JSON contracts are typed; a schema that drifts from its
  dataclass is a defect tests will not catch.

## Vendored

- **spritefusion-pixel-snapper** (MIT, Hugo Duprez) — compiled to `wasm32-wasip1` and
  committed as `vendor/pixel-snapper.wasm` with its `LICENSE`. Adopted for its dithering
  preservation; see `docs/wiki/prior-art.md`.
