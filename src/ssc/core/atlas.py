"""Packing a set of differently sized images into one texture.

Pure, and split in two on purpose. `place` is arithmetic over sizes and decides where
everything goes; `draw` moves the pixels and decides nothing. The interesting failures —
two entries sharing a pixel, an extrusion reaching into a neighbour — are all in the first
half, which is testable against integers with no images at all.

The counterpart to `assemble.pack`, and the difference is what an entry *is*. A sheet's
cells are equal and a frame is addressed by its index; an atlas' entries are whatever size
they arrived at and are addressed by a rectangle. Trying to serve both from one layout gives
an icon set a cell as large as its largest member and an atlas that is mostly empty.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ssc.core.assemble import Place, check_canvas, common_anchor

#: The gap and the extrusion are both dials on the atlas' size, and both multiply: `padding`
#: applies twice per entry on each axis. A ceiling here keeps a typo from being an
#: allocation — the same argument `MAX_CANVAS` makes about a cell.
MAX_GAP = 64

#: An atlas is not a million entries. The same ceiling `recover.py` puts on a sheet's cells,
#: for a reason of this module's own: `default_width` searches by doubling, and every step of
#: that search sorts and places the whole set. Without a bound here the cost of the *search*
#: scales with however many files a caller can point `--in` at, which is not the caller's
#: intent even when it is not an attack.
MAX_ENTRIES = 4096


class EntryDoesNotFit(ValueError):
    """An entry that no atlas of this width can hold (R1.6).

    Its own type, because `place` raises three different refusals and the fix differs by
    which: a wider atlas answers this one and says nothing useful about a gap.
    """


class GapTooWide(ValueError):
    """A padding or an extrude that is out of range, or an extrude past its padding (R2.3)."""


@dataclass(frozen=True)
class Rect:
    """Where an entry's own pixels are. Not the padding, and not the extrusion (R2.4)."""

    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class Entry:
    """One image to place, by id and size. The pixels arrive later, in `draw`."""

    id: str
    size: tuple[int, int]


@dataclass(frozen=True)
class Placed:
    """One entry, where it went, and its anchor within itself."""

    id: str
    rect: Rect
    anchor: tuple[int, int] = (0, 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rect": self.rect.as_dict(),
            "anchor": {"x": self.anchor[0], "y": self.anchor[1]},
        }


@dataclass(frozen=True)
class Placement:
    """Where everything went, and how big the atlas has to be."""

    width: int
    height: int
    entries: list[Placed]
    padding: int = 0
    extrude: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "padding": self.padding,
            "extrude": self.extrude,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def next_power_of_two(value: int) -> int:
    power = 1
    while power < value:
        power *= 2
    return power


def default_width(entries: list[Entry], padding: int) -> int:
    """The smallest power of two that fits the widest entry and keeps the atlas no taller
    than it is wide.

    A power of two because some engines still want one and it costs nothing to give; roughly
    square because a caller who did not say has no opinion, and a 4096x40 strip is a worse
    answer than a 256x256 for every consumer of it. The height is *not* rounded up — that
    would waste up to half the file to satisfy a constraint nothing in this project has.
    """
    widest = max(entry.size[0] for entry in entries) + 2 * padding
    width = next_power_of_two(max(widest, 1))
    while width < 2**16:
        if shelve(entries, width, padding)[1] <= width:
            return width
        width *= 2
    return width


def in_shelf_order(entries: list[Entry]) -> list[Entry]:
    """By height descending, then by id (R1.5).

    Sorted once by `place` and handed to every `shelve` call, rather than inside `shelve`
    where the doubling search would repeat it at each step.
    """
    return sorted(entries, key=lambda entry: (-entry.size[1], entry.id))


def shelve(entries: list[Entry], width: int, padding: int) -> tuple[list[Placed], int]:
    """Lay the entries out left to right on shelves, and say how tall that got.

    Takes them already in shelf order — height descending, so a shelf's height is set by its
    first entry — because `default_width` calls this repeatedly and the sort does not change
    between those calls.

    The pen starts at `padding` and each entry advances it by its own width *plus* padding —
    one gap between neighbours, not one each. Growing every entry by padding on all four
    sides instead is the obvious model and is wrong by a factor of two between neighbours,
    which wastes most of a densely packed atlas while satisfying every "is there a gap"
    check written to catch its absence.
    """
    placed: list[Placed] = []
    pen_x = pen_y = padding
    shelf_height = 0

    for entry in entries:
        entry_width, entry_height = entry.size
        if padding + entry_width + padding > width:
            raise EntryDoesNotFit(
                f"{entry.id} is {entry_width} wide, too wide for a {width}-wide atlas"
                + (f" with {padding} of padding" if padding else "")
            )
        if pen_x + entry_width + padding > width:
            pen_x = padding
            pen_y += shelf_height + padding
            shelf_height = 0
        placed.append(Placed(id=entry.id, rect=Rect(pen_x, pen_y, entry_width, entry_height)))
        pen_x += entry_width + padding
        shelf_height = max(shelf_height, entry_height)

    return placed, pen_y + shelf_height + padding


