# vendor/

Not ours. Rebuilt from upstream, never hand-edited.

## `pixel-snapper.wasm`

[spritefusion-pixel-snapper][upstream] (MIT, Hugo Duprez) at commit
`ae20461f60fb39e75d15f184bab1ebec1219511c`, plus the thin flat-ABI wrapper in
`wasm/pixel-snapper/`, compiled to `wasm32-wasip1`.

`LICENSE` is upstream's, and it stays with the module.

Rebuild it with `python wasm/build.py`; `python wasm/build.py --check` says whether what
is committed here still matches that source. The ABI and the reason for the patch are in
[`wasm/README.md`](../wasm/README.md); the decisions are
`docs/adr/0002-vendor-the-pixel-snapper-as-a-wasi-module.md` and
`docs/adr/0003-patch-upstream-and-call-it-over-a-flat-abi.md`.

[upstream]: https://github.com/Hugo-Dz/spritefusion-pixel-snapper
