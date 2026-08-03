# Prior art

What already exists in this space, what was taken, and what was refused. Recording the
refusals matters as much as the adoptions — otherwise the same option gets re-litigated
every six months.

## spritefusion-pixel-snapper — adopted

[Hugo Duprez, MIT](https://github.com/Hugo-Dz/spritefusion-pixel-snapper). Rust, and the
engine behind `ssc tool snap`. Its selling point is that it preserves dithering, which a
naive modal downsample destroys — and dithering is a wanted aesthetic, not noise.

Cost of adopting it: upstream builds for `wasm32-unknown-unknown` with wasm-bindgen JS
glue, so a WASI target needs a thin wrapper crate written for it. That work is on the
critical path and its fallback ladder is a native per-platform binary or a port to numpy.

## proper-pixel-art — refused

[Kenneth J. Allen, MIT](https://github.com/KennethJAllen/proper-pixel-art). Python, on
PyPI, and it would have removed Rust, `wasmtime` and a vendored binary from the critical
path entirely. It also *detects* the pixel grid — Canny, Hough, median spacing — and
computes one mesh and palette across a video's frames.

Refused in favour of the snapper's maturity and provenance. What that costs: grid
detection and the shared cross-frame palette become this project's code rather than a free
side effect. Smaller than it looks — `doctor` owes a grid detector whichever engine sits
under `snap`, and the flicker fix needs a shared palette regardless.

## Sorceress "True Pixel" — competitor, read closely

A commercial suite (one-off fee) covering the same path: frame extraction, chroma
cleanup, palette conversion, sheets for Godot, Unity and GameMaker. Their public
wiki documents each tool, and reading it changed four decisions rather than confirming
them:

- **Chroma has a Global and a Flood mode.** Matching the key colour everywhere eats a
  green gem inside the character. Flood from the border does not.
- **Atlas export pads transparency.** Without padding the GPU samples across an entry
  boundary and neighbours bleed into each other.
- **Their sprite tool auto-detects grid, frame size, margin and spacing** on an imported
  sheet. Requiring the caller to declare the layout makes "repairs a sheet you already
  have" untrue for sheets of unknown origin.
- **Animations have ping-pong, reverse and named sections inside one sheet.** An attack's
  windup, hit and recovery are ranges, not three sheets.

Two things their documentation settles by omission or admission. Their tileset tool has
**no autotile, no Wang tiles, no terrain transitions** — so leaving those out is not a gap
against the market. And they state plainly that seamless generation "is AI-assisted and is
not guaranteed", which is the honest version of what every model does: generate, repair,
verify.

Their verification for seams is a 2×2 tiled preview with a grid overlay — a human looking
at four copies. Keeping both that and a measured `seam` check is deliberate: the
measurement is what an agent acts on, the picture is what a person trusts.

## 3D → 2D — out of scope

Rendering a rigged model from N angles is the deterministic answer to cross-direction
consistency, which [[anchor-and-directions]] works around with anchors and mirroring. It
is a different product: it needs a renderer, a scene format and rigged input, and the
person who has a rigged model is not the person who has one AI image.

## Hosted models

Fal hosts BiRefNet for background removal alongside the image and video models, which
makes model-quality masking a remote call with no local inference stack at all. It costs
money per call, which is why it lives under the verb that bills.
