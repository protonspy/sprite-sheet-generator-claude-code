# `vendor/pixel-snapper.wasm` — how it is built

`ssc tool snap` runs [spritefusion-pixel-snapper][upstream] (MIT, Hugo Duprez) as a WASI
module, so the algorithm ships without a Rust toolchain and without per-platform binaries.
This directory holds everything needed to rebuild that module; `vendor/` holds the result.

```
python wasm/build.py            # clone, patch, build, copy into vendor/
python wasm/build.py --check    # rebuild into a temp dir and diff against vendor/
```

The build needs `cargo`, the `wasm32-wasip1` target (`rustup target add wasm32-wasip1`)
and network access to GitHub. Nothing in CI runs it: CI tests the committed `.wasm`.

## Why a patch and not a plain dependency

Upstream targets `wasm32-unknown-unknown` with wasm-bindgen JS glue. Its public entry
point, `process_image`, returns `Result<Vec<u8>, JsValue>`, and everything that would make
it callable from plain Rust — `process_image_common`, `parse_palette_hex`, `Config`'s
`palette` field — is private.

`wasm32-wasip1` is still `target_arch = "wasm32"`, so building it as-is pulls wasm-bindgen
in and produces a module importing `__wbindgen_placeholder__` functions that no WASI host
can supply. `upstream.patch` is the smallest change that avoids that:

- the four `cfg(target_arch = "wasm32")` gates guarding the wasm-bindgen path become
  `cfg(all(target_arch = "wasm32", not(target_os = "wasi")))`, and the wasm-bindgen and
  `getrandom/js` dependencies are gated on `target_os = "unknown"`;
- `process_image_wasi` is added beside `process_image` — the same body, returning
  `Result<Vec<u8>, PixelSnapperError>` instead of a `JsValue`.

The algorithm itself is untouched, which is what makes the equivalence check in
`tests/test_pixel_snapper_wasm.py` meaningful. Why a WASI module at all is
`docs/adr/0002-vendor-the-pixel-snapper-as-a-wasi-module.md`; why it is built this way is
`docs/adr/0003-patch-upstream-and-call-it-over-a-flat-abi.md`.

## The flat ABI

`wasm/pixel-snapper/` is ours: a `cdylib` exposing a C ABI over that entry point, so the
module is instantiated once and called per frame rather than spawned per file.

| Export | Meaning |
|---|---|
| `ssc_alloc(len) -> ptr` · `ssc_dealloc(ptr, len)` | caller-owned input buffer |
| `ssc_snap(in_ptr, in_len, k_colors, pixel_size_override, pal_ptr, pal_len) -> i32` | `0` ok, `1` failed |
| `ssc_result_ptr()` · `ssc_result_len()` | the output PNG, valid until the next call |
| `ssc_error_ptr()` · `ssc_error_len()` | a UTF-8 message when the call returned `1` |

`k_colors = 0` and `pixel_size_override <= 0` mean "use the default"; `pal_len = 0` means
no palette. A panic inside the module is a wasm trap, not a return code.

[upstream]: https://github.com/Hugo-Dz/spritefusion-pixel-snapper
