"""`ssc gen boxart` — specs/box-art R1, R2, R3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner
from conftest import FakeClient, load_meta
from test_gen_commands import GROK, NANO

from ssc.cli import kinds
from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.commands import gen as commands

KAEL = (
    "--var",
    "name=Kael",
    "--var",
    "archetype=frost warden",
    "--var",
    "costume=rime-blue plate",
    "--var",
    "prop=a rune-etched axe",
    "--var",
    "setting=a frozen fen under aurora light",
)


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


@pytest.fixture
def space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    (tmp_path / "ssc.yaml").write_text(
        yaml.safe_dump({"schema": 1, "models": {"image": NANO, "video": GROK}}), encoding="utf-8"
    )
    CliRunner().invoke(main, ["asset", "new", "hero", "--kind", "character"])
    return tmp_path


# R1.1, R1.2 — the concept piece, on its own template whatever the asset's kind names.


def test_box_art_is_generated_on_the_box_art_template(space: Path, api: FakeClient) -> None:
    code, payload = run(
        "gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL, "--dry-run"
    )

    assert code == 0, payload
    assert payload["template"] == "box-art"
    assert payload["stage"] == "boxart"
    sent = payload["arguments"]["prompt"]
    assert "Painterly" in sent
    # the one template that must not ask for chroma: box art is never cut out
    assert "chroma" not in sent


def test_box_art_lands_as_a_stage_of_the_asset(space: Path, api: FakeClient, keyed: None) -> None:
    code, payload = run("gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL)

    assert code == 0, payload
    record = load_meta(space / "assets" / "character" / "hero")
    entries = [entry for entry in record.files if entry.stage == "boxart"]
    assert len(entries) == 1
    # `source`, like every generated file: it cost money and no command reproduces it
    assert entries[0].file_class == "source"
    assert entries[0].produced_by.command == "gen boxart"


# R1.3 — the box-art cell, not the asset's.


def test_the_prompt_carries_the_box_art_cell_and_not_the_characters(
    space: Path, api: FakeClient
) -> None:
    """A character's cell is 64x64 and its concept piece is a 1024x1536 portrait. Filling the
    template from the asset's own kind would ask for a portrait the size of a sprite."""
    _, payload = run(
        "gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL, "--dry-run"
    )

    sent = payload["arguments"]["prompt"]
    assert "1024x1536" in sent
    assert "64x64" not in sent


def test_a_project_that_redeclares_the_box_art_kind_moves_the_cell(
    space: Path, api: FakeClient
) -> None:
    """The number comes from the profile rather than from a constant, so redeclaring the kind
    is the one place that changes it."""
    (space / "ssc.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "models": {"image": NANO, "video": GROK},
                "kinds": {"box-art": {"cell": "512x768"}},
            }
        ),
        encoding="utf-8",
    )

    _, payload = run(
        "gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL, "--dry-run"
    )

    assert "512x768" in payload["arguments"]["prompt"]


def test_the_default_size_is_the_box_art_cell(space: Path, api: FakeClient) -> None:
    _, payload = run(
        "gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL, "--dry-run"
    )

    assert payload["size"]["requested"] == "1024x1536"


# R1.4 — concept-art fidelity, and no way to ask for anything else.


def test_box_art_takes_no_style_and_carries_none(space: Path, api: FakeClient) -> None:
    """Not by a check but by there being nothing to pass: the template names no style slot,
    and the command offers no flag. The look of the brief is not the look of the deliverable,
    even when the asset's own style is `pixel-art`."""
    names = {parameter.name for parameter in commands.gen_boxart.params}

    assert "style" not in names
    _, payload = run(
        "gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL, "--dry-run"
    )
    assert payload["style"] is None or payload["style"]["name"] == "pixel-art"
    assert "pixel art" not in payload["arguments"]["prompt"].lower().replace("not pixel art", "")


# R1.5 — what to do with it.


