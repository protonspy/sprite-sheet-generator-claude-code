"""Where the commands are attached to the group.

Separate from `main.py` because the commands import `ssc_command` from there; assembling
in a third module is what keeps that a one-way dependency instead of a cycle.
"""

from __future__ import annotations

from ssc.cli.commands.asset import asset
from ssc.cli.commands.clean import clean
from ssc.cli.commands.init import init
from ssc.cli.main import main

main.add_command(init)
main.add_command(asset)
main.add_command(clean)

__all__ = ["main"]
