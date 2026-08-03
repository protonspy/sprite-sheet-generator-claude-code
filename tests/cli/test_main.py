"""R4.1 · R4.2 · R4.3 — the group translates a Result or an SscError into an exit code."""

from __future__ import annotations

import json

from click.testing import CliRunner

from ssc.cli.errors import GatePending, SscError, UsageError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@ssc_command("ok")
def ok_command(*, dry_run: bool) -> Result:
    return Result("ok", "it worked", data={"n": 1}, dry_run=dry_run)


@ssc_command("boom")
def boom_command(*, dry_run: bool) -> Result:
    raise SscError("boom", "it broke", fix="ssc init")


@ssc_command("misuse")
def misuse_command(*, dry_run: bool) -> Result:
    raise UsageError("misuse", "called wrong")


@ssc_command("pending")
def pending_command(*, dry_run: bool) -> Result:
    raise GatePending("pending", "a gate is open")


def test_success_exits_zero_and_prints_the_summary() -> None:
    result = CliRunner().invoke(ok_command, [])
    assert result.exit_code == 0
    assert result.output.strip() == "it worked"


def test_json_output_is_one_object_and_nothing_else() -> None:
    result = CliRunner().invoke(ok_command, ["--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "ok": True,
        "command": "ok",
        "summary": "it worked",
        "dry_run": False,
        "cached": False,
        "n": 1,
    }


def test_dry_run_reaches_the_command_and_the_object() -> None:
    result = CliRunner().invoke(ok_command, ["--dry-run", "--json"])
    assert json.loads(result.output)["dry_run"] is True


def test_each_error_maps_to_its_exit_code() -> None:
    assert CliRunner().invoke(boom_command, []).exit_code == 1
    assert CliRunner().invoke(misuse_command, []).exit_code == 2
    assert CliRunner().invoke(pending_command, []).exit_code == 3


def test_a_failure_under_json_is_still_one_object_on_stdout() -> None:
    """A harness parses stdout unconditionally; splitting the failure onto stderr would
    make --json mean two different things depending on the outcome."""
    runner = CliRunner()
    result = runner.invoke(boom_command, ["--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["fix"] == "ssc init"


def test_a_failure_without_json_goes_to_stderr() -> None:
    result = CliRunner().invoke(boom_command, [])
    assert result.exit_code == 1
    assert "it broke" in result.stderr
    assert result.stdout == ""


def test_bad_arguments_are_invalid_usage() -> None:
    """click's own parse failures already exit 2, which is the code R4.2 gives them."""
    assert CliRunner().invoke(ok_command, ["--nope"]).exit_code == 2
