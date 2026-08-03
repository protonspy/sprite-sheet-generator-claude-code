# Pixel art conversion — design

## What changes

Serves R1.1, R1.2, R2.1, R2.2, R3.1, R3.3, R4.3.

Four new modules, split on the line `.claude/rules/project.md` draws: `core/` takes and
returns `ndarray` plus a params dataclass, `cli/` owns the files, the cache and the JSON.

- **`core/pixelart.py`** — the algorithms, all pure: build one palette across a set, map a
  frame onto it, the two dithers, orphan-cluster cleanup, outline emphasis.
- **`core/board.py`** — the two reference images, and the layout each one reports.
- **`cli/snapper.py`** — the binding to `vendor/pixel-snapper.wasm`. It lives in `cli/`
  and not `core/` because it loads a file from disk and holds a `wasmtime` store, which is
  exactly what `core/` is defined not to do.
- **`cli/commands/convert.py`** — `tool snap`, `tool pixelart` and the `tool board` group.

`tests/test_pixel_snapper_wasm.py` already drives the flat ABI through a `Snapper` class
written for that test. `cli/snapper.py` is that class moved into the package and given the
error contract; the test keeps its own copy of nothing and imports the real one, so the
binary's ABI has exactly one reader.

## The grid a set shares

R2.2 is the requirement with a real design problem behind it, and the shape of the answer
comes from what the vendored module will and will not tell us. Measured against the pinned
build, on `tests/fixtures/fake-pixels-8x8-at-12x.png` (96×96):

| call | output |
|---|---|
| auto-detect | 10×10 |
| `pixel_size=9.6` | 12×12 |
| `pixel_size=10` | 11×11 |
| `pixel_size=11` | 10×10 |
| `pixel_size=16` | 6×7 |

Three things follow. The module **does not report the size it chose** — only an image. Its
override is **not the inverse of its output**: the auto run implies 96/10 = 9.6, and
passing 9.6 back gives 12×12, not 10×10. And a large override stops producing square
output at all.

So the consensus cannot be taken on the module's internal number, because that number is
not observable. It is taken on **the output grid**, which is the thing that actually has to
match: snap every frame with auto-detection, take the size most of the set resolved to, and
bring any frame that disagrees onto it with `core.resize`. Nearest neighbour on an already-
snapped grid image moves no colour and introduces no blur — it is the one resampler this
project has, and this is the case it exists for.

In practice the correction is rarely applied: frames of one animation arrive at one size
and the module is deterministic (verified across three fresh instantiations). The guarantee
is worth stating exactly anyway, because it is what `flicker` depends on: **every frame of
a set comes back on one grid**, not "usually does".

`--pixel-size` (R2.3) skips all of it — one override, every frame, one pass.

## The palette a set shares

The same argument, one layer up, and the reason `pixelart` takes a set rather than a file:
one palette is computed from **every opaque pixel of every frame at once**, then each frame
is mapped onto it. Quantizing frame by frame is what makes a region that did not move
change colour between adjacent frames, which is `flicker` — a defect `doctor` measures and
that no post-process removes, because the information is already gone.

Alpha is not quantized and not touched (R3.3). Pixel art alpha is binary; a semi-transparent
edge is `halo`, which is `doctor`'s to report and `bgremove`'s to fix. Folding either into
the colour mapping would hide one defect inside another.

## Alternatives considered

**Reusing `doctor`'s `detect_pixel_size` for R2.2 — rejected on measurement.** It returns
`1` on the fake-pixel fixture, and that is correct for what it is: `doctor` asks *is this
on a grid*, and a detected size of 1 beside a high off-grid share is precisely how it says
"no". `snap` asks a different question — *what grid was this meant to be on* — and only the
module answers that. Two detectors that look interchangeable and are not is worth the
paragraph.

**PIL's `quantize` for the palette, rather than writing median cut.** Adopted for building
the palette; the mapping onto it is ours, because R3.1 needs one palette applied to many
frames and `quantize` has no such notion. `Image.quantize` does not resample, so it does
not touch the nearest-neighbour invariant `workspace-foundation` set —
`tests/test_no_other_resampler.py` guards that mechanically either way.

## Risks

**The vendored module is a foreign runtime in the hot path.** `snap` runs per frame, twice
per pipeline, so a leaked store or a re-instantiation per frame turns into real time. One
`Snapper` serves a whole set, which the existing test already pins
(`test_the_instance_is_reusable_across_frames`), and a failed call must leave the instance
usable — also already pinned.
