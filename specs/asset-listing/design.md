# Asset listing — design

## What changes

Serves R1.1, R1.2, R2.1, R2.2, R2.6, R3.1, R3.2, R3.4, R3.6, R3.8.

Two new modules and no change to anything that exists:

- **`src/ssc/cli/listing.py`** — reading the workspace back. It walks `assets/*/*/meta.json`,
  classifies each recorded file by medium, resolves an asset from a `<kind>/<key>` or bare
  `<key>` address, and walks a file's lineage. Nothing here is a command, which is what
  lets `show`'s stage resolution be tested against a hand-built `AssetMeta` rather than
  through the CLI.
- **`src/ssc/cli/commands/media.py`** — the `image` and `video` groups. They differ in
  exactly one value, the medium they filter on, so both are built by one factory rather
  than written twice. `ssc video list` differing from `ssc image list` by a typo in one of
  the two copies is the failure that costs a day to see.

`app.py` gains two `add_command` lines. `meta.py`, `workspace.py` and `output.py` are
untouched: the record already carries everything both commands report, which is the point
of `workspace-foundation` having recorded it.

**The noun scopes `show`, not just `list`.** `ssc video show hero` considers only the
videos in that asset's chain, which is what R3.4's default and R3.5's refusal are written
against. Without it the two `show` commands would be one command reachable by two names,
and a caller asking for the last video of a mixed asset would get whatever image happened
to be written after it.

`show` reaches into `sheet-doctor` for R3.8 by calling `commands.doctor.load_input` and
`commands.doctor.measure` with no parameters. That is a CLI-layer module importing another
CLI-layer module, not `core` reaching sideways, and it keeps the ceilings on decode size
that `doctor` already enforces — `show` reads files somebody downloaded, so it inherits
the same exposure.

## Data

Nothing is written. One shape describes a recorded file everywhere it appears —
`{kind, key, stage, class, path, media, sha256, derived_from, produced_by}` — and both
commands emit it: `list` as `files` plus `unclassified`, naming any recorded file whose
extension placed it in neither medium (R1.2); `show` as `file`, as each element of
`lineage` ordered root-first, and alongside `doctor`, which is `sheet-doctor`'s report or
`null` with a `doctor_skipped` reason beside it (R3.9).

One shape rather than a narrower one for `list`: a caller that has to re-fetch a file
through `show` to learn its `sha256` is a caller making two calls where the first already
held the answer, and a second shape is a second thing to keep in step. A recorded file that is not on disk takes that same path rather
than failing the command: the record is the only thing that explains where the file went,
so refusing to print it is refusing to answer the question that was asked.

The `unclassified` field is why R1.2 exists rather than the obvious "ignore it". A file
that is recorded and appears in no listing is invisible to the only caller that cannot
run `ls`, and invisible is the one thing this leaf is built to prevent.

## Alternatives considered

**The medium: derived from the extension, not recorded in `meta.json`.** The alternative is
a `media` field on `FileRecord`, set by whichever command wrote the file. Deriving won on
two grounds. A recorded field can disagree with the file — `meta.json` is hand-editable and
this project's own error path tells people to fix it by hand — and a derived one cannot.
And it costs `workspace-foundation` a delta, a schema bump and a field every future
`record()` call site has to remember, to store something that is a pure function of a string
already in the record. The cost of being wrong is small and symmetrical: adding the field
later is additive, and the classifier stays as the fallback for records written before it.

Not an ADR. Reversing it is one field and one migration on a schema with no data in the
world yet, which is `design.md`'s side of the line in [knowledge-base.md](../../.claude/rules/knowledge-base.md).

**A bare key is accepted, and ambiguity refuses.** `adr:0007-group-assets-by-kind-then-key`
made keys unique per kind rather than globally, so `show hero` can genuinely mean two
assets. Requiring `<kind>/<key>` always would make the common case — one asset with that
key — needlessly verbose for the agent this leaf exists for. Guessing between two would be
worse than either. So: resolve when unambiguous, refuse and name the candidates when not
(R3.3), which is the same shape as every other refusal here — a code, a message, and a
`fix` the caller can run.

## Risks

**A symlink moves the target after the string was validated.** `check_relative_path`
validates a recorded path as text — relative, forward-slashed, no `..` — which cannot see
that a segment is a symlink pointing elsewhere on disk. So R4.2 needs a second gate that
resolves at the moment of acting, and the place it belongs moved once.

It began as `inside`, shared with `clean` and hung on `Entry.file` so that every read went
through it. That was a check standing *next to* a read rather than part of one: `show`
tested a resolved path and opened it a statement later, which is the same window
`workspace-foundation` R3.7 spent three tasks closing on the writes. The gate is now
`Directory.read`, which descends through the held directory — `O_NOFOLLOW` per segment on
POSIX, the resolved path against a just-re-identified directory on Windows — so
containment and the read are one act and `Entry.file` is gone rather than left as a second
way to reach the same file. `inside` stays for `clean`'s pre-flight, which is a *report* of
what a sweep would remove and not the guard; `Directory.delete` is that.

`placed` is the other half (R4.1), and it has to sit on **every** route to an asset
directory — the glob in `asset_dirs`, the `<kind>/<key>` branch of `resolve`, which never
touches that glob, and the three routes that create one. Guarding some of them is the same
as guarding none: the first attempt here guarded only the glob, and `ssc image show
character/hero` still read an asset directory that had left the workspace. The link does
not even need a privilege — a Windows directory junction is unprivileged, which is why the
tests make one rather than skipping the platform this project is developed on.

**Escaping is not the only way to be the wrong directory**, and the function was named
after the weaker half. `under_assets` proved a directory resolved somewhere *under*
`assets/`, which admits `assets/character/hero` linked to `assets/icon/coin`: it never
leaves the workspace, so every check passed, and `show character/hero` reported
`icon/coin`'s record under the name that was asked for. The address is the caller's whole
statement of which asset it means, so the check is that the directory resolves to exactly
the `<kind>/<key>` place naming it. That subsumes the escape and costs nothing legitimate
— a `<kind>/` link pointing off the disk already failed the weaker test — and the rename
to `placed` is part of the fix rather than tidying: a name that describes half the check is
how the other half went missing.

`assets/` itself being a link stays deliberately allowed. It is the root both sides resolve
against, so a workspace whose art lives on another disk keeps working.

All of them refuse rather than skipping silently: an asset that is quietly not there is the
failure mode this leaf exists to remove.

**A lineage cycle is reachable through a hand-edited `meta.json`.** `derived_from` is a
list of paths validated for escape, not for acyclicity, so `a → b → a` survives being
loaded and would spin the walk forever. R3.7 makes it a refusal with the offending file
named; the walk carries a seen-set and stops at the second visit. This is the only loop in
the leaf and it reads untrusted input, so it is worth the four lines.
