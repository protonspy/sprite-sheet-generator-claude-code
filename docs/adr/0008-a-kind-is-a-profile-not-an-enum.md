---
status: accepted
---

# 0008 · A kind is a profile, not an enum

## Context

`workspace-foundation` records a `kind` on every asset and deliberately gives it no meaning:
it is a name and a directory level, nothing more. Something has to give it meaning, because
six commands need to know what an asset of a given kind *is* — what cell it targets, whether
it animates, where its anchor sits, which `doctor` checks apply to it, and which prompt
template `gen image` should reach for.

The kinds an asset library needs are open-ended. This project names six — `character`,
`icon`, `tile`, `ui`, `banner`, `map` — and a real project will want a cursor, a portrait, a
font, a VFX sheet. A closed enum makes every one of those a code change and a release.

This is also the decision `asset-listing` and `sheet-assembly` have already been shaped
around without stating: `assets/<kind>/<key>/` puts kind first precisely so that a
project-defined kind gets a directory rather than a special case.

## Decision

A kind is a **profile**: a named record declaring cell size, anchor mode, whether it
animates, its atlas layout, the `doctor` checks that apply to it, and its generation
template. Built-in profiles ship with the package; a project declares its own in `ssc.yaml`
and needs no code change to do it. `ssc kind list` is how a caller discovers what exists,
because an extensible set cannot be hard-coded into a harness.

A project's declaration may extend a built-in or stand alone. Where it names a built-in's
name, the project's wins — a project overriding `character`'s cell is the ordinary case, not
an error.

## Consequences

**The set of kinds is data, so every consumer must read it rather than branch on it.** Any
`if kind == "character"` in this codebase is the defect this ADR exists to prevent, and it
is the thing to look for in review.

**A profile is validated when it is read, not when it is used.** A typo in `ssc.yaml`
surfaces as a refusal from `ssc kind list` rather than as a wrong cell size three commands
later. That is a promise about *every* field, which is stronger than it sounds: coercing a
name field with `str()` accepted a map, a null and a boolean alike, and an `anchor: cetnre`
that reached a consumer would have fallen through to centre behaviour with nothing said. So
the fields with a domain are checked against it, and the rest are checked for being names.

**`ssc.yaml` is the first attacker-influenced structured input this tool parses**, and it
is a file that survives hand-editing. It is bounded in size, its document shape is checked
before anything indexes into it, and anchors are refused outright — `safe_load` blocks
arbitrary object construction but does not bound alias expansion, and a kilobyte of aliases
hangs every kind-aware command in the workspace.

**Built-ins can change under a project.** A project that names no cell inherits one, and a
later version of `ssc` may ship a different one. That is the price of built-ins being
defaults rather than a frozen table, and it is why `ssc kind show` reports the resolved
profile and where each field came from.

**M2's other five leaves consume this.** `atlas-packing` reads the atlas layout,
`tile-assets` and `ui-assets` read the applicable checks, `normal-maps` reads whether one is
produced by default, and `parallax-layers` is a kind whose asset is N files rather than one.
Building any of them against a closed enum first would have hardened the enum into each of
their signatures.
