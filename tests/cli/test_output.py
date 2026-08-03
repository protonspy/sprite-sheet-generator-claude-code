"""R4.1 — one object per command, rendered as JSON or as prose."""

from __future__ import annotations

import json

from ssc.cli.errors import UsageError
from ssc.cli.output import Result, render


def test_a_result_carries_the_flags_every_command_has() -> None:
    payload = Result(command="init", summary="workspace created").as_dict()
    assert payload["ok"] is True
    assert payload["command"] == "init"
    assert payload["dry_run"] is False
    assert payload["cached"] is False


def test_command_data_is_flattened_into_the_object() -> None:
    """A harness reads `path`, not `data.path` — one object, not one wrapping another."""
    payload = Result("init", "created", data={"path": "/w/ssc.yaml"}).as_dict()
    assert payload["path"] == "/w/ssc.yaml"


def test_json_rendering_is_exactly_one_object() -> None:
    text = render(Result("init", "created").as_dict(), as_json=True)
    assert json.loads(text)["command"] == "init"


def test_prose_rendering_is_the_summary() -> None:
    assert render(Result("init", "workspace created").as_dict(), as_json=False) == (
        "workspace created"
    )


def test_prose_says_when_nothing_was_written() -> None:
    text = render(Result("init", "workspace created", dry_run=True).as_dict(), as_json=False)
    assert text.startswith("[dry run]")


def test_prose_says_when_a_result_was_reused() -> None:
    text = render(Result("snap", "snapped", cached=True).as_dict(), as_json=False)
    assert "cached" in text


def test_an_error_renders_with_its_code_and_fix() -> None:
    text = render(
        UsageError("no-workspace", "no workspace found", fix="ssc init").as_dict(), as_json=False
    )
    assert "no workspace found" in text
    assert "no-workspace" in text
    assert "ssc init" in text
