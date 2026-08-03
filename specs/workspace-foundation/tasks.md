# Workspace foundation — tasks

There are no existing tests over these paths: `src/ssc/` is an empty package and
`tests/test_smoke.py` asserts only that it imports. The two suites that do exist —
`test_pixel_snapper_wasm.py` and `test_model_registry_fallback.py` — touch nothing here.
So the "identify what already covers this" step is answered once, here, rather than
repeated per task.

## 1 · The decision, and the contract every command inherits

- [x] 1.1 (Unit) Record the kind-first layout as `adr:0007-group-assets-by-kind-then-key`, against the design document's stage-first grouping — R2.1
- [x] 1.2 (Unit) Define `SscError` and `UsageError`: a stable code, a message, an optional `fix`, and the exit code each maps to — R4.2, R4.5
- [x] 1.3 (Unit) Build the `Result` object and render it either as one JSON object or as prose — R4.1
- [x] 1.4 (Unit) Wire the click group: `--json` and `--dry-run` as shared options, and the translation from a returned `Result` or a raised `SscError` into an exit code — R4.1, R4.2, R4.3

## 2 · Writing safely

- [x] 2.1 (Unit) Write a file atomically through temp-plus-rename, and refuse a path that already exists — R3.5, R3.6
- [x] 2.2 (TDD) Make `core.resize()` the only resampler in the codebase, and fail the suite on any other resize call under `src/` — R4.4

## 3 · The workspace

- [x] 3.1 (Unit) Find the workspace root by searching ancestors for `ssc.yaml`, and let a command declare whether it needs one — R1.1, R1.4, R1.5, R1.6
- [x] 3.2 (Unit) `ssc init` — create `ssc.yaml`, `assets/` and `cache/`, and refuse where a workspace already exists — R1.2, R1.3

## 4 · The asset record

- [x] 4.1 (Unit) Model `meta.json` — schema, key, kind, and one entry per file carrying its class — and persist it atomically — R3.1, R3.2, R3.6
- [x] 4.2 (Unit) Allocate the next numbered prefix and build a filename from the label and the stages applied so far — R2.1, R2.4
- [x] 4.3 (Unit) Record a written file with its digest and provenance, refuse a stage already taken, and resolve a stage name back to its file — R3.1, R3.3, R3.4
- [x] 4.4 (Unit) `ssc asset new <key> --kind <kind>` — create the directory and its `meta.json`, and refuse a key the kind already has — R2.2, R2.3
- [x] 4.5 (Unit) Reject any subdirectory of an asset other than `frames/` — R2.5
- [x] 4.6 (Unit) Call that rejection where a caller addresses one asset, and the escape check on every route that reaches one, the two that create included — R2.5

## 5 · The cache

- [x] 5.1 (TDD) Derive the cache key from the inputs' content, the command, the parameters that affect the result, and a salt later leaves extend — R5.1
- [x] 5.2 (Unit) Store an entry, look one up, and report the hit in the command's result — R5.2, R5.3

## 6 · Deleting

- [x] 6.1 (TDD) `ssc clean` — delete the files classed `derived`, never one classed `source`, and drop each deleted file's record — R6.1, R6.2, R6.3

## 7 · What a command may say

- [x] 7.1 (Unit) Redact a credential — an environment secret by value, a `key=value` pair, an authorization scheme or a connection string's password by shape — at the boundary every command's output crosses — R4.6

## Notes

**The red was observed on all three TDD tasks.** 5.1 and 6.1 failed on
`ModuleNotFoundError` for `ssc.cli.cache` and `ssc.cli.app` before either existed. 2.2
needed more than that, because a guard over a codebase with nothing wrong in it passes
whether or not it works: a module calling `Image.resize(..., Image.BILINEAR)` was added
under `src/`, the guard failed naming that line, and the module was removed.

**Three tasks are TDD, and two of them because being wrong is not recoverable.** 6.1
deletes files, and a `source` is what a model produced: it cost money and cannot be
regenerated, so the test proving `clean` will not touch one is written before `clean`
exists. 5.1 decides when a result is reused, and a key that ignores a parameter returns a
stale image that looks plausible — the failure nobody notices. 2.2 is the invariant the
whole of M1 rests on: one careless bilinear resize undoes `snap`, and the damage is
invisible until 4× zoom.
