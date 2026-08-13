# Agent harness — tasks

Covers the paths `ssc init` already exercises. Existing tests that touch this work, run
before anything is written:
`tests/cli/test_workspace.py` (init contract, R1.1–R1.6), `tests/cli/test_skills.py`
(relay install, report shape), `tests/cli/test_main.py` (exit codes, --json/--dry-run).

## 1 · The payload

- [x] 1.1 (Unit) Ship the three harness trees under `ssc.data.harness` — claude carries `CLAUDE.md` and `.claude/`; codex and opencode carry `AGENTS.md` and their own `.codex/` / `.opencode/` — taken from this checkout's harness — R3.1, R3.2, R3.3
- [x] 1.2 (Unit) Put a "Using `ssc`" section in every root instruction file (`CLAUDE.md`, both `AGENTS.md`) — R2.1, R2.2

## 2 · The installer

- [x] 2.1 (Unit) `harness.install` — copy a target's payload into `<root>/`, writing new files and keeping (never overwriting) files already there — R3.4
- [x] 2.2 (Unit) Hand the sprite relay skills to the selected target's skill directory, so codex/opencode get them where their agent reads them — R3.5

## 3 · The command

- [x] 3.1 (Unit) `ssc init` selects the harness: no flag → claude, `--codex`, `--opencode` — and a conflict of the two flags is a usage error that writes nothing — R1.1, R1.2, R1.3, R1.4
- [x] 3.2 (Unit) The init result reports the agent and its written/kept files; `--json` carries them; `--dry-run` writes nothing — R4.1, R4.2

## Notes

The harness payload is the harness data this checkout carries, so each copied file no longer
needs hand-maintaining the moment it is installed — a refresh later means re-copying from the
harness source, which is a decision for a future leaf if the payload drifts.