def test_the_result_names_the_command_that_derives_the_sprite(space: Path, api: FakeClient) -> None:
    _, payload = run(
        "gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL, "--dry-run"
    )

    assert "tool pixelart" in payload["derive"]


# R2.1, R2.2 — only where there is nothing to derive from.


def test_there_is_no_reference_to_give(space: Path, api: FakeClient) -> None:
    """A caller holding art has already answered the question box art asks, so the flags that
    would carry it do not exist here."""
    names = {parameter.name for parameter in commands.gen_boxart.params}

    assert names.isdisjoint({"references", "stages", "board"})


def test_a_second_piece_is_refused(space: Path, api: FakeClient, keyed: None) -> None:
    argv = ("gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL)
    code, first = run(*argv)
    assert code == 0, first

    code, second = run(*argv)

    assert code == 2
    assert "boxart" in second["error"]["message"]


# R3.1 — where box art must not go.


def test_box_art_named_as_a_reference_is_refused(space: Path, api: FakeClient, keyed: None) -> None:
    """The trap docs/wiki/box-art-and-style.md describes: the model honours it, and the
    anchor comes back too finely detailed to survive being reduced to a cell."""
    code, made = run("gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL)
    assert code == 0, made

    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the South anchor",
        "--from-stage",
        "boxart",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "box-art-as-reference"
    assert "tool pixelart" in payload["error"]["fix"]


def test_the_refusal_survives_the_stage_being_renamed(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """Against the provenance rather than the stage name: `--stage` renames the stage, and
    the record is what remembers where a file came from."""
    code, made = run(
        "gen",
        "boxart",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        *KAEL,
        "--stage",
        "concept",
    )
    assert code == 0, made

    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the South anchor",
        "--from-stage",
        "concept",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "box-art-as-reference"


def test_box_art_animated_into_frames_is_refused_too(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """A clip is frames, and frames at box art's fidelity are the same unusable frames an
    anchor drawn from it would be — so the refusal is about what comes out, not about which
    command asked."""
    code, made = run("gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL)
    assert code == 0, made

    code, payload = run(
        "gen",
        "video",
        "--asset",
        "character/hero",
        "--prompt",
        "walking",
        "--from-stage",
        "boxart",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "box-art-as-reference"


@pytest.mark.parametrize(
    ("verb", "extra"),
    [("expand", ("--prompt", "more of the fen")), ("bgremove", ())],
)
def test_a_generation_that_turns_box_art_into_box_art_is_allowed(
    space: Path, api: FakeClient, keyed: None, verb: str, extra: tuple[str, ...]
) -> None:
    """Widening the concept piece, and cutting the character out of it for a select screen,
    both produce box art. Refusing them would block real work to prevent nothing."""
    code, made = run("gen", "boxart", "--asset", "character/hero", "--prompt", "a knight", *KAEL)
    assert code == 0, made

    code, payload = run(
        "gen",
        verb,
        "--asset",
        "character/hero",
        "--from-stage",
        "boxart",
        *extra,
        "--dry-run",
    )

    assert code == 0, payload


def test_a_stage_that_is_not_box_art_is_still_a_reference(
    space: Path, api: FakeClient, keyed: None
) -> None:
    code, made = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "the South anchor", "--board"
    )
    assert code == 0, made

    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "turned West",
        "--from-stage",
        "gen:identity",
        "--dry-run",
    )

    assert code == 0, payload
    assert payload["references"][0]["role"] == "identity"


def test_the_box_art_kind_still_takes_its_own_asset(space: Path, api: FakeClient) -> None:
    """A roster piece is a deliverable in its own right, so `box-art` stays a kind an asset
    can be — and generating box art *for* one is the same command."""
    CliRunner().invoke(main, ["asset", "new", "kael", "--kind", "box-art"])

    code, payload = run(
        "gen", "boxart", "--asset", "box-art/kael", "--prompt", "a knight", *KAEL, "--dry-run"
    )

    assert code == 0, payload
    assert kinds.BUILT_INS["box-art"].cell == (1024, 1536)
    assert ws.find(space) is not None
