"""Every `fix` a `doctor` finding carries has to be a command that exists.

`Finding.fix` is the whole point of measuring rather than judging: `core/doctor/finding.py`
says the agent "does not decide whether something looks right, it reads a measurement and
runs the command in `fix`". A fix naming an option value the CLI does not accept is worse
than an empty one - the agent runs it, gets exit `2`, and has no second suggestion. That is
what `ssc tool cut --mode bbox` was, against a `--mode` whose choices are chroma and
islands, and it had reached the harness doc by being copied out of the code.

The strings are read from the module rather than from a list here, so a check added later
is covered without anybody remembering to add it. `plans/harness-accuracy.md`, task 3.1.
"""

from __future__ import annotations

import ast
import inspect

import click
import pytest

from ssc.cli.app import main
from ssc.core.doctor import checks


def fix_strings() -> list[str]:
    """Every `fix=` literal in `core/doctor/checks.py`.

    Statically, not by provoking each defect: a check whose defect branch is hard to reach
    from a synthetic frame would silently drop out of this test's coverage, and that is
    exactly the branch nobody looks at.
    """
    tree = ast.parse(inspect.getsource(checks))
    found = {
        keyword.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "fix"
        and isinstance(keyword.value, ast.Constant)
        and isinstance(keyword.value.value, str)
    }
    return sorted(found)


def test_every_check_that_can_report_a_defect_offers_a_fix() -> None:
    """A guard on the reader above: an empty result would make every test below vacuous."""
    assert len(fix_strings()) >= len(list(checks.Check)) - 4


@pytest.mark.parametrize("fix", fix_strings())
def test_the_fix_names_a_command_and_options_the_cli_accepts(fix: str) -> None:
    # A fix may end in a parenthesised aside - "ssc tool pixelart (one palette for the
    # set)" - which is prose about the command rather than part of it.
    tokens = fix.split("(")[0].split()
    assert tokens[0] == "ssc", f"{fix!r} does not start at the CLI"

    command: click.Command = main
    rest = tokens[1:]
    while rest and not rest[0].startswith("-"):
        assert isinstance(command, click.Group), f"{fix!r}: {rest[0]!r} is not a subcommand"
        found = command.get_command(click.Context(command), rest[0])
        assert found is not None, f"{fix!r}: there is no `{rest[0]}` here"
        command = found
        rest.pop(0)
    assert not isinstance(command, click.Group), f"{fix!r} stops at a group, not a command"

    flags = {name: param for param in command.params for name in param.opts}
    index = 0
    while index < len(rest):
        flag = rest[index]
        assert flag.startswith("-"), f"{fix!r}: {flag!r} follows nothing that takes it"
        param = flags.get(flag)
        assert param is not None, f"{fix!r}: {command.name} has no {flag}"
        index += 1
        if index < len(rest) and not rest[index].startswith("-"):
            value = rest[index]
            if isinstance(param.type, click.Choice):
                assert value in param.type.choices, (
                    f"{fix!r}: {flag} takes {', '.join(param.type.choices)}, not {value!r}"
                )
            index += 1
