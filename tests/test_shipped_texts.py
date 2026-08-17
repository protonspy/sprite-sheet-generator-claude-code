"""The texts `ssc init` writes into a workspace — `specs/model-pricing/` R4.1-R4.5.

The agent driving a workspace reads these, not this repository's specs. A model named in
one of them that the registry does not carry is a paid call that fails with
`unknown-model`, and nothing else in the suite would notice: they are Markdown, so no
import and no schema binds them to `models.json`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import click
import pytest

from ssc.cli.app import main

DATA = Path(__file__).resolve().parent.parent / "src" / "ssc" / "data"

#: The accounts this project's endpoints live under. A backticked token starting with one
#: of these is being named as a model, which is what makes it checkable.
ACCOUNTS = ("fal-ai/", "openai/", "xai/", "bytedance/")

#: Anything inside backticks. Endpoints are always written that way in these texts, and
#: reading prose without them would match the wiki's sentences about the providers.
BACKTICKED = re.compile(r"`([^`\n]+)`")

HARNESS = sorted(DATA.joinpath("harness").rglob("*.md"))
SKILLS = sorted(DATA.joinpath("skills").glob("*/SKILL.md"))


def registry_endpoints() -> set[str]:
    document = json.loads(DATA.joinpath("models.json").read_text(encoding="utf-8"))
    return {model["endpoint_id"] for model in document["models"]}


def endpoints_named_in(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return {
        token
        for token in BACKTICKED.findall(text)
        if token.startswith(ACCOUNTS) and " " not in token
    }


@pytest.mark.parametrize("path", HARNESS + SKILLS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_endpoint_a_shipped_text_names_is_in_the_registry(path: Path) -> None:
    """R4.5 — the one fact about these texts a machine can check."""
    known = registry_endpoints()

    unknown = sorted(endpoints_named_in(path) - known)

    assert not unknown, f"{path.name} names {unknown}, which the registry does not carry"


@pytest.mark.parametrize("path", HARNESS, ids=lambda p: p.parent.name)
def test_the_instruction_file_names_the_default_for_each_media(path: Path) -> None:
    """R4.1 — the default is what a call uses when nothing else says, so an agent that has
    to generate once to find out has already paid to learn it."""
    core = json.loads(DATA.joinpath("core.json").read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")

    assert "## Choosing a model" in text
    for media, endpoint in core["defaults"].items():
        assert endpoint in text, f"{path.name} does not name the {media} default"
    assert "ssc model list" in text
    assert "ssc model show" in text


@pytest.mark.parametrize("path", HARNESS, ids=lambda p: p.parent.name)
def test_the_instruction_file_names_what_moves_the_cost(path: Path) -> None:
    """R4.2 — the four core concepts that multiply a call, named as the levers they are."""
    text = path.read_text(encoding="utf-8")

    for option in ("--count", "--size", "--quality", "--seconds"):
        assert option in text, f"{path.name} does not name {option}"
    assert "ssc budget" in text


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_names_the_model_its_paid_calls_reach_for(path: Path) -> None:
    """R4.3 — a skill that says `gen image` and no more leaves the choice to a habit."""
    text = path.read_text(encoding="utf-8")

    assert endpoints_named_in(path), f"{path.parent.name} names no model"
    assert "paid call" in text


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_says_what_to_set_at_each_end_of_the_work(path: Path) -> None:
    """R4.4 — `--count` and `--quality` are the two ends: several cheap candidates, then the
    chosen one at full quality."""
    text = path.read_text(encoding="utf-8")

    assert "--count" in text, path.parent.name
    assert "--quality" in text, path.parent.name


# --- skill-coverage R3.1-R3.2: the text answers to the CLI -------------------------

#: Words that end an invocation's command path: a placeholder, a flag, a quoted value, a
#: shell construct. Anything else bare is either a subcommand or an argument, and which one
#: it is depends on whether the node reached so far takes subcommands.
STOPS = ("-", "<", "[", "{", "(", '"', "'", "$", "|")

TRAILING = ".,;:!?)`'"


def command_tree() -> dict[tuple[str, ...], tuple[bool, set[str]]]:
    """Every command path `ssc` answers to, with the options it takes and whether it
    dispatches further.

    Read from the Click tree rather than from `--help` text: the tree is what actually
    resolves an invocation, and parsing help output would test the formatter.
    """
    tree: dict[tuple[str, ...], tuple[bool, set[str]]] = {}

    def walk(command: click.Command, path: tuple[str, ...]) -> None:
        options: set[str] = set()
        for param in command.params:
            options.update(param.opts)
            options.update(param.secondary_opts)
        group = isinstance(command, click.Group)
        tree[path] = (group, options)
        if isinstance(command, click.Group):
            for name, sub in command.commands.items():
                walk(sub, (*path, name))

    walk(main, ())
    return tree


def invocations(text: str) -> list[str]:
    """Every backticked token that tells an agent to run something.

    The skills write a command both ways — `ssc index` in a sentence about the CLI,
    `tool bgremove` in a sentence about a stage — so a scan that demanded the binary
    would read four fifths of the run as prose.
    """
    top = {path[0] for path in command_tree() if len(path) == 1}
    found = []
    for token in BACKTICKED.findall(text):
        head = token.split()[0].strip(TRAILING) if token.split() else ""
        if head == "ssc" or head in top:
            found.append(token if head == "ssc" else "ssc " + token)
    return found


def unresolved(token: str, tree: dict[tuple[str, ...], tuple[bool, set[str]]]) -> list[str]:
    """What in this invocation the CLI would not answer to."""
    words = [word.strip(TRAILING) for word in token.split()][1:]
    faults: list[str] = []
    path: tuple[str, ...] = ()

    consuming = True
    for word in words:
        if not word:
            continue
        if word.startswith(STOPS):
            consuming = False
        elif consuming and (*path, word) in tree:
            path = (*path, word)
            continue
        elif consuming and tree[path][0]:
            # The node reached dispatches, so a bare word here is a subcommand it does
            # not have — not an argument, which only a leaf takes.
            faults.append(f"{' '.join(('ssc', *path, word))} is not a command")
            consuming = False
        else:
            consuming = False

        if word.startswith("--"):
            flag = word.split("=")[0]
            if flag not in tree[path][1]:
                faults.append(f"{flag} is not an option of {' '.join(('ssc', *path))}")

    return faults


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_command_a_skill_names_resolves(path: Path) -> None:
    """R3.1, R3.2 — a skill is read before anything has been run, so a command that does
    not exist is not a typo an agent recovers from: it is the first step of the run."""
    tree = command_tree()

    faults = [
        fault
        for token in invocations(path.read_text(encoding="utf-8"))
        for fault in unresolved(token, tree)
    ]

    assert not faults, f"{path.parent.name}: " + "; ".join(sorted(set(faults)))


def test_the_resolution_check_reads_the_invocations_it_thinks_it_reads() -> None:
    """The floor. A scan that stopped matching would report every text clean for good, so
    assert it still finds invocations, still resolves them, and still rejects a fake."""
    tree = command_tree()
    found = [token for path in SKILLS for token in invocations(path.read_text(encoding="utf-8"))]

    assert len(found) > 80, "the skills name fewer commands than any of them did"
    assert ("tool", "doctor") in tree
    assert not unresolved("ssc tool doctor --in frames/", tree)
    assert unresolved("ssc tool nonesuch", tree)
    assert unresolved("ssc tool doctor --nonesuch", tree)
