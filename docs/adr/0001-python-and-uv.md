---
status: accepted
---

# 0001 · Python, distributed with uv

## Context

`ssc` is image processing with a computer-vision tail: connected components, morphology,
flood fill, colour quantization, and eventually ONNX inference for background removal and
pose tracking. That work has one mature ecosystem, and it is Python — numpy, Pillow,
OpenCV and `onnxruntime` are all first-class there and second-class or absent everywhere
else.

Go was the alternative actually considered, and its argument was distribution: one static
binary, no interpreter, no environment. That argument does not survive contact with the
CV requirement. ONNX inference from Go goes through cgo, which is exactly what destroys
the static binary — so the only real advantage of the language was conditional on not
building the thing the tool is for.

The distribution problem is real regardless. The target user runs one command against a
directory of images; asking them to manage a virtualenv is a tax on every use.

## Decision

Python, `>=3.11`, `src/` layout, built with hatchling, and run through **uv** —
`uv run ssc …`, `uvx ssc …` — so a user gets an isolated, resolved environment without
creating or activating one. The optional model runtimes are extras (`[cv]`, `[cv-gpu]`)
rather than dependencies, so the deterministic half of the tool installs small.

Against Go for the reason above. Against Rust, which would have kept the CV story but
made every contributor pay for the borrow checker in code that is mostly array
arithmetic. Against pip and a hand-managed venv, which is what uv exists to replace.

## Consequences

- No single binary, ever. Distribution is a Python package, and the install story is
  "have uv". That is the cost paid for the ecosystem.
- **The version floor is 3.12, and the ecosystem set it rather than this project.** 3.11
  was the intent — `X | Y` unions, `tomllib`, exception groups, nothing needing
  `typing_extensions`. Building `specs/workspace-foundation/` found it unworkable: numpy's
  own type stubs use `type` statements, so `mypy --python-version 3.11` cannot parse them,
  and the project's most-used dependency becomes untypeable at exactly the layer where the
  types matter. Pinning numpy backwards to keep a floor nobody had asked for was the worse
  trade.
- CI runs on Linux and Windows against one Python rather than one OS against three
  Pythons: what breaks per-platform in this project is paths, line endings and the
  `wasmtime` runtime, not language versions.
- The Rust toolchain does not disappear entirely — it is needed to rebuild the vendored
  snapper (see `adr:0002-vendor-the-pixel-snapper-as-a-wasi-module`) — but no user and no
  CI job needs it.
