"""Where the commands are attached to the group.

Separate from `main.py` because the commands import `ssc_command` from there; assembling
in a third module is what keeps that a one-way dependency instead of a cycle.
"""

from __future__ import annotations

from ssc.cli.commands.asset import asset
from ssc.cli.commands.clean import clean
from ssc.cli.commands.convert import bgremove, board, pixelart, snap
from ssc.cli.commands.doctor import doctor
from ssc.cli.commands.init import init
from ssc.cli.commands.media import image, video
from ssc.cli.commands.recover import curate, cut, slice_sheet
from ssc.cli.main import main, tool

main.add_command(init)
main.add_command(asset)
main.add_command(clean)
main.add_command(image)
main.add_command(video)
main.add_command(tool)
tool.add_command(doctor)
tool.add_command(snap)
tool.add_command(pixelart)
tool.add_command(board)
tool.add_command(bgremove)
tool.add_command(cut)
tool.add_command(slice_sheet)
tool.add_command(curate)

__all__ = ["main"]
