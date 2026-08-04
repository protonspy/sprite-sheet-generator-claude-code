"""Where the commands are attached to the group.

Separate from `main.py` because the commands import `ssc_command` from there; assembling
in a third module is what keeps that a one-way dependency instead of a cycle.
"""

from __future__ import annotations

from ssc.cli.commands.asset import asset
from ssc.cli.commands.budget import budget
from ssc.cli.commands.clean import clean
from ssc.cli.commands.convert import (
    bgremove,
    board,
    control_states,
    layers,
    ninepatch_guides,
    normal_map,
    pixelart,
    snap,
    tile_wrap,
)
from ssc.cli.commands.doctor import doctor
from ssc.cli.commands.gen import gen_group
from ssc.cli.commands.init import init
from ssc.cli.commands.job import job
from ssc.cli.commands.kind import kind
from ssc.cli.commands.media import image, video
from ssc.cli.commands.model import model
from ssc.cli.commands.recover import (
    align,
    curate,
    cut,
    expand_canvas,
    mirror,
    pack_sheet,
    slice_sheet,
)
from ssc.cli.main import main, tool

main.add_command(init)
main.add_command(asset)
main.add_command(clean)
main.add_command(budget)
main.add_command(kind)
main.add_command(job)
main.add_command(model)
main.add_command(image)
main.add_command(video)
main.add_command(gen_group)
main.add_command(tool)
tool.add_command(doctor)
tool.add_command(snap)
tool.add_command(pixelart)
tool.add_command(board)
tool.add_command(bgremove)
tool.add_command(cut)
tool.add_command(slice_sheet)
tool.add_command(curate)
tool.add_command(expand_canvas)
tool.add_command(mirror)
tool.add_command(align)
tool.add_command(pack_sheet)
tool.add_command(tile_wrap)
tool.add_command(normal_map)
tool.add_command(layers)
tool.add_command(ninepatch_guides)
tool.add_command(control_states)

__all__ = ["main"]
