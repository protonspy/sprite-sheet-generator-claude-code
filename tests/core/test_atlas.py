"""Packing a set by size — specs/atlas-packing R1, R2.

The two TDD tasks in this leaf assert properties rather than coordinates: an overlap and an
off-by-one extrusion both produce an atlas that looks right in a viewer and samples a
neighbour on a GPU, so a test pinned to the numbers one run produced would encode the bug as
faithfully as the fix.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core import atlas


def sizes(*pairs: tuple[int, int]) -> list[atlas.Entry]:
    return [atlas.Entry(id=f"e{index}", size=pair) for index, pair in enumerate(pairs)]


def overlap(a: atlas.Rect, b: atlas.Rect) -> bool:
    return (
        a.x < b.x + b.width
        and b.x < a.x + a.width
        and a.y < b.y + b.height
        and b.y < a.y + a.height
    )


# R1.1, R1.5 — no two entries share a pixel, nothing leaves the atlas, and the same set
# packs the same way twice.


def test_no_two_entries_overlap() -> None:
    placed = atlas.place(sizes((32, 32), (16, 48), (64, 8), (24, 24), (8, 8), (40, 30)))

    rects = [entry.rect for entry in placed.entries]
    for first in range(len(rects)):
        for second in range(first + 1, len(rects)):
            assert not overlap(rects[first], rects[second]), f"{rects[first]} hits {rects[second]}"


def test_no_entry_leaves_the_atlas() -> None:
    placed = atlas.place(sizes((32, 32), (16, 48), (64, 8), (24, 24)))

    for entry in placed.entries:
        assert entry.rect.x >= 0 and entry.rect.y >= 0
        assert entry.rect.x + entry.rect.width <= placed.width
        assert entry.rect.y + entry.rect.height <= placed.height


def test_every_entry_is_placed_exactly_once() -> None:
    placed = atlas.place(sizes((32, 32), (16, 48), (64, 8)))

    assert sorted(entry.id for entry in placed.entries) == ["e0", "e1", "e2"]


def test_an_entry_keeps_the_size_it_arrived_with() -> None:
    """Nothing here resamples, so a rectangle is the size that went in (R1.1)."""
    given = sizes((32, 7), (16, 48), (5, 5))

    placed = atlas.place(given)

    by_id = {entry.id: entry.rect for entry in placed.entries}
    for entry in given:
        assert (by_id[entry.id].width, by_id[entry.id].height) == entry.size


def test_the_same_set_packs_the_same_way_twice() -> None:
    given = sizes((32, 32), (16, 48), (64, 8), (24, 24))

    first = atlas.place(given)
    second = atlas.place(given)

    assert first.as_dict() == second.as_dict()


def test_the_order_the_entries_arrive_in_does_not_change_the_result() -> None:
    """R1.5 is about the *set*, not about the caller's iteration order — a directory read
    on another filesystem hands them over in another order."""
    given = sizes((32, 32), (16, 48), (64, 8), (24, 24))

    forwards = atlas.place(given)
    backwards = atlas.place(list(reversed(given)))

    assert forwards.as_dict() == backwards.as_dict()


def test_a_taller_entry_is_placed_before_a_shorter_one() -> None:
    """The shelf's whole premise: sorted by height, so a shelf's height is set by its first
    entry and the ones beside it are no taller."""
    placed = atlas.place(sizes((8, 8), (8, 64), (8, 32)))

    order = [entry.id for entry in placed.entries]
    assert order == ["e1", "e2", "e0"]


# R2.1 — the gap holds between every pair, and at the edge.


@pytest.mark.parametrize("padding", [0, 1, 4])
def test_padding_holds_between_every_pair_and_at_the_edge(padding: int) -> None:
    placed = atlas.place(sizes((32, 32), (16, 48), (64, 8), (24, 24), (9, 9)), padding=padding)

    for entry in placed.entries:
        grown = atlas.Rect(
            x=entry.rect.x - padding,
            y=entry.rect.y - padding,
            width=entry.rect.width + 2 * padding,
            height=entry.rect.height + 2 * padding,
        )
        assert grown.x >= 0 and grown.y >= 0
        assert grown.x + grown.width <= placed.width
        assert grown.y + grown.height <= placed.height
        for other in placed.entries:
            if other.id != entry.id:
                assert not overlap(grown, other.rect)


def test_padding_is_measured_between_the_rectangles_not_around_them() -> None:
    """Two entries on one shelf are exactly `padding` apart — the check above would also
    pass if the gap were twice what was asked for, which wastes half the atlas."""
    placed = atlas.place(sizes((16, 16), (16, 16)), width=64, padding=3)

    first, second = sorted(placed.entries, key=lambda entry: entry.rect.x)
    assert second.rect.x - (first.rect.x + first.rect.width) == 3


# R1.6 — an entry that cannot fit is named, not silently dropped or shrunk.


def test_an_entry_wider_than_the_atlas_is_refused_by_name() -> None:
    with pytest.raises(ValueError, match="wide"):
        atlas.place([atlas.Entry(id="banner", size=(200, 8))], width=64)


def test_an_entry_that_does_not_fit_the_padding_is_refused_too() -> None:
    """A 64-wide entry fits a 64-wide atlas until a gap is asked for at the edge."""
    with pytest.raises(ValueError, match="banner"):
        atlas.place([atlas.Entry(id="banner", size=(64, 8))], width=64, padding=2)


# R1.2 — the anchor is per entry and relative to that entry's own rectangle.


def test_the_anchor_is_reported_within_the_entry_not_within_the_atlas() -> None:
    placed = atlas.place(sizes((16, 16), (32, 32)))

    for entry in placed.entries:
        assert 0 <= entry.anchor[0] < entry.rect.width
        assert 0 <= entry.anchor[1] < entry.rect.height


def test_a_measured_anchor_is_carried_through_per_entry() -> None:
    """R1.2 — entries of different sizes cannot share an anchor, which is the same fact that
    makes them an atlas rather than a sheet."""
    placed = atlas.place(sizes((16, 16), (32, 32)), anchors={"e0": (3, 4), "e1": (9, 9)})

    assert {entry.id: entry.anchor for entry in placed.entries} == {"e0": (3, 4), "e1": (9, 9)}


def test_the_anchor_of_an_image_is_measured_the_way_align_measures_one() -> None:
    """Pinned to `align`'s convention rather than to a hand-computed midpoint: the atlas'
    anchors have to agree with the ones `align` and `pack` report, or an engine placing a
    sprite from the index puts it half a pixel off the ground for one kind and not another.
    Opaque columns 2..5 and rows 5..6, and the measured foot is (4, 6)."""
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[5:7, 2:6] = (255, 255, 255, 255)

    found = atlas.anchors_of({"a": image}, "feet")

    assert found["a"] == (4, 6)


# R2.2, R2.3, R2.4 — drawing, and the border repeated outwards.


def solid(width: int, height: int, colour: int) -> np.ndarray:
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    frame[:, :] = (colour, colour, colour, 255)
    return frame


def test_each_entry_lands_at_its_rectangle_unchanged() -> None:
    images = {"a": solid(8, 8, 10), "b": solid(4, 12, 20)}
    placed = atlas.place([atlas.Entry(id="a", size=(8, 8)), atlas.Entry(id="b", size=(4, 12))])

    sheet = atlas.draw(placed, images)

    for entry in placed.entries:
        rect = entry.rect
        cut = sheet[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
        assert np.array_equal(cut, images[entry.id])


def test_the_extruded_pixel_equals_the_border_it_came_from() -> None:
    """Not merely "is not transparent": an extrusion that repeats the wrong row is exactly
    as invisible in a viewer as no extrusion at all, and worse on a GPU."""
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[:, :] = (0, 0, 0, 255)
    image[0, :] = (255, 0, 0, 255)  # top row red
    image[3, :] = (0, 0, 255, 255)  # bottom row blue
    image[:, 0] = (0, 255, 0, 255)  # left column green
    placed = atlas.place([atlas.Entry(id="a", size=(4, 4))], padding=2, extrude=2)

    sheet = atlas.draw(placed, {"a": image})
    rect = placed.entries[0].rect

    for distance in (1, 2):
        above = sheet[rect.y - distance, rect.x : rect.x + rect.width]
        below = sheet[rect.y + rect.height - 1 + distance, rect.x : rect.x + rect.width]
        left = sheet[rect.y : rect.y + rect.height, rect.x - distance]
        assert np.array_equal(above, image[0, :])
        assert np.array_equal(below, image[3, :])
        assert np.array_equal(left, image[:, 0])


def test_the_extruded_corner_repeats_the_corner_pixel() -> None:
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[:, :] = (1, 2, 3, 255)
    image[0, 0] = (9, 9, 9, 255)
    placed = atlas.place([atlas.Entry(id="a", size=(4, 4))], padding=1, extrude=1)

    sheet = atlas.draw(placed, {"a": image})
    rect = placed.entries[0].rect

    assert np.array_equal(sheet[rect.y - 1, rect.x - 1], image[0, 0])


def test_an_extrusion_never_reaches_a_neighbour() -> None:
    """R2.3's reason, asserted rather than argued: with the extrusion at the full width of
    the padding, the pixel next to a neighbour's edge is still that neighbour's."""
    images = {name: solid(8, 8, value) for name, value in (("a", 10), ("b", 200))}
    placed = atlas.place(
        [atlas.Entry(id="a", size=(8, 8)), atlas.Entry(id="b", size=(8, 8))],
        width=32,
        padding=2,
        extrude=2,
    )

    sheet = atlas.draw(placed, images)

    for entry in placed.entries:
        rect = entry.rect
        cut = sheet[rect.y : rect.y + rect.height, rect.x : rect.x + rect.width]
        assert np.array_equal(cut, images[entry.id])


def test_an_extrude_wider_than_the_padding_is_refused() -> None:
    with pytest.raises(ValueError, match="padding"):
        atlas.place(sizes((8, 8)), padding=1, extrude=2)


def test_the_reported_rectangle_excludes_the_extrusion() -> None:
    """R2.4: the rect an engine reads is the art. Drawing the extrusion draws a smear."""
    plain = atlas.place([atlas.Entry(id="a", size=(8, 8))], width=64, padding=4)
    extruded = atlas.place([atlas.Entry(id="a", size=(8, 8))], width=64, padding=4, extrude=4)

    assert plain.entries[0].rect == extruded.entries[0].rect
    assert (extruded.entries[0].rect.width, extruded.entries[0].rect.height) == (8, 8)
