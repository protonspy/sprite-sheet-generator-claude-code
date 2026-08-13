"""The harness skills a workspace gets, shipped inside the package.

The four `sprite-*` skills are a template, not a file somebody copies out of this
repository. `ssc` is the CLI a game project installs, so the runs it drives have to
arrive with it: `ssc init` writes them into `.claude/skills/`, the same way it writes
`ssc.yaml` and `assets/`. A project that pinned an older `ssc` gets the skills that
older commands actually support, which is the reason to ship them as data rather than to
document a copy step nobody re-runs on upgrade.

They are read from `ssc.data.skills` with `importlib.resources`, so this works from a
wheel as much as from a checkout.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError

#: Where a workspace keeps them. The harness reads `.claude/skills/<name>/SKILL.md`, so the
#: layout is the harness's and not ours to choose.
SKILLS_DIR = ".claude/skills"
SKILL_FILE = "SKILL.md"


@dataclass(frozen=True)
class Skill:
    """One shipped skill: the directory name it installs under, and its text."""

    name: str
    text: str


def shipped() -> tuple[Skill, ...]:
    """Every skill in the package, by name.

    Sorted so two installs write the same list in the same order — `ssc init --json`
    reports what it wrote, and a report that reorders between runs is a diff nobody made.
    """
    root = resources.files("ssc.data").joinpath("skills")
    found = []
    for entry in sorted(root.iterdir(), key=lambda item: item.name):
        skill = entry.joinpath(SKILL_FILE)
        if not skill.is_file():
            continue
        found.append(Skill(name=entry.name, text=skill.read_text(encoding="utf-8")))
    return tuple(found)


@dataclass(frozen=True)
class Installed:
    """What an install did: the skills written, and the ones already there.

    Two lists rather than one count, because they mean different things to the person
    reading the result — `kept` is a skill this workspace already had, which is not a
    failure and not something to overwrite.
    """

    written: tuple[str, ...]
    kept: tuple[str, ...]


def install(root: Path, *, skills_dir: str = SKILLS_DIR, dry_run: bool = False) -> Installed:
    """Write every shipped skill into `<root>/<skills_dir>/<name>/SKILL.md`.

    `skills_dir` is relative to the workspace root and names where the target agent reads
    skills — `.claude/skills` for Claude Code, `.codex/skills` and `.opencode/skills` for
    the other two. Nothing overwrites: a skill whose `SKILL.md` is already there is kept
    and reported, because a project may have edited the relay for its own art pipeline and
    an install that silently reverted that edit is worse than one that says it did nothing.
    """
    base = root / Path(skills_dir)
    written: list[str] = []
    kept: list[str] = []
    for skill in shipped():
        relative = f"{skills_dir}/{skill.name}/{SKILL_FILE}"
        if (base / skill.name / SKILL_FILE).exists():
            kept.append(relative)
            continue
        if dry_run:
            written.append(relative)
            continue
        (base / skill.name).mkdir(parents=True, exist_ok=True)
        with Directory.open(base / skill.name) as held:
            try:
                held.write_new(SKILL_FILE, skill.text.encode("utf-8"))
            except SscError:
                # Between the check above and this write somebody else installed it. The
                # refusal is `write_new`'s and it is the right one; here it means kept.
                kept.append(relative)
                continue
        written.append(relative)
    return Installed(written=tuple(written), kept=tuple(kept))
