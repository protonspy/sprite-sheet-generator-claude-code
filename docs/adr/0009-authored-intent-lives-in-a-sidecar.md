---
status: accepted
---

# 0009 · Authored intent lives in a sidecar

## Context

`specs/engine-index/` needs three things `ssc` cannot derive from any image: the frame rate an
animation plays at, whether it loops, ping-pongs or reverses, and the named sections of one
set — an attack's windup, hit and recovery. None of the three is measurable. Somebody decides
them, and the decision has to survive on disk.

`meta.json` was the obvious place: it is already per asset, already validated on read, already
what every command loads. It is also, by its own first line, "what each file in an asset is,
and where it came from" — a record of what commands did. A frame rate is not that.

The consequence is not aesthetic. `ssc clean` reads exactly one field of `meta.json`, `class`,
and deletes every file recorded as `derived`. Putting hand-written values in that file makes
the record a caller edits and the record `clean` acts on the same file, and the first
hand-edit that gets a class wrong deletes art. `specs/workspace-foundation/` R6 spent its
whole design on "nothing deletes a source", and this would put a new way to reach that.

`specs/frame-metadata/` needs the same thing again, more so: hit boxes, hurt boxes and named
markers are authored data with no derivation at all. And `specs/asset-derivation/` in M5 names
`<asset>.yaml` as where an asset's recipe lives. Three leaves want one file.

## Decision

Authored intent lives in **`assets/<kind>/<key>/asset.yaml`**, beside `meta.json` and not
inside it.

- **`meta.json` stays provenance.** What each file is, where it came from, what class it is.
  Written by commands, read by `clean`, never hand-edited in the ordinary case.
- **`asset.yaml` is authored.** Written by a person or an agent, read by `ssc index` and by
  whatever comes after it, and **never recorded in `meta.json`** — `meta.record` refuses the
  name, so `clean` cannot reach it however the record is edited.
- **Validated on read, strictly.** Unknown keys are refused rather than ignored, because a key
  `ssc` silently drops is a value its author believes is in effect. `frames:` is refused today
  and becomes `specs/frame-metadata/`'s.
- One file per asset, growing by section: `playback:` now, `frames:` next, the derivation
  recipe after that.

## Consequences

- The two records can disagree — a sidecar declaring sections for eight frames beside a set
  that now has six. `ssc index` resolves the sections against the frames it actually finds and
  refuses the mismatch, naming the section and the count. That check has to exist wherever a
  sidecar value is used against measured art, and it is not free.
- `ssc clean` gains nothing to do and nothing to avoid: the file is not in the record, so the
  rule it already follows is the rule that protects it.
- A second file per asset is a second thing to copy when an asset is moved by hand, and a
  second thing to remember in any future export or import.
- Reversing this means moving authored fields into `meta.json` and rewriting every workspace's
  records, which is why it is a record rather than a paragraph in `design.md`: people will
  have written these files by hand, and a hand-written file is not a migration you can run.
