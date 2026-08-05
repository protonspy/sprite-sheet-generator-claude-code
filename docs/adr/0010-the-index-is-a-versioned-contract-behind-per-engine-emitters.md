---
status: accepted
---

# 0010 · The index is a versioned contract behind per-engine emitters

## Context

`dist/index.json` is the first file `ssc` writes that something outside this repository
reads. Everything before it — `meta.json`, a job record, a gate — is read by `ssc` itself,
so its shape can change in the commit that changes the reader. The index cannot: a game
loads it, and the loader lives in a codebase nobody here can edit.

Three leaves write into it and none of them is built yet. `specs/engine-index/` puts the
sheets, atlases and tilesets there. `specs/frame-metadata/` adds a box and a marker per
frame. `specs/style-and-palette/` will want the palette an asset resolved against. Each
one arrives after some workspace has already shipped an index to an engine.

The other half is that four engines want four different shapes for the same measurements.
Pixi wants a frame table keyed by name with a fractional anchor; Phaser wants its own
atlas hash; Godot wants a resource description; `generic` wants the numbers as measured.
Writing four emitters that each walk the workspace is four places to fix a cell-size bug
and four chances for `pixi` and `phaser` to disagree about what the anchor was.

## Decision

**`dist/index.json` is a versioned contract**, and every format is a pure function of one
internal model.

- **One model, built once.** `ssc.cli.index` gathers the workspace into `Built` —
  `SheetEntry`, `AtlasEntry`, `TilesetEntry` — and that is the only code that reads a
  workspace. Measurement happens exactly once.
- **Emitters are pure and take `Built`.** `ssc.cli.formats` holds `generic`, `pixi`,
  `phaser` and `godot`; each takes the model and returns a document. None of them opens a
  file. A fifth engine is a function, not a traversal.
- **`schema` is the first field, and it versions the shape, not `ssc`.** `SCHEMA = 1`
  today. A consumer that reads it can tell a field it does not know from a field that was
  removed, which is the distinction a loader has to make to fail usefully.
- **Additive changes keep the number.** A new key that an old loader ignores is not a new
  version. Removing a key, renaming one, or changing a unit is, and it increments `schema`.
- **`format` is recorded beside `schema`.** The same workspace emitted twice is two files
  with the same measurements in two shapes, and a loader handed the wrong one should say so
  rather than read fields that happen to overlap.

## Consequences

- The interesting invariants are testable without any engine: two formats emitted from one
  `Built` cannot disagree about a cell, because neither of them measured it.
- The cost lands on `frame-metadata` and `style-and-palette`. Each has to extend `Built`
  and then decide, per format, whether the new value has a natural home there or is dropped
  — `godot` has no place for a hurtbox, and dropping it silently is a decision, not an
  oversight. That per-format answer belongs in each leaf's `design.md`.
- `generic` is load-bearing and stays the default. It is the only format that carries
  everything, so it is where a value goes when no engine has a slot for it, and it is what
  `ssc preview` reads.
- Reversing this means an engine's loader is already parsing the shape we changed. That is
  why it is a record: the constraint is other people's code, and no amount of care inside
  this repository can migrate it.
