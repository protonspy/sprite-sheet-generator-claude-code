# This project

`ssc` — a CLI that turns AI-generated art into game-ready assets. Python, distributed
with `uv`. The decomposition lives in `plans/ssc-pipeline.md`.

## Commands

```bash
# Build
uv build

# Test — the whole suite
uv run pytest

# Test — one file or one test (used after every task; scope, not suite)
uv run pytest tests/core/test_snap.py
uv run pytest -k "bgremove and flood"

# Lint — both layers, both required
uv run ruff check .
uv run mypy src

# Format / format check
uv run ruff format
uv run ruff format --check
```

`uv sync --all-extras` before any of the above on a fresh checkout. The `[cv]` and
`[cv-gpu]` extras are optional at runtime and the suite must pass without them — a test
that needs them skips with a reason rather than failing.

## Conventions

- **Branch names:** `feat/<slug>`, `fix/<slug>`, `plan/<slug>`.
- **Commits:** Conventional Commits, scoped by module — `feat(core/snap):`,
  `fix(cli/bgremove):`, `docs(wiki):`.
- **`core/` is pure.** Functions take and return `ndarray` plus a params dataclass. No
  file IO, no `click`, no `meta.json`. The `cli/` layer owns IO, cache, lineage and JSON
  output. This split is what makes a core function testable against an 8×8 array.
- **Every command emits JSON and writes a new file.** Nothing mutates its input, and
  nothing prints a result a caller has to parse out of prose.
- **Exit codes are the contract:** `0` ok · `1` error · `2` invalid usage · `3` a gate is
  pending.

## Boundaries

- **Nearest neighbour is the only resampler.** There is one `core.resize()` and a test
  that fails if `Image.resize` or `cv2.resize` is called anywhere else. Any other
  resampler reintroduces the sub-pixel blur `snap` exists to remove, and the damage is
  invisible until 4× zoom.
- **`vendor/pixel-snapper.wasm` and its `LICENSE` are not ours.** Rebuilt from upstream,
  never hand-edited; the licence file stays.
- **Test fixtures with measured defects are the asset.** A sheet with 4px of bleed in
  frame 3, a tile with a 3px seam. Do not regenerate or "fix" them — `doctor` is
  validated against those exact numbers, and everything else depends on `doctor` being
  right.
- **Nothing deletes a `source` file.** `ssc clean` may remove `derived` only. A source is
  what a model produced: it cost money and is not reproducible.
