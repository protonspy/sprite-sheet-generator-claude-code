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

import pytest

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
