# Agent harness — design

## What changes

Serves R1.1–R4.2. Three pieces, mirroring how `skills.py` already ships data inside the
package.

```
src/ssc/
  data/
    harness/
      claude/           CLAUDE.md + .claude/rules/ + .claude/skills/ + .claude/command/
      codex/            AGENTS.md + .codex/rules/ + .codex/skills/ + .codex/command/
      opencode/         AGENTS.md + .opencode/rules/ + .opencode/skills/ + .opencode/command/
  cli/
    harness.py          read a target's payload via importlib.resources, install it
    commands/init.py    the --codex / --opencode flags, default claude
tests/cli/test_harness.py
```

`ssc.cli.harness` is the mechanical sibling of `ssc.cli.skills`: a `targets()` table maps an
agent name to its data directory, an `install(root, target)` walks the payload writing every
file with `write_new` (refusing an existing one, reporting kept), and `--dry-run` reports
without writing. The root instruction file lands at the workspace root — `CLAUDE.md` for
claude, `AGENTS.md` for codex and opencode — and its body carries a "Using `ssc`" section.

## Boundaries and contracts

**The payload lives in the package, not in the workspace.** The harness texts are the same
data `scc` uses to shape a project, so they ship as resources read with
`importlib.resources.files("ssc.data")`, exactly like `skills.shipped()`. A project that
pinned an older `ssc` gets the harness its commands support. This keeps `ssc init` from
needing the network or a separate payload checkout.

**Claude Code is the default because it already is.** Today `ssc init` writes the sprite
skills into `.claude/skills/` unconditionally; the new contract folds that into the claude
target's install (R3.5). `--no-skills` still strips the sprite-relay skills from the report
and the disk, but the harness rules and AGENTS.md/CLAUDE.md always land — they are the reason
the workspace is usable by an agent at all.

**The target is an exclusive choice, not a state machine.** Three flags would mean an agent
matrix; one optional argument plus a default is exactly three outcomes. `--codex` and
`--opencode` never compose (R1.4), and an unknown value is a usage error before anything is
written.

**Nothing overwrites; everything is reported.** `write_new` already enforces R3.4. The
install reports written versus kept file paths (relative, posix-style) under an `agent` key
in the result, so `--json` is self-describing (R4.1).

## Data

The payload root for each target is `src/ssc/data/harness/<agent>/`, copied as it stands
here so a project installs it byte-identical to this checkout:

- `claude/` — `CLAUDE.md` (with a "Using `ssc`" section) · `.claude/rules/` · `.claude/commands/`
- `codex/` — `AGENTS.md` (with a "Using `ssc`" section) · `.codex/rules/` · `.codex/commands/`
- `opencode/` — `AGENTS.md` (with a "Using `ssc`" section) · `.opencode/rules/` · `.opencode/commands/`

The sprite relay skills are not part of this payload. They are the same
`ssc.data.skills` resources `skills.shipped()` already installs today, and `harness.install`
hands `skills.install` the target's skill directory — `.claude/skills` for claude,
`<target>/skills` for the other two — so R3.5 reuses the existing relay instead of duplicating
it per target. Rules and commands are Markdown shipped alongside; nested skill payloads keep
the existing `SKILL.md` shape.

## Alternatives considered

**Reading the harness from the live source tree** — copying `.claude/` out of this checkout
at install time — was rejected: it works in a checkout and breaks from a wheel, and the
whole reason `skills` ships as data is that a pinned version must install its own payload.

**One shared payload rendered per agent** (interpolating the root filename) was rejected:
the harness texts already differ by carried directory, and a template with branching for
three agents is harder to audit than three explicit trees.

## Risks

- **The payload can grow stale.** The harness texts are this package's own copy, not read
  from `scc` at build time. When `scc` ships a new version, `ssc`'s copy has to be refreshed
  by a human; the manifest `scc-manifest.json` names the version that produced this checkout,
  so the refresh has a target.
- **Sprout and `--no-skills` interplay.** R3.5 ties the sprite relay to the target; if a
  later leaf moves the relay again, the harness spec and this one must move together.