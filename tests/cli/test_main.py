"""R4.1 · R4.2 · R4.3 — the group translates a Result or an SscError into an exit code."""

from __future__ import annotations

import json

import click
import pytest
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


@click.option("--extra", default="x")
@ssc_command("above")
def above_command(*, dry_run: bool, extra: str) -> Result:
    return Result("above", f"got {extra}")


def test_a_command_may_declare_its_options_either_side_of_the_decorator() -> None:
    """Stated because a comment here once claimed the opposite: click's `_param_memo`
    appends to a built Command's `params` as readily as to a function's
    `__click_params__`, so the convention is readability, not a constraint."""
    result = CliRunner().invoke(above_command, ["--extra", "hello"])
    assert result.exit_code == 0
    assert result.output.strip() == "got hello"


def test_an_unexpected_exception_is_still_one_json_object() -> None:
    """Plan task 0.10, and the reason four reviews found four different tracebacks: R4.1
    says every command emits one JSON object, and that has to hold for the failures nobody
    anticipated too. The one caller this tool is built for cannot parse a traceback."""
    import json

    from click.testing import CliRunner

    from ssc.cli.main import ssc_command

    @ssc_command("boom", help="Raise something nobody planned for.")
    def boom(*, dry_run: bool) -> object:
        raise KeyError("a key nobody checked")

    result = CliRunner().invoke(boom, ["--json"], catch_exceptions=False)
    # stdout, not output: the traceback goes to stderr, so the one JSON object on stdout
    # stays exactly that — which is the half of R4.1 that is easy to lose while fixing the
    # other half.
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["ok"] is False
    assert payload["error"]["code"] == "internal-error"
    assert "KeyError" in payload["error"]["message"]
    # And the diagnosis a person needs is not swallowed either — it is on stderr, where it
    # cannot pollute the object.
    assert "Traceback" in result.stderr
    assert "test_main.py" in result.stderr


def test_a_result_that_cannot_be_rendered_is_still_one_json_object() -> None:
    """The catch-all has to cover the encoder, not stop before it: `json.dumps` raises on a
    set, a Path, a numpy scalar — and three commands build `Result.data` from numpy-backed
    computations already."""
    import json

    from click.testing import CliRunner

    from ssc.cli.main import ssc_command
    from ssc.cli.output import Result

    @ssc_command("unrenderable", help="Return something json cannot encode.")
    def unrenderable(*, dry_run: bool) -> Result:
        return Result("unrenderable", "ok", {"weird": {1, 2, 3}})

    result = CliRunner().invoke(unrenderable, ["--json"], catch_exceptions=False)
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["error"]["code"] == "internal-error"
    assert "cannot be rendered" in payload["error"]["message"]


def test_a_credential_in_an_unexpected_exception_reaches_neither_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan task 0.11. The catch-all puts `str(exception)` in the object, which is right —
    but an HTTP client's message carries the URL, and a URL carries the key. Both channels
    are guarded, because stderr is what a CI log keeps (R4.6)."""
    import json

    from click.testing import CliRunner

    from ssc.cli.main import ssc_command

    monkeypatch.setenv("FAL_KEY", "abcd1234-secret-value")

    @ssc_command("bill", help="Fail the way an HTTP client fails.")
    def bill(*, dry_run: bool) -> object:
        raise RuntimeError("401 for https://fal.run/x?api_key=abcd1234-secret-value")

    result = CliRunner().invoke(bill, ["--json"], catch_exceptions=False)
    payload = json.loads(result.stdout)

    assert result.exit_code == 1
    assert payload["error"]["code"] == "internal-error"
    assert "abcd1234-secret-value" not in result.stdout
    assert "abcd1234-secret-value" not in result.stderr
    assert "401" in payload["error"]["message"]
    assert "Traceback" in result.stderr


def test_a_credential_in_an_ordinary_result_is_redacted_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The path a leaf writes on purpose: `gen --dry-run` reports the call it would make,
    and the call is where the URL is. A guard on the catch-all alone would miss it."""
    import json

    from click.testing import CliRunner

    from ssc.cli.main import ssc_command
    from ssc.cli.output import Result

    monkeypatch.setenv("FAL_KEY", "abcd1234-secret-value")

    @ssc_command("resolved", help="Report the call that would be made.")
    def resolved(*, dry_run: bool) -> Result:
        return Result(
            "resolved", "would call fal", {"url": "https://fal.run/x?key=abcd1234-secret-value"}
        )

    result = CliRunner().invoke(resolved, ["--json"], catch_exceptions=False)
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert "abcd1234-secret-value" not in result.output
    assert payload["url"].endswith("***")
