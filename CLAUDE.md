# CLAUDE.md

Spec-driven development, scaffolded and checked by `scc`. Keep this file short —
the methodology lives in `.claude/rules/`. Never inline it here.

## Rules — `.claude/rules/<name>.md`

Claude Code loads `.claude/rules/` into your context at session start, so these are already
in front of you and there is nothing to open. What the triggers below tell you is *when*
each rule governs — the failure they prevent is not a rule you never read, it is a rule
you had all along and applied at the wrong moment, or not at all.

Triggered by where you are in the work:

- `autonomy.md` — at kickoff, before writing anything
- `routing.md` — work arrives and needs a vehicle: a spec, or a plan
- `methodology.md` — starting a task: which cycle, what to run first
- `verification.md` — code is written and you think it is done
- `delivery.md` — last task done: branch, review, PR

Triggered by what you are about to touch:

- `project.md` — **before you run any build, test, lint, or format command.** This
  project's commands exist nowhere else: `scc` ships the file as a stub for the team
  to fill in, and runs none of them itself. A command that did not come from there is
  a guess, and a guessed test command that exits 0 looks exactly like a passing suite.
- `code-search.md` — **before you go looking for code you have not read yet.** This
  workspace keeps a symbol graph, and a structural question answered from it costs one
  call instead of a grep and six reads.
- `specs.md` — writing requirements, design, or tasks for a spec
- `tasks.md` — working through a spec's task list
- `knowledge-base.md` — something was learned, or a decision was made

## Layout

```
specs/<feature>/   requirements.md · design.md · tasks.md
plans/<name>.md    structure, plus a checklist and/or spec references
docs/              knowledge base — wiki, adr, codewiki, glossary, stack

.claude/rules/ — the methodology above
.claude/skills/ — authoring each part of docs/, and running a plan group by group
.claude/commands/ — the same skills on demand: /scc-plan-run, /scc-wiki, /scc-adr, …
```

## Checking your work

`scc validate` — or `npx @protonspy/scc validate` if not installed (`@<version>` pins for CI).
`scc update` brings a newer scc's rules and agents in: it shows the plan, then asks.

Exit `0` ok · `1` could not run · `2` ran and found something. A finding is an answer, not a crash.

`scc` checks artifact *shape* only; it never reads source, so whether the code honors
the artifact is on you.

<!-- rtk-instructions v2 -->
## RTK
Prefix EVERY command with `rtk`, including each link in a `&&` chain (`rtk git add . && rtk git commit -m "x"`).
No dedicated filter means it passes through unchanged — always safe.

Covered:
- cargo build/check/clippy/test, go test, tsc, lint, prettier, next build
- jest, vitest, playwright, pytest, rspec, rake test, test `<cmd>`
- git (all subcommands)
- gh pr view/checks, gh run list, gh issue list, gh api
- pnpm, npm run, npx, prisma, uv run
- ls, read, grep, find
- err, log, json, deps, env, summary, diff
- docker, kubectl, curl, wget

Meta: `rtk gain [--history]`, `rtk discover`, `rtk proxy <cmd>` (no filtering), `rtk init [--global]`
Caveat: `rtk grep` with `-c -l -L -o -Z` runs raw.
<!-- /rtk-instructions -->
