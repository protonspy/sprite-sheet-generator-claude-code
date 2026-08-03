---
autonomy: auto
ci: wait
---

# Workspace foundation — requirements

## Purpose

The workspace is the disk contract every other command in `ssc` inherits: where an asset
lives, what each of its files is, which command produced it, and which of them may be
deleted. It exists because the twenty-six leaves that follow must not each invent an
answer — and because a file whose provenance nobody recorded cannot be reproduced,
debugged, or safely thrown away. This is for an operator at a terminal and, at least as
much, for an agent driving `ssc` with no eyes on the directory.

## R1 · The workspace

- **R1.1** The `ssc` CLI shall treat a directory holding `ssc.yaml` at its root as a workspace.
- **R1.2** When `ssc init` runs in a directory holding no `ssc.yaml`, the `ssc` CLI shall create `ssc.yaml`, `assets/` and `cache/` there.
- **R1.3** If `ssc init` runs where `ssc.yaml` already exists, then the `ssc` CLI shall change nothing and exit `2`.
- **R1.4** The `ssc` CLI shall locate the workspace by searching the current directory and its ancestors for `ssc.yaml`.
- **R1.5** If a workspace command runs outside a workspace, then the `ssc` CLI shall exit `2` and report that no workspace was found.
- **R1.6** Where a command takes `--in` and `--out`, the `ssc` CLI shall run that command without a workspace.

## R2 · Assets on disk

- **R2.1** The `ssc` CLI shall place an asset at `assets/<kind>/<key>/` and name its files `<NNN>_<label>.<ext>`, where `NNN` orders the chain for a reader.
- **R2.2** When `ssc asset new <key> --kind <kind>` runs, the `ssc` CLI shall create that directory and its `meta.json`.
- **R2.3** If an asset with that key already exists in that kind, then the `ssc` CLI shall change nothing and exit `2`.
- **R2.4** The `ssc` CLI shall order an asset's chain by the numbered prefix and shall never accept that prefix as a file's address.
- **R2.5** The `ssc` CLI shall permit no subdirectory of an asset other than `frames/`.

## R3 · Provenance

- **R3.1** When it writes a file into an asset, the `ssc` CLI shall record in that asset's `meta.json` the file's stage, its class, the command and parameters that produced it, and the files it was derived from.
- **R3.2** The `ssc` CLI shall give every recorded file exactly one class: `source`, `derived` or `output`.
- **R3.3** The `ssc` CLI shall resolve a stage name to a file without the caller supplying that file's numbered prefix.
- **R3.4** If two files in one asset would carry the same stage, then the `ssc` CLI shall refuse the write and exit `2`.
- **R3.5** If a command would write over a file that already exists, then the `ssc` CLI shall refuse the write and exit `1`.
- **R3.6** The `ssc` CLI shall write `meta.json` atomically, leaving either the previous record or the new one after an interrupted command.
- **R3.7** (ADDED) When it writes a file into an asset or deletes one from it, the `ssc` CLI shall act through the directory it checked rather than through that directory's path.
- **R3.8** (ADDED) If the directory that was checked is no longer the one its path names, then the `ssc` CLI shall change nothing in that asset and exit `1`.

## R4 · The CLI contract

- **R4.1** The `ssc` CLI shall accept `--json` on every command and, when given it, emit exactly one JSON object on stdout and nothing else.
- **R4.2** The `ssc` CLI shall exit `0` on success, `1` on error, `2` on invalid usage, and `3` while a gate is pending.
- **R4.3** When `--dry-run` is given, the `ssc` CLI shall write nothing and report what it would have written.
- **R4.4** Where a command resizes an image, the `ssc` CLI shall resample with nearest neighbour.
- **R4.5** The `ssc` CLI shall report an error as a JSON object carrying a stable code, a message, and the command that fixes it where one exists.
- **R4.6** (MODIFIED) If a value held by an environment variable whose name reads like a credential, or a credential carried in a URL, a `key=value` pair, an authorization scheme, or a field whose *name* says its value is a credential, would appear in what a command emits, then the `ssc` CLI shall replace it with `***` on both stdout and stderr.

## R5 · The cache

- **R5.1** The `ssc` CLI shall address a cached result by a key derived from the content of its inputs, the command, and the parameters that affect the result.
- **R5.2** When a command's cache key is already present, the `ssc` CLI shall reuse the cached result instead of recomputing it and shall report that reuse in its JSON.
- **R5.3** The `ssc` CLI shall remain correct with `cache/` deleted at any moment.

## R6 · Deleting

- **R6.1** When `ssc clean` runs, the `ssc` CLI shall delete the files classed `derived` and no others.
- **R6.2** The `ssc` CLI shall never delete a file classed `source`.
- **R6.3** When `ssc clean` deletes a file, the `ssc` CLI shall remove that file's record from `meta.json`.

## Out of scope

- **What a kind means.** `kind` is recorded as a name, and nothing here reads it. The
  profile that gives it meaning — cell, anchor mode, applicable checks, template — is
  `specs/asset-kinds/`.
- **Listing and showing.** `ssc image list` and `ssc image show --stage nobg` are
  `specs/asset-listing/`; this leaf owes them a recorded stage, not the commands.
- **`jobs/` and gates.** Exit `3` is reserved here so the contract is complete, but nothing
  in this leaf produces it.
- **A command that actually caches.** R5 defines the key, the store and the field that
  reports a reuse, and all three are built and tested — but `init`, `asset new` and
  `clean` compute nothing worth caching, so R5.2's reuse is exercised at the library
  boundary rather than through a command. The first command to close that loop is
  `specs/pixel-art-conversion/`'s `ssc tool snap`, which is also the reason the cache
  exists: `snap` runs on every frame of every animation.
