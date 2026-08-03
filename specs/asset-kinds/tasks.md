# Asset kinds — tasks

**What already covers these paths:** `tests/cli/test_workspace.py` covers locating a
workspace and reading `ssc.yaml`, which is where a declared profile comes from;
`tests/cli/test_meta.py` covers the `kind` field this gives meaning to; and
`tests/cli/test_main.py` covers the command contract. All were run green before this work
started.

## 1 · The profile

- [x] 1.1 (Unit) Define a profile and the six built-ins — R1.1, R1.2
- [x] 1.2 (Unit) Resolve a kind from the built-ins and `ssc.yaml`, field by field, carrying where each came from — R1.3, R1.4, R2.3
- [x] 1.3 (Unit) Refuse a declaration naming a field that is not one, or a value the field cannot take — R1.5

## 2 · Discovering them

- [x] 2.1 (Unit) Build `ssc kind list` and `ssc kind show`, refusing a name that resolves to nothing — R2.1, R2.2, R2.4

## 3 · Using them

- [x] 3.1 (Unit) Refuse `ssc asset new` for a kind that resolves to nothing, and accept any that does — R3.1, R3.2
