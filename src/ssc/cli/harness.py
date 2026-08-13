"""The coding agent's harness a workspace gets, shipped inside the package.

A workspace `ssc init` creates is meant to be driven by a coding agent, and the three —
Claude Code, OpenAI Codex, OpenCode — each read their instructions from a different file
and keep their skills in a different tree. A workspace that came up without the agent
that will drive it loses its first session to reverse-engineering the CLI, so `ssc init`
lays the selected agent's instruction file and the sprite relay where that agent reads
them.

The payload is `ssc.data.harness.<agent>`, read with `importlib.resources` like the
skills, so this works from a wheel as much as from a checkout. Nothing in here is the
`scc` harness: the doc this ships is the sprite/UI/asset context, not a development
methodology — see `src/ssc/data/harness/<agent>/CLAUDE.md` and `AGENTS.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from ssc.cli.atomic import write_new
from ssc.cli.skills import Installed as SkillsInstalled
from ssc.cli.skills import install as install_skills


@dataclass(frozen=True)
class Target:
    """One agent's harness: the root instruction file it reads, and where its skills go."""

    name: str
    instruction_file: str
    skills_dir: str


TARGETS: tuple[Target, ...] = (
    Target("claude", "CLAUDE.md", ".claude/skills"),
    Target("codex", "AGENTS.md", ".codex/skills"),
    Target("opencode", "AGENTS.md", ".opencode/skills"),
)


def target(name: str) -> Target:
    for one in TARGETS:
        if one.name == name:
            return one
    raise ValueError(f"no harness target named {name!r}")


def instruction_text(t: Target) -> bytes:
    """The root instruction file for a target, shipped inside the package."""
    root = resources.files("ssc.data").joinpath("harness").joinpath(t.name)
    return root.joinpath(t.instruction_file).read_bytes()


@dataclass(frozen=True)
class Installed:
    """What an install did: the agent it installed, and what it wrote and kept.

    `written` and `kept` are relative paths (posix-style) so `--json` is self-describing:
    the instruction file first, then the skills.
    """

    agent: str
    written: tuple[str, ...]
    kept: tuple[str, ...]
    skills: SkillsInstalled


def empty_skills() -> SkillsInstalled:
    return SkillsInstalled(written=(), kept=())


def install(
    root: Path, agent_name: str, *, with_skills: bool = True, dry_run: bool = False
) -> Installed:
    """Install one agent's harness into `root`.

    `with_skills=False` lays out only the root instruction file — `ssc init --no-skills`
    is why that exists. Nothing overwrites (R3.4): a file already there is kept and
    reported, because a project may have edited its instruction file or relay, and an
    install that silently reverted that edit is worse than one that says it did nothing.
    """
    t = target(agent_name)
    written: list[str] = []
    kept: list[str] = []
    relative = t.instruction_file

    if dry_run:
        written.append(relative)
    elif (root / relative).exists():
        kept.append(relative)
    else:
        write_new(root / relative, instruction_text(t))
        written.append(relative)

    skills_installed = (
        install_skills(root, skills_dir=t.skills_dir, dry_run=dry_run)
        if with_skills
        else empty_skills()
    )
    written.extend(skills_installed.written)
    kept.extend(skills_installed.kept)
    return Installed(
        agent=agent_name,
        written=tuple(written),
        kept=tuple(kept),
        skills=skills_installed,
    )
