# Pixel art conversion — tasks

**What already covers these paths:** `tests/test_pixel_snapper_wasm.py` covers the vendored
module and the flat ABI this leaf binds to — including that one instance serves many frames
and that a failed call leaves it usable — and it is the test that must stay green when the
`Snapper` class moves out of it into `src/`. `tests/core/test_resize.py` and
`tests/test_no_other_resampler.py` cover the only resampler, which R2.2 and R2.4 both call.
`tests/cli/test_cache.py` covers the store R2.7 uses. `tests/core/doctor/test_checks.py`
covers `detect_pixel_size` and the mask helpers this leaf reuses for R3.6 and R3.7. All were
run green before this work started.

## 1 · The frame set

- [x] 1.1 (Unit) Read `--in` as one image or an ordered frame set, and refuse an `--out` that already exists — R1.1, R1.2, R1.3, R1.4

## 2 · `snap`

- [x] 2.1 (Unit) Move the flat-ABI binding into `cli/snapper.py`, one instance per set, failures as `SscError` — R2.1, R2.6
- [x] 2.2 (Unit) Resolve one grid across a set and bring every frame onto it — R2.2, R2.3
- [ ] 2.3 (Unit) Build `ssc tool snap`: `--grid` against the return to the arrival size, and the colour constraints — R2.4, R2.5
- [x] 2.4 (Unit) Key a snapped frame by its content, its grid and its parameters — R2.7

## 3 · `pixelart`

- [ ] 3.1 (TDD) Compute one palette across a frame set and map every frame onto it, leaving alpha alone — R3.1, R3.2, R3.3
- [ ] 3.2 (Unit) Ordered and Floyd-Steinberg dithering against a fixed palette, and neither by default — R3.4, R3.5
- [ ] 3.3 (Unit) Orphan-cluster cleanup, and one-pixel outline emphasis — R3.6, R3.7
- [ ] 3.4 (Unit) Build `ssc tool pixelart` over the four — R3.1, R3.4, R3.6, R3.7

## 4 · `board`

- [ ] 4.1 (Unit) Generate the checkerboard and the pose board, each reporting the layout it wrote — R4.1, R4.2, R4.3
