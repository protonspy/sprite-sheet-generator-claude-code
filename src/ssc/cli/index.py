"""The index model — what an engine is told about a workspace.

`ssc index` reads `assets/`, packs what each kind's profile says it packs, and writes
`dist/`. This module is the model that sits between those two: it knows about assets, kinds
and sidecars, and nothing about any particular engine. `cli/formats.py` renames its fields
for Pixi, Phaser and Godot without reading a workspace or an image.
"""

from __future__ import annotations

from ssc.cli.errors import SscError
from ssc.cli.sidecar import Section


def resolve_sections(
    sections: tuple[Section, ...], *, frames: int, where: str
) -> tuple[Section, ...]:
    """The authored sections, checked against the set that actually exists (R2.4, R2.5).

    Both ends are inclusive, so the last frame of an eight-frame set is 7. That is the whole
    of this function and it is why it is worth one: an engine handed `[3, 8]` over eight
    frames does not complain, it plays a frame that is not there or stops one short, and
    nobody notices until they watch it.

    The refusal names the first section that is wrong rather than collecting them all: the
    author fixes one line, reruns, and the next is found. Listing every fault of a file
    somebody is halfway through writing is noise.
    """
    for section in sections:
        if frames < 1 or section.first >= frames or section.last >= frames:
            raise SscError(
                "section-out-of-range",
                f"{where}: section {section.name!r} covers frames "
                f"{section.first} to {section.last}, and the set has {frames}",
                fix=f"the last frame of this set is {frames - 1}"
                if frames
                else "this set has no frames to divide into sections",
            )
    return sections
