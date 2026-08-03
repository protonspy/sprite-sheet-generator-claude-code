# Workspace foundation — design

## What changes

Serves R1.1–R1.6, R2.1–R2.5, R3.1–R3.6, R4.1–R4.5, R5.1–R5.3, R6.1–R6.3.

`src/ssc/` today is an empty package. This leaf fills it with the two layers every later
command plugs into, plus the three commands that exercise them end to end: `ssc init`,
`ssc asset new`, `ssc clean`. Resolving a stage to a file lands as a function rather than a
command, because the command that exposes it is `specs/asset-listing/`'s.

```
src/ssc/
  core/           pure: ndarray in, ndarray out, no IO
    resize.py       the one resampler (R4.4)
  cli/            impure: filesystem, cache, lineage, JSON
    errors.py       SscError and the exit codes (R4.2, R4.5)
    output.py       one result object, rendered as JSON or as prose (R4.1)
    atomic.py       temp-plus-rename writes (R3.6)
    workspace.py    finding the root, ssc.yaml (R1.1–R1.6)
    meta.py         the asset record: files, stages, classes (R2, R3, R6)
    cache.py        content-addressed results (R5)
    main.py         the click group and the shared options
    commands/       init.py · asset.py · clean.py
tests/                mirrors src/, plus test_no_other_resampler.py
```

The layer boundary is **purity, not user interface** — which is why `workspace.py` and
`cache.py` sit under `cli/` despite having nothing to do with argument parsing.
`.claude/rules/project.md` draws the line there deliberately: `core/` is what can be tested
against an 8×8 array with no directory in sight, and everything else is the other side.

## Boundaries and contracts

**Everything a command prints is one object.** A command builds a `Result` and returns it;
`main.py` renders it — as JSON when `--json` is given, as prose otherwise — and maps it to
an exit code. Commands never call `print`, and nothing writes to stdout except that final
render, which is what makes R4.1's "and nothing else" enforceable rather than aspirational.

**Errors are values with a fix.** `SscError` carries `code` (stable, machine-readable),
`message`, an optional `fix` naming the command that resolves it, and an exit code. The
`fix` field is the same shape a `doctor` finding will carry and the same shape a `gen`
refusal will carry, so a harness learns it once.

| Exit | Meaning | Raised as |
|---|---|---|
| `0` | success | no error |
| `1` | error — the command ran and failed | `SscError` |
| `2` | invalid usage — the command should not have been called this way | `UsageError` |
| `3` | a gate is pending | reserved; nothing here raises it |

**Nearest neighbour is enforced, not documented.** `core.resize()` is the only function
permitted to resample, and a test walks the AST of `src/` and fails on any other `resize`
call. The plan is explicit that one careless bilinear resize undoes all of M1 and that the
damage is invisible until 4× zoom — so this is a test, not a review convention.

**One object means one place to redact (R4.6).** Because every command's output crosses
`render`, that is where a credential is replaced by `***` — the deliberate message a leaf
composes from a provider's response as much as the catch-all's `str(exception)`. Two rules,
because a credential arrives two ways: by *value*, matching anything the environment holds
under a secret-looking name, which catches a leak in a format nobody predicted; and by
*shape*, matching `api_key=…` or `Authorization: Bearer …`, which catches a credential that
never passed through this process's environment. The traceback on stderr goes through the
same guard, because stderr is what a CI log keeps. Nothing here holds a secret today —
`gen-fal` is the first leaf that will, and the guard has to exist before it rather than
after the first key reaches somebody's log.

**One gate, not one per route (R2.5, asset-listing R4.1).** An asset directory is validated
where it is resolved, not where it is used. `under_assets` refuses one that resolved out of
`assets/` through a link, and every route passes through it — `list`, `show`, `recover`,
and the two that *create*, `asset new` and `tool slice` — because guarding some of several
routes is the same as guarding none. The creating routes check twice, before and after
`mkdir`: the first check runs against a `<kind>/` that may not exist yet, and a missing
component resolves to itself, so a link planted in between would otherwise be created
through. `addressed` adds the layout check (no subdirectory but `frames/`) and is used
where a caller *named* one asset and is about to read or write it. Deliberately not on the
workspace scan: refusing to list a workspace over one asset's stray directory takes down
`list`, `clean` and every unrelated asset with it, and the read paths here skip what they
cannot use rather than aborting.

