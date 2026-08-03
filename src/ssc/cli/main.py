"""The click group, and the one place a `Result` or an `SscError` becomes an exit code."""

from __future__ import annotations

import functools
import traceback
from collections.abc import Callable
from typing import Any

import click

from ssc.cli import workspace
from ssc.cli.errors import EXIT_ERROR, EXIT_OK, SscError
from ssc.cli.output import Result, render


def ssc_command(
    name: str, help: str | None = None, *, needs_workspace: bool = False
) -> Callable[[Callable[..., Result]], click.Command]:
    """Turn a function returning a `Result` into a command.

    Every command gets `--json` and `--dry-run` here rather than declaring them (R4.1,
    R4.3), and no command decides its own exit code (R4.2) or writes to stdout itself.

    `needs_workspace` is how a command declares the dependency instead of remembering to
    look one up: with it, the located `Workspace` arrives as a keyword argument and the
    refusal for a missing one is identical everywhere (R1.5). Commands that work off
    `--in`/`--out` leave it alone (R1.6).

    A command's own `@click.option` and `@click.argument` go **below** this decorator by
    convention, so the whole signature reads in one place. Either order works — click's
    `_param_memo` appends to a `Command`'s `params` and to a plain function's
    `__click_params__` alike — so this is readability, not a constraint.
    """

    def decorate(fn: Callable[..., Result]) -> click.Command:
        @click.option("--json", "as_json", is_flag=True, help="Emit one JSON object on stdout.")
        @click.option(
            "--dry-run", is_flag=True, help="Write nothing, and report what would be written."
        )
        @functools.wraps(fn)
        def inner(*args: Any, as_json: bool, dry_run: bool, **kwargs: Any) -> None:
            try:
                if needs_workspace:
                    kwargs["workspace"] = workspace.require()
                payload = fn(*args, dry_run=dry_run, **kwargs).as_dict()
                code = EXIT_OK
            except SscError as error:
                payload = error.as_dict()
                code = error.exit_code
            except Exception as unexpected:
                # The diagnosis a person needs goes to stderr, where it cannot pollute the
                # one object on stdout. Discarding it was the wrong half of the trade: the
                # machine gains a parseable envelope and the developer loses the file and
                # the line, which is exactly what four review rounds of this leaf needed.
                click.echo(traceback.format_exc(), err=True)
                # Every command emits one JSON object (R4.1), and that has to hold for the
                # failures nobody anticipated too — otherwise the one caller this tool is
                # built for gets a traceback on stderr and nothing it can parse. Four
                # separate reviews found four different ways to reach this, each a distinct
                # exception type; the fifth would have been found by a user.
                #
                # The diagnosis is not swallowed: the type and the message are in the
                # object, which is more than a traceback gives a program and enough for a
                # person to act on.
                payload = SscError(
                    "internal-error",
                    f"{type(unexpected).__name__}: {unexpected}",
                    fix="this is a bug in ssc; the code and message above are what to report",
                ).as_dict()
                code = EXIT_ERROR

            # Rendering is inside the guard too, because it is where the JSON is actually
            # produced: `json.dumps` raises on a `set`, a `Path`, a numpy scalar, and
            # `Result.data` is built from numpy-backed computations in three commands
            # already. A catch-all that stops before the encoder does not cover R4.1.
            try:
                text = render(payload, as_json=as_json)
            except Exception as unrenderable:
                click.echo(traceback.format_exc(), err=True)
                payload = SscError(
                    "internal-error",
                    f"this command built a result that cannot be rendered: {unrenderable}",
                    fix="this is a bug in ssc; the code and message above are what to report",
                ).as_dict()
                code = EXIT_ERROR
                # Plain strings, so this one cannot fail the same way.
                text = render(payload, as_json=as_json)

            # With --json, stdout carries the object and nothing else — including when the
            # object describes a failure. Without it, an error belongs on stderr.
            click.echo(text, err=not as_json and not payload["ok"])
            raise SystemExit(code)

        return click.command(name=name, help=help)(inner)

    return decorate


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="sprite-sheet-generator-claude-code")
def main() -> None:
    """Turn AI-generated art into game-ready 2D assets.

    `tool` commands are local, free and synchronous. `gen` commands bill.
    """


@click.group("tool", help="Local, free and synchronous. Nothing under `tool` bills.")
def tool() -> None:
    """The verb carries the guarantee: `tool` is free, `gen` charges. An agent scanning
    the command list can tell which calls burn credit without inspecting a flag."""
