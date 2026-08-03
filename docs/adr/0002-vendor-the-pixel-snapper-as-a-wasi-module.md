---
status: accepted
---

# 0002 · Vendor the pixel snapper as a WASI module

## Context

Recovering real pixels from fake ones is the defect `ssc tool snap` exists to repair, and
it is not a resize — it is grid detection plus a quantization that has to **preserve
dithering**, because dithering is a wanted aesthetic and a naive modal downsample
destroys it. `spritefusion-pixel-snapper` (MIT, Hugo Duprez) already does that and is the
maturest implementation available.

It is Rust. This is a Python project (`adr:0001-python-and-uv`), so using it at all means
choosing how Rust code reaches a Python process.

Two alternatives were real. `proper-pixel-art` (MIT, Python, on PyPI) would have removed
Rust from the picture entirely and throws in grid detection and a shared cross-frame
palette for free. Porting the algorithm to numpy would have removed the dependency
instead. Both were weighed in `docs/wiki/prior-art.md` and lost to the snapper's maturity
and provenance — the dithering behaviour is the whole reason it was wanted, and it is the
part hardest to reproduce correctly.

The third option, shipping a native binary per platform, is the one that looks cheapest
and is not: it means a build matrix, three or more artifacts per release, and a
per-platform failure mode for a project whose CI already carries two operating systems.

## Decision

Vendor the snapper as a single `wasm32-wasip1` module, `vendor/pixel-snapper.wasm`,
committed to the repository with upstream's `LICENSE`, and run it with `wasmtime`.

One artifact serves every platform, no user needs a Rust toolchain, and the module has no
ambient authority — it gets bytes in and bytes out, with no filesystem and no network.
What it costs is a binary in git and a rebuild step that lives outside CI; how the module
is actually produced, and what that cost is in practice, is
`adr:0003-patch-upstream-and-call-it-over-a-flat-abi`.

What this does **not** buy is grid detection or a cross-frame palette — those were the
free side effects of the refused alternative, and they are now this project's code.
That is a smaller loss than it looks: `doctor` owes a `pixel_grid` detector whichever
engine sits under `snap`, and the `flicker` fix needs one palette across a frame set
regardless.

## Consequences

- `wasmtime` is a hard runtime dependency, not an extra. Every install carries it whether
  or not the user ever snaps anything.
- A 350KB binary is committed and reviewed by nobody. The mitigations are a pinned
  upstream commit, a reproducible build, and `python wasm/build.py --check`, which says
  whether what is committed still corresponds to that source.
- Upstream is not tracked automatically. Taking a newer snapper is a deliberate act with a
  patch to re-apply and a fixture to re-measure.
- Grid detection and the shared palette are ours to write, in `sheet-doctor` and
  `pixel-art-conversion` respectively.