**Nothing overwrites.** Every write goes through a helper that refuses an existing path
(R3.5). Combined with "every command writes a new file", the recovery story for any mistake
is `git checkout`, and there is no state to unwind.

## Data

**`ssc.yaml`** — the workspace root marker, and deliberately almost empty. Kind profiles,
budget and palette belong to later leaves; what this one owns is the schema version.

```yaml
schema: 1
```

**`meta.json`**, one per asset, at `assets/<kind>/<key>/meta.json`:

```json
{
  "schema": 1,
  "key": "hero",
  "kind": "character",
  "created_at": "2026-08-02T21:00:00Z",
  "files": [
    {
      "path": "001_anchor_s.png",
      "stage": "anchor",
      "class": "source",
      "sha256": "…",
      "produced_by": {"command": "gen image", "params": {}, "cache_key": null},
      "derived_from": [],
      "written_at": "2026-08-02T21:00:00Z"
    }
  ]
}
```

- `path` is relative to the asset directory, so an asset survives being moved.
- `stage` is the address (R3.3), and it is unique within an asset (R3.4).
- `class` decides deletability (R6) and is the only field `ssc clean` reads.
- `derived_from` names paths inside the same asset, which is what makes the chain
  reconstructible without parsing filenames.

**Filenames** are `<NNN>_<label>.<ext>`, where `NNN` is the next unused three-digit prefix
and `label` accumulates the stages applied so far: `001_anchor_s.png` →
`002_anchor_s.snap.png` → `003_anchor_s.nobg.png`. The prefix orders one `ls`; it is never
an address (R2.4), because inserting a step in the middle would otherwise renumber
everything downstream and break every script that hard-coded `003`.

**The cache key** is `sha256` over a canonical JSON document:

```json
{"command": "tool snap", "params": {}, "inputs": ["<sha256 per input file>"], "salt": {}}
```

`params` is sorted and holds only what changes the result. `salt` exists because two later
leaves must join the key without redesigning it — `model-registry` adds the model id,
`cv-runtime` adds the execution provider — and the plan is explicit that a cache
conflating those is worse than no cache. Entries live at `cache/<key[:2]>/<key>`, so
`cache/` is a content-addressed store with no index to corrupt and no migration when its
shape changes: deleting it is always safe (R5.3).

## Alternatives considered

**Grouping by stage rather than by kind** — `images/`, `videos/`, `frames/`, `sprites/`,
with the key underneath — was the original design document's layout, and this leaf reverses
it. It answers "where are the videos" well and "what exists of kind `tile`" badly, and the
second is the question an operator and an agent actually ask. Kind-first also keeps an
extensible kind system honest: a project-defined kind gets a directory rather than a
special case. This is the hardest thing in the plan to change later, so it is
`adr:0007-group-assets-by-kind-then-key`.

**Addressing files by their numbered prefix** was rejected for the renumbering reason
above: the stage name is the address, the prefix is presentation.

**A cache index** — SQLite, or a JSON manifest — was rejected because it is a second source
of truth about what is cached, and its failure mode is an index that disagrees with the
directory, which survives unnoticed. Content addressing makes the filename the index.

## Risks

- **`meta.json` is rewritten whole on every write.** At the scale this tool works at — tens
  of files per asset — that is irrelevant, and it is what makes the atomic write trivial.
  It stops being irrelevant if something ever records 200 frames as 200 separate entries;
  a frame set is one entry with a directory in it, and `specs/frame-recovery/` has to keep
  it that way.
- **`salt` is a guess about the future**, shaped from two known needs. If a third arrives
  that does not fit "extra fields folded into the key", the key function changes and every
  cached entry misses — wasteful, not wrong.
