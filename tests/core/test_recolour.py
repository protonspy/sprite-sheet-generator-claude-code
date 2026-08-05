"""`recolour_frames` — map one palette onto another, position by position (task 5.3).

The assertion comes from the requirement: a red slime becomes a blue slime through a
colour map, not a second generation. Position 0 of `from` maps to position 0 of `to`,
which is what makes the map a deliberate act rather than a nearest-colour guess.
"""

from __future__ import annotations

import numpy as np

from ssc.core.recolour import recolour_frames


def frame(colours: list[tuple[int, int, int]]) -> np.ndarray:
    """A 4x4 RGBA frame split into horizontal bands of `colours`, fully opaque."""
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    rows = len(colours)
    for index, colour in enumerate(colours):
        start = index * 4 // rows
        end = (index + 1) * 4 // rows
        image[start:end, :, :3] = colour
    image[..., 3] = 255
    return image


def test_red_maps_to_blue_position_by_position() -> None:
    """The whole point: a red slime becomes a blue slime."""
    src = np.array([(255, 0, 0), (0, 200, 0)], dtype=np.uint8)
    dst = np.array([(0, 0, 255), (200, 200, 0)], dtype=np.uint8)
    outcome = recolour_frames([frame([(255, 0, 0), (0, 200, 0)])], src, dst)

    rgb = outcome.frames[0][..., :3]
    assert np.all(rgb[:2] == (0, 0, 255))  # red band → blue
    assert np.all(rgb[2:] == (200, 200, 0))  # green band → yellow


def test_alpha_is_left_untouched() -> None:
    src = np.array([(255, 0, 0)], dtype=np.uint8)
    dst = np.array([(0, 0, 255)], dtype=np.uint8)
    image = frame([(255, 0, 0)])
    image[..., 3] = 128
    outcome = recolour_frames([image], src, dst)
    assert set(int(v) for v in outcome.frames[0][..., 3].flatten()) == {128}


def test_the_measurement_records_both_palettes() -> None:
    src = np.array([(255, 0, 0), (0, 0, 0)], dtype=np.uint8)
    dst = np.array([(0, 0, 255), (255, 255, 255)], dtype=np.uint8)
    outcome = recolour_frames([frame([(255, 0, 0), (0, 0, 0)])], src, dst)
    assert outcome.measurement["from"] == ["ff0000", "000000"]
    assert outcome.measurement["to"] == ["0000ff", "ffffff"]
