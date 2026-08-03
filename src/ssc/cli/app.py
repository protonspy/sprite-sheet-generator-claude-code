"""Where the commands are attached to the group.

Separate from `main.py` because the commands import `ssc_command` from there; assembling
in a third module is what keeps that a one-way dependency instead of a cycle.
"""

from __future__ import annotations

from ssc.cli.commands.asset import asset
from ssc.cli.commands.clean import clean
from ssc.cli.commands.doctor import doctor
from ssc.cli.commands.init import init
from ssc.cli.commands.media import image, video
from ssc.cli.main import main, tool

main.add_command(init)
main.add_command(asset)
main.add_command(clean)
main.add_command(image)
main.add_command(video)
main.add_command(tool)
tool.add_command(doctor)

__all__ = ["main"]