def place(
    entries: list[Entry],
    *,
    width: int | None = None,
    padding: int = 0,
    extrude: int = 0,
    anchors: dict[str, tuple[int, int]] | None = None,
) -> Placement:
    """Where every entry goes (R1.1, R1.5, R1.6, R2.1, R2.3).

    `anchors` is what `draw`'s caller measured per image; without it every anchor is the
    centre of the entry, which is what a set nobody aligned actually has.
    """
    if not entries:
        raise ValueError("there are no entries to pack")
    if len(entries) > MAX_ENTRIES:
        # Before the width search, not after: bounding the *result* does not bound the cost
        # of looking for it, and the search is what scales with the set.
        raise EntryDoesNotFit(f"{len(entries)} entries is past the ceiling of {MAX_ENTRIES}")
    if padding < 0 or extrude < 0:
        raise GapTooWide("padding and extrude are distances, so neither can be negative")
    if padding > MAX_GAP or extrude > MAX_GAP:
        raise GapTooWide(f"padding and extrude are capped at {MAX_GAP}")
    if extrude > padding:
        # The whole point of the extrusion is to fill the gap. Wider than the gap, it writes
        # into the neighbour whose sampling it exists to protect (R2.3).
        raise GapTooWide(f"an extrude of {extrude} is wider than the padding of {padding}")
    seen = {entry.id for entry in entries}
    if len(seen) != len(entries):
        raise ValueError("two entries share an id")

    ordered = in_shelf_order(entries)
    chosen = width if width is not None else default_width(ordered, padding)
    if chosen < 1:
        raise EntryDoesNotFit(f"an atlas needs a width of at least 1, got {chosen}")

    placed, height = shelve(ordered, chosen, padding)
    check_canvas(chosen, height, "the atlas")

    measured = anchors or {}
    return Placement(
        width=chosen,
        height=height,
        entries=[
            Placed(
                id=entry.id,
                rect=entry.rect,
                anchor=measured.get(
                    entry.id, (entry.rect.width // 2, max(entry.rect.height - 1, 0))
                ),
            )
            for entry in placed
        ],
        padding=padding,
        extrude=extrude,
    )


def anchors_of(images: dict[str, np.ndarray], mode: Place) -> dict[str, tuple[int, int]]:
    """Each image's own anchor, measured the way `align` and `pack` measure one.

    Per entry rather than one for the set: entries of different sizes cannot share an anchor,
    which is the same fact that makes them an atlas rather than a sheet.
    """
    found: dict[str, tuple[int, int]] = {}
    for name, image in images.items():
        point, _ = common_anchor([image], mode)
        height, width = image.shape[:2]
        found[name] = point or (width // 2, max(height - 1, 0))
    return found


def draw(placement: Placement, images: dict[str, np.ndarray]) -> np.ndarray:
    """The atlas itself (R1.1, R2.2).

    One slice assignment per entry and one per extruded edge — every pixel is copied, none
    is computed, so this cannot reintroduce the blur `snap` removes.
    """
    missing = sorted({entry.id for entry in placement.entries} - set(images))
    if missing:
        raise ValueError(f"no image for {', '.join(missing)}")

    sheet = np.zeros((placement.height, placement.width, 4), dtype=np.uint8)
    for entry in placement.entries:
        image = images[entry.id]
        rect = entry.rect
        if (image.shape[1], image.shape[0]) != (rect.width, rect.height):
            raise ValueError(
                f"{entry.id} was placed as {rect.width}x{rect.height} "
                f"but its image is {image.shape[1]}x{image.shape[0]}"
            )
        sheet[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width] = image
        if placement.extrude:
            extrude_into(sheet, rect, placement.extrude)
    return sheet


def extrude_into(sheet: np.ndarray, rect: Rect, distance: int) -> None:
    """Repeat the entry's border pixels `distance` outwards (R2.2).

    The corners repeat the corner pixel, which is what makes the extruded band continuous:
    an edge-only extrusion leaves four transparent squares at the diagonals, and a GPU
    sampling near a corner reads one of them.
    """
    top, left = rect.y, rect.x
    bottom, right = rect.y + rect.height - 1, rect.x + rect.width - 1

    for step in range(1, distance + 1):
        sheet[top - step, left : right + 1] = sheet[top, left : right + 1]
        sheet[bottom + step, left : right + 1] = sheet[bottom, left : right + 1]
    # Columns after rows, so the sides pick up the rows just written and the corners come out
    # of the same two statements rather than needing four of their own.
    for step in range(1, distance + 1):
        sheet[top - distance : bottom + distance + 1, left - step] = sheet[
            top - distance : bottom + distance + 1, left
        ]
        sheet[top - distance : bottom + distance + 1, right + step] = sheet[
            top - distance : bottom + distance + 1, right
        ]
