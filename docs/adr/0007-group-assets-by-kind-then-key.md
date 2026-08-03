---
status: accepted
---

# 0007 · Group assets by kind, then key

## Context

The design document this project started from grouped the workspace by stage —
`images/`, `videos/`, `frames/`, `sprites/`, with the asset key underneath each. That
layout answers "where are the videos" immediately, which is the question you ask while
building the tool.

It is not the question anyone asks while using it. An operator asks *what exists of kind
`tile`*, and an agent asks the same thing before deciding what to do next; under a
stage-first layout that answer is spread across four directories and reconstructed by
globbing. `specs/asset-listing/` exists precisely because an agent cannot glob, so the
layout and the listing command are one decision rather than two.

There is a second pressure. `kind` is an **extensible profile**, not an enum
(`specs/asset-kinds/`): a project declares its own in `ssc.yaml` without touching code. A
stage-first tree has nowhere for a project-defined kind to go that is not a special case,
while a kind-first tree gives it a directory and nothing else.

This is the hardest thing in the plan to change later. Every command writes into this
layout, every `meta.json` path is relative to it, and by the time it is wrong there are
assets in it.

## Decision

`assets/<kind>/<key>/`, and inside the key the chain stays **flat**:

```
assets/character/hero/
  meta.json
  001_anchor_s.png
  002_anchor_s.snap.png
  003_anchor_s.nobg.png
  frames/
```

One `ls` reads the whole lineage in order, which is what the numbered prefix is for — and
only what it is for: the prefix is presentation, and a file is addressed by its `stage`
(`adr:0005-a-job-always-exists` has the analogous rule for jobs, where the id is the
address). Inserting a step in the middle must not renumber everything downstream and break
every script that hard-coded `003`.

`frames/` is the single permitted subdirectory, because a frame set is the one thing in an
asset that is genuinely a set rather than a step. Everything else being flat is what keeps
"read the directory, understand the asset" true.

Against stage-first grouping, for the reasons above. Against a flat `assets/<key>/` with
the kind held only in `meta.json`, which would have made the common question require
reading every file in the tree.

## Consequences

- **The kind is in the path, so renaming an asset's kind moves it.** That is a real
  operation someone will want, and it is a move plus a `meta.json` edit rather than a
  field update. Judged acceptable: kinds are chosen at creation and rarely change, and the
  move is at least visible.
- **Two assets in different kinds may share a key**, and nothing global disambiguates
  them. Uniqueness is per kind (R2.3), so every command that takes a key takes a kind with
  it. A globally unique key was rejected as a bigger cost: it would force keys like
  `tile-grass` and put the kind back in the name.
- **`meta.json` paths are relative to the asset directory**, so an asset survives being
  moved or copied elsewhere — which is what makes the point above cheap rather than
  dangerous.
- Nothing here reads the kind. It is a directory name until `specs/asset-kinds/` gives it
  meaning, and that is deliberate: this layout has to be right before the profile system
  exists, not after.
