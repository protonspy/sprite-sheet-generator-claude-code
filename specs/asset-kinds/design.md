# Asset kinds — design

## What changes

Serves R1.1, R1.3, R1.4, R2.3, R3.1.

One new module, `cli/kinds.py`, and one command group, `ssc kind`. It is in `cli/` and not
`core/` because a profile comes off disk — `ssc.yaml` — and `core/` takes arrays and
dataclasses, not files.

The decision itself is `adr:0008-a-kind-is-a-profile-not-an-enum`, and the shape follows from
it: profiles are **data**, built-ins are a dict in the package, a project's are a `kinds:`
map in `ssc.yaml`, and resolution merges the two field by field.

## Where each field came from

R2.3 asks for the *provenance* of each field, not just its value, and that is the part worth
building rather than assuming. A project overriding one field of `character` and inheriting
five is the ordinary case, and "why is my cell 32" is the question a person actually asks. So
resolution returns the value **and** its source, and `kind show` prints both.

This is also what keeps built-ins honestly documented as defaults: a later `ssc` may ship a
different built-in cell, and a project that inherited one can see that it did.

## Reading, not branching

R3.1 is the requirement this leaf exists to make enforceable. `if kind == "character"`
anywhere in this codebase is the defect the ADR names, and it cannot be prevented by a type —
so it is a review target and a grep, not a mechanism. What the design *can* do is make the
right thing easy: `resolve(name)` returns a profile, every field is on it, and no consumer
ever needs the name for anything but a lookup.

## Alternatives considered

**A `kinds.yaml` of its own, rather than a key in `ssc.yaml`.** Rejected: a workspace already
has one file that says what this project is, and a second one is a second thing to find, to
validate and to keep in step. `ssc.yaml` is almost empty today precisely so that leaves like
this one can fill it.

**Validating a profile lazily, when a command uses it.** Rejected in favour of validating on
read (R1.5): a typo in `ssc.yaml` should be a refusal from `kind list`, not a wrong cell size
surfacing three commands later as art that is subtly the wrong size.

That promise only holds if it covers every field, and the first version did not: `cell`,
`checks` and the booleans were checked while the name fields were coerced with `str()`,
which accepted a map, a null and a boolean without a word. `anchor` and `atlas_layout` have
real domains — `core.assemble` implements three anchors — so they are checked against them.

## Reading a file nobody wrote carefully

`ssc.yaml` is the first structured input this tool parses beyond a schema number, and it is
a file that survives hand-editing by an agent. So it is bounded in size before it is read,
its document shape is checked before anything indexes into it, `RecursionError` is caught
alongside `YAMLError` because PyYAML's scanner raises the former on deeply nested flow
collections, and anchors are refused: `safe_load` does not bound alias expansion, and six
levels of them is a kilobyte on disk and hundreds of millions of nodes in memory.
