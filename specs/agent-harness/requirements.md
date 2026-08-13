---
autonomy: auto
ci: wait
lang: en
---

# Agent harness — requirements

## Purpose

A workspace `ssc init` creates is meant to be driven by a coding agent. That agent is one
of Claude Code, OpenAI Codex or OpenCode, and the three read their instructions from
different places: Claude Code reads `CLAUDE.md` and the `.claude/` tree, Codex and OpenCode
read `AGENTS.md` and their own `.codex/` / `.opencode/` trees. A workspace that came up
without the agent it will be driven by loses the first session to reverse-engineering the
CLI. This leaf makes `ssc init` lay out the selected agent's harness and its instruction
file alongside the sprite workspace, so a fresh directory is already shaped for the agent.

## R1 · Selecting the agent

- **R1.1** When `ssc init` runs and the user names no agent, the `ssc` CLI shall lay out the
  Claude Code harness and write `CLAUDE.md`.
- **R1.2** When `ssc init --codex` runs, the `ssc` CLI shall lay out the Codex harness and
  write `AGENTS.md`.
- **R1.3** When `ssc init --opencode` runs, the `ssc` CLI shall lay out the OpenCode harness
  and write `AGENTS.md`.
- **R1.4** If `ssc init` is given both `--codex` and `--opencode`, then the `ssc` CLI shall change
  nothing and exit `2`.

## R2 · The instruction file

- **R2.1** When `ssc init` writes `CLAUDE.md`, the `ssc` CLI shall write it at the workspace
  root, and it shall carry instructions on how to drive `ssc`.
- **R2.2** When `ssc init` writes `AGENTS.md`, the `ssc` CLI shall write it at the workspace
  root, and it shall carry instructions on how to drive `ssc`.

## R3 · The harness tree

- **R3.1** When `ssc init` selects Claude Code, the `ssc` CLI shall lay out the harness under
  `.claude/`.
- **R3.2** When `ssc init` selects Codex, the `ssc` CLI shall lay out the harness under
  `.codex/`.
- **R3.3** When `ssc init` selects OpenCode, the `ssc` CLI shall lay out the harness under
  `.opencode/`.
- **R3.4** The `ssc` CLI shall not overwrite a harness file that already exists, and shall
  report it as kept rather than written.
- **R3.5** The `ssc` CLI shall lay out the sprite skills into the selected agent's harness
  tree, exactly where it lays them out for Claude Code today.

## R4 · The report

- **R4.1** When `ssc init` lays out an agent harness, the `ssc` CLI shall report in its JSON
  which agent it laid out and which files it wrote and kept.
- **R4.2** When `--dry-run` is given, the `ssc` CLI shall write nothing and report what the
  selected agent's layout would have written, in addition to the workspace files
  `workspace-foundation R4.3` already reports.

## Out of scope

- **The harness contents.** What lives in `.claude/rules/` and the skills is shipped as the
  same payload `scc` lays out here; this leaf owns that a target exists and installs, not
  what the texts say.
- **Synchronizing the sprite skills.** `.claude/skills/sprite-*` are the sprite relay, the
  `adr`/`codewiki`/`glossary`/`plan-run`/`prd`/`stack`/`wiki` skills are the harness; both
  install, and neither updates after `ssc init`.
- **Other agents.** A fourth agent's harness is a future leaf; the target enum here is
  exactly three.