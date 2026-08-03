---
status: accepted
---

# 0003 · Patch upstream, and call it over a flat ABI

## Context

`adr:0002-vendor-the-pixel-snapper-as-a-wasi-module` decided to ship the snapper as a WASI
module. Task 0.1 of `plans/ssc-pipeline.md` existed because nobody knew whether that was
possible, and the plan carried a fallback ladder — per-platform native binaries, then a
numpy port — to be taken with the evidence in hand. This is that evidence.

Upstream builds for `wasm32-unknown-unknown` with wasm-bindgen. Three facts turned out to
matter, none of them visible from the README:

- **`wasm32-wasip1` is still `target_arch = "wasm32"`.** Every `cfg` upstream uses to mean
  "browser" fires under WASI too, so an unmodified build pulls wasm-bindgen in and emits a
  module importing `__wbindgen_placeholder__` functions. No WASI host can satisfy those.
- **The public entry point does not cross the boundary.** `process_image` returns
  `Result<Vec<u8>, JsValue>`, which is a JS type.
- **Nothing else is public.** `process_image_common`, `parse_palette_hex` and `Config`'s
  `palette` field are all private, so a wrapper crate consuming the library as a plain
  dependency cannot reach the algorithm at all — with or without a palette.

So "write a thin wrapper crate" was not sufficient on its own. Something upstream had to
change.

## Decision

Keep the WASI module, and produce it in two pieces.

**A patch, not a fork.** `wasm/upstream.patch` is 80 lines and touches five things: four
`cfg` gates become `all(target_arch = "wasm32", not(target_os = "wasi"))`, the
wasm-bindgen and `getrandom/js` dependencies are gated on `target_os = "unknown"`, and a
`process_image_wasi` is added beside `process_image` with the same body and a
`PixelSnapperError` in place of the `JsValue`. **The algorithm is untouched.** Upstream is
never checked into this repository as source: `wasm/build.py` fetches the pinned commit
`ae20461`, applies the patch, and builds.

**A flat ABI, not a WASI `main`.** `wasm/pixel-snapper/` is ours — a `cdylib` exporting
`ssc_alloc` / `ssc_dealloc` / `ssc_snap` / `ssc_result_*` / `ssc_error_*` over linear
memory. The alternative, a WASI `main` piping stdin to stdout, was rejected on cost:
`snap` runs on the anchor and then on every recovered frame, so a 200-frame sheet is 200
calls. The flat ABI is one instantiation reused across all of them; a `main` is a process
setup and teardown per frame.

The fallback ladder was not needed and is not being kept warm.

## Consequences

- **The build is faithful.** On the fixture in `tests/fixtures/`, the module's output is
  byte-identical to upstream's own native CLI, both with auto-detection and with a pixel
  size override. That equivalence is what makes "the algorithm is untouched" a claim
  rather than a hope, and it is worth re-checking after any upstream bump.
- **The build is reproducible.** `wasm/build.py` remaps the two paths that vary between
  machines — the checkout and `CARGO_HOME` — so the same toolchain produces the same
  bytes from a different directory. `--check` compares them. What it cannot absorb is a
  different rustc version, and it says so rather than pretending.
- **CI does not rebuild the module**, because that would need a Rust toolchain and network
  access on every run to verify a file that changes once a year. CI tests the committed
  artifact; `--check` is a human act at bump time. A committed binary that nobody
  re-derives is the standing risk of this decision.
- **Upstream bumps cost a patch rebase.** The four `cfg` lines are stable, but the added
  function tracks `process_image`, so an upstream change to its signature is a conflict.
- **A panic inside the module is a wasm trap, not a return code.** `ssc_snap` reports the
  errors upstream returns; it cannot report the ones upstream panics on, and the Python
  side has to treat a trap as a failure of the call.
