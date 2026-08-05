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
- **httpx** — HTTP for anything the provider client does not cover, which today is reading
  a model's published OpenAPI schema.
- **fal-client** — the generation provider, pinned `>=1.0,<2`. Chosen for `submit` →
  `get_handle(app, request_id)` → `status`/`result`/`cancel`, which is what lets a job
  survive the death of the process that started it; the pin and the version evidence are
  `adr:0006-job-store-rides-the-fal-client-handle-surface`.

## Optional extras

- **`[cv]`: onnxruntime, rembg / BiRefNet** — model-based background removal that runs
  locally and costs nothing per call.
- **`[cv-gpu]`: onnxruntime-gpu, rembg** — the same models against a different runtime
  distribution rather than a runtime flag, which is why the extras split instead of taking
  a switch. `rembg` is in both extras because it is the model layer, not the runtime.
- **`onnxruntime-directml` — accepted, and installed by hand.** DirectML ships in a third
  distribution that neither extra carries, which
  `adr:0011-two-extras-for-onnxruntime-and-detection-that-ignores-them` recorded as an open
  gap. Resolved by keeping `--device directml` in the accepted set and naming the package
  in the refusal: a Windows user with an AMD or Intel GPU is told what to install, and no
  extra promises a build it does not deliver. It is not a dependency of this project, so
  it is here as a decision rather than in `pyproject.toml`.

The execution provider each of these gives is part of the cache key, so a CPU result and a
CUDA result are never one entry — `ssc.cli.devices.cache_salt` is where that is folded in.

**What installing `[cv]` trusts.** `rembg` downloads its weights on first use, to a
user-level cache, over a channel `ssc` neither controls nor checksums — and `onnxruntime`
then loads that graph and runs it. Installing the extra is therefore trusting `rembg`'s
distribution the way installing any dependency trusts its index, and it is recorded here
rather than left implicit because `ssc tool bgremove --model` is the first command to put a
downloaded model on that path. A project that cannot accept it has the chroma key, which
downloads nothing.

## Development

- **pytest** — the suite, and golden tests over small arrays for each pure core function.
- **ruff** — lint and format in one tool, fast enough to run per task.
- **mypy** — checks `src/`, `strict`. The JSON contracts are typed; a schema that drifts
  from its dataclass is a defect tests will not catch.
- **types-PyYAML** — `pyyaml` ships no annotations, so under `strict` every `ssc.yaml`
  read would otherwise be `Any` at exactly the boundary where the shape is in doubt.
- **hatchling** — build backend. Chosen for handling the `src/` layout with no
  configuration beyond naming the package.

## CI

- **GitHub Actions** — the repo is on GitHub and the PR is where work lands, so checks
  belong where the review is.
- **Matrix: Linux and Windows, one Python.** Two operating systems beat three Python
  versions here: what actually breaks per platform in this project is paths, line endings
  and the `wasmtime` runtime, and all three only break on Windows — which is also where
  it is developed.
- **`scc validate` runs as its own job.** Exit `2` means it ran and found something, which
  is a failing check rather than a crashed one.

## Vendored

- **spritefusion-pixel-snapper** (MIT, Hugo Duprez) — compiled to `wasm32-wasip1` and
  committed as `vendor/pixel-snapper.wasm` with its `LICENSE`. Adopted for its dithering
  preservation; see `docs/wiki/prior-art.md`,
  `adr:0002-vendor-the-pixel-snapper-as-a-wasi-module` and
  `adr:0003-patch-upstream-and-call-it-over-a-flat-abi`. Rebuilt by `wasm/build.py`, which
  needs `cargo` and the `wasm32-wasip1` target — neither at runtime nor in CI.

## Not adopted

Everything above this line is installed and decided. Nothing below it is either — it is
recorded so the next session knows the question was seen, not so it can be treated as
settled.

- **mediapipe** — the expected answer for pose tracking through an animation cycle, which
  `specs/cv-motion-consistency/` needs. Not installed, not in any manifest, and not
  decided: it is a heavy dependency for one M6 leaf, so it earns an ADR when that leaf is
  built rather than a line here that reads like adoption.
