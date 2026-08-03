"""The click group, and the one place a `Result` or an `SscError` becomes an exit code."""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import click

from ssc.cli import workspace
from ssc.cli.errors import EXIT_OK, SscError
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

            # With --json, stdout carries the object and nothing else — including when the
            # object describes a failure. Without it, an error belongs on stderr.
            click.echo(render(payload, as_json=as_json), err=not as_json and not payload["ok"])
            raise SystemExit(code)

        return click.command(name=name, help=help)(inner)

    return decorate


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="sprite-sheet-generator-claude-code")
def main() -> None:
    """Turn AI-generated art into game-ready 2D assets.

    `tool` commands are local, free and synchronous. `gen` commands bill.
    """
