---
autonomy: auto
ci: wait
---

# Harness accuracy

The instruction file `ssc init` writes — `CLAUDE.md` for Claude Code, `AGENTS.md` for
Codex and OpenCode — states things the CLI does not do: a `doctor` invocation that does
not parse, a defect map missing two checks and naming three fixes the code never emits,
and a cost section that points at the billed path for work a `tool` command does free.
This corrects the three texts and adds the test that would have caught the drift.

## Why

The harness doc is the first thing an agent driving a fresh workspace reads, and it is
the only thing standing between that agent and a bill. Every error found is one an agent
acts on rather than notices: `ssc tool doctor <asset>` exits `2`, a `seam` reported
`skipped` reads as clean, and `gen bgremove` bills for `fal-ai/birefnet/v2` when the same
model runs locally for nothing under the `[cv]` extra. The text drifted because nothing
holds it to the code — `tests/cli/test_harness.py` asserts only that one heading is
present — so the correction is only half the work and the test is the other half. Done
means the three files agree with the CLI and a future divergence fails CI.

## Paths

- `src/ssc/data/harness/claude/CLAUDE.md`
- `src/ssc/data/harness/codex/AGENTS.md`
- `src/ssc/data/harness/opencode/AGENTS.md`
- `tests/cli/test_harness.py`

## References

- `specs/agent-harness/` — that a target exists and installs. It puts the harness
  *contents* out of scope, so this plan is where the texts are owned.
- `docs/adr/0008-a-kind-is-a-profile-not-an-enum.md` — why the doc's kind list must not
  read as closed.

## Out of scope

- **New skills.** `background`, `box-art`, `banner` and `map` have no `sprite-*` skill
  driving them. That is real and it is a separate piece of work.
- **The four `sprite-*` skills' own texts.** Only the root instruction file is corrected
  here; the skills were not audited against the CLI.
- **Rewording a `fix` string that already resolves.** The code is the authority and the
  doc moves to meet it. One of them does not resolve — see task 3.1 — and that one is
  corrected in the code, because a doc cannot move to meet a command that exits `2`.

## Tasks

- [x] 1.1 (TDD) Pin every target's doc to the code — each `Check`, each built-in kind, and each default model named
- [x] 2.1 (Unit) Correct the `doctor` invocation to `--in` and `--kind`, and say `seam` and `nineslice` are opt-in
  _Depends 1.1_
- [x] 2.2 (Unit) Complete the defect map with `consistency` and `scale`, and align every fix to the string `doctor` emits
  _Depends 1.1_
- [x] 2.3 (Unit) Correct the cost section — `--seconds` over `--opt duration`, and the three background-removal paths by what each costs
  _Depends 1.1_
- [x] 2.4 (Unit) Name `gate`, `run`, `status`, `job` and `kind list`, and stop the kind list reading as closed
  _Depends 1.1_
- [x] 2.5 (Unit) Repair the wording the Codex and OpenCode variants lost
  _Depends 1.1_
- [x] 3.1 (TDD) Make every `fix` string `doctor` emits resolve against the CLI — `ssc
      tool cut --mode bbox` names no mode that exists

## Done when

- `uv run pytest tests/cli/test_harness.py` passes, and its new test fails when a `Check`
  is added to the enum without being named in all three docs.
- Every command and option named in the three docs resolves under `ssc --help`.
- `uv run pytest`, `uv run ruff check .`, `uv run mypy` and `npx @protonspy/scc validate`
  all pass.
