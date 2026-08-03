# Asset listing — tasks

**What already covers these paths:** nothing reads the workspace back yet, so the covering
tests are the ones for the record and the contract this leaf reads through —
`tests/cli/test_meta.py` (stage resolution, `AssetMeta` loading), `tests/cli/test_workspace.py`
(locating a workspace and building an asset path), `tests/cli/test_main.py` (`--json`,
`--dry-run`, exit codes) and `tests/test_smoke.py` (the wired CLI). All four were run green
before this work started and must stay green after it. `tests/cli/test_doctor.py` covers
the `load_input`/`measure` pair `show` calls for R3.8.

## 1 · Reading the workspace back

- [x] 1.1 (Unit) Classify a recorded file as image, video or neither from its extension — R1.1, R1.2
- [x] 1.2 (Unit) Walk every asset's `meta.json` in kind, key and chain order — R2.6
- [x] 1.3 (Unit) Resolve an asset from `<kind>/<key>` or a bare `<key>`, refusing an ambiguous one — R3.2, R3.3
- [x] 1.4 (Unit) Walk a file's lineage transitively, refusing a cycle — R3.6, R3.7

## 2 · The two commands

- [x] 2.1 (Unit) Build `list` over one medium, with the kind, `--stage` and `--class` filters — R2.1, R2.2, R2.3, R2.4, R2.5, R2.7
- [x] 2.2 (Unit) Build `show`: the stage, the default of the chain's last file, and the refusal naming the stages there are — R3.1, R3.4, R3.5
- [x] 2.3 (Unit) Attach `doctor` to a shown image, skip it with a reason otherwise, and honour `--no-doctor` — R3.8, R3.9, R3.10
- [x] 2.4 (Unit) Wire `image` and `video` onto the CLI from one factory and cover both end to end — R2.1, R2.2, R3.1
- [x] 2.5 (Unit) Re-resolve an asset directory and a recorded path before reading either, so a symlink cannot move the target after validation — R4.1, R4.2
