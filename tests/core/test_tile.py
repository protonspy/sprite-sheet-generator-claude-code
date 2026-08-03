"""Closing a wrap, and measuring one — specs/tile-assets R1, R2.

The measurement is the TDD half. What it asserts is what the ratio *means*: a tile that
already wraps scores about 1, because its boundary is as ordinary an adjacency as any other
in the image, and a hard discontinuity scores far above that whether the tile is noisy or
flat. A test pinned to raw differences instead would have to be rewritten for every input.
"""

from __future__ import annotations

import numpy as np
import pytest

from ssc.core import tile
from ssc.core.doctor.checks import SeamParams, check_seam
from ssc.core.doctor.finding import Check, Status


def gradient(width: int, height: int) -> np.ndarray:
    """A tile whose columns all differ from their neighbours by the same amount, and whose
    last column is nothing like its first — a seam by construction."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    for column in range(width):
        image[:, column, :3] = column * (255 // max(width - 1, 1))
    image[:, :, 3] = 255
    return image


def wrapping(width: int, height: int) -> np.ndarray:
    """A tile that already wraps: every column equals the one before it, edges included."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = 120
    image[:, :, 3] = 255
    return image


def noisy(width: int, height: int, seed: int = 7, block: int = 4) -> np.ndarray:
    """A textured tile, meaning one with spatial correlation — random *blocks*, not random
    pixels.

    The distinction is the check's one real limitation and it belongs in the fixture rather
    than in a threshold. Uniform per-pixel noise is maximally discontinuous everywhere, so
    no boundary in it can be *unusual*, and a ratio against the image's own adjacency
    correctly says so — it just says nothing useful. Every tile this pipeline produces has
    come through `snap` or `pixelart` and is blocky by construction, which is exactly the
    correlated case.
    """
    generator = np.random.default_rng(seed)
    low = generator.integers(0, 256, size=(-(-height // block), -(-width // block), 3))
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = np.repeat(np.repeat(low, block, axis=0), block, axis=1)[:height, :width]
    image[:, :, 3] = 255
    return image


# R2.1 — the ratio, and what it means.


def test_a_tile_that_already_wraps_scores_about_one() -> None:
    finding = check_seam(wrapping(16, 16))

    assert finding.status is Status.OK
    assert finding.measurement["horizontal"] <= 1.5
    assert finding.measurement["vertical"] <= 1.5


def test_a_hard_discontinuity_scores_far_above_its_own_texture() -> None:
    image = noisy(16, 16)
    image[:, -1, :3] = 0  # a black column against random neighbours, on one side only

    finding = check_seam(image)

    assert finding.status is Status.DEFECT
    assert finding.measurement["horizontal"] > 1.5


def test_the_score_is_relative_so_a_noisy_tile_that_wraps_is_still_clean() -> None:
    """The whole reason the check is a ratio: an absolute difference calls every noisy tile
    broken, and every flat tile with a glaring seam clean."""
    image = noisy(32, 32)
    image[:, -1] = image[:, 0]
    image[-1, :] = image[0, :]

    finding = check_seam(image)

    assert finding.status is Status.OK


def test_a_flat_tile_with_one_off_row_is_caught_even_though_the_difference_is_small() -> None:
    image = wrapping(16, 16)
    image[-1, :, :3] = 130  # ten levels away — invisible next to noise, glaring on a floor

    finding = check_seam(image)

    assert finding.status is Status.DEFECT
    assert finding.measurement["vertical"] > finding.measurement["horizontal"]


def test_each_axis_is_measured_on_its_own() -> None:
    """A tile may wrap one way and not the other, and reporting one number would hide it."""
    image = gradient(16, 16)  # columns ramp, rows are identical

    finding = check_seam(image)

    assert finding.measurement["horizontal"] > finding.measurement["vertical"]


def test_the_threshold_is_a_multiple_of_the_image_s_own_adjacency() -> None:
    image = noisy(16, 16)
    image[:, -1, :3] = 0

    strict = check_seam(image, SeamParams(max_ratio=1.2))
    lenient = check_seam(image, SeamParams(max_ratio=1000.0))

    assert strict.status is Status.DEFECT
    assert lenient.status is Status.OK


# R2.2, R2.3 — the fix it names, and the input it will not judge.


def test_a_seam_names_the_command_that_closes_it() -> None:
    image = noisy(16, 16)
    image[:, -1, :3] = 0

    assert "tool tile" in (check_seam(image).fix or "")


@pytest.mark.parametrize("shape", [(1, 8), (8, 1), (1, 1)])
def test_an_image_one_pixel_on_a_side_is_skipped_with_a_reason(shape: tuple[int, int]) -> None:
    image = np.zeros((*shape, 4), dtype=np.uint8)

    finding = check_seam(image)

    assert finding.status is Status.SKIPPED
    assert finding.reason
    assert finding.check is Check.SEAM


# R1.1, R1.3 — closing by copying, and saying what changed.


def test_the_last_column_and_row_become_copies_of_the_first() -> None:
    image = gradient(8, 8)

    closed, report = tile.close(image)

    assert np.array_equal(closed[:, -1], image[:, 0])
    assert np.array_equal(closed[-1, :], closed[0, :])
    assert report["mode"] == "edge"
    assert report["edges"] == ["right", "bottom"]
    # What moved, not what was written to: this gradient's rows are already identical, so
    # only the column write changes anything. Reporting the region's size instead would
    # claim work on every re-run of an already-closed tile.
    assert report["pixels_changed"] == tile.pixels_changed(image, closed)
    assert report["pixels_changed"] == 8


def test_closing_leaves_the_rest_of_the_art_alone() -> None:
    image = gradient(8, 8)

    closed, _ = tile.close(image)

    assert np.array_equal(closed[:-1, :-1], image[:-1, :-1])


def test_closing_a_tile_that_already_wraps_changes_nothing() -> None:
    """`edge` is a real edit when the edges differ, so it has to be idempotent — a tool that
    degrades an asset a little on each re-run is what "nothing mutates its input" exists to
    make impossible."""
    image = wrapping(8, 8)

    once, _ = tile.close(image)
    twice, _ = tile.close(once)

    assert np.array_equal(once, image)
    assert np.array_equal(twice, once)


def test_closing_twice_is_the_same_as_closing_once() -> None:
    image = gradient(8, 8)

    once, _ = tile.close(image)
    twice, _ = tile.close(once)

    assert np.array_equal(twice, once)


def test_a_closed_tile_measures_clean() -> None:
    """The loop the plan describes, in one assertion: the fix satisfies the measurement."""
    image = noisy(16, 16)

    closed, _ = tile.close(image)

    assert check_seam(closed).status is Status.OK


def test_closing_invents_no_colour() -> None:
    image = noisy(16, 16)

    closed, _ = tile.close(image)

    was = {tuple(colour) for colour in image.reshape(-1, 4)}
    now = {tuple(colour) for colour in closed.reshape(-1, 4)}
    assert now <= was


# R1.2 — mirror.


def test_mirror_makes_the_tile_symmetric_about_both_axes() -> None:
    image = noisy(8, 8)

    mirrored, report = tile.close(image, mode="mirror")

    assert np.array_equal(mirrored[:, 4:], mirrored[:, :4][:, ::-1])
    assert np.array_equal(mirrored[4:, :], mirrored[:4, :][::-1, :])
    assert report["mode"] == "mirror"


def test_a_mirrored_tile_measures_clean() -> None:
    mirrored, _ = tile.close(noisy(16, 16), mode="mirror")

    assert check_seam(mirrored).status is Status.OK


def test_mirror_keeps_the_top_left_quarter_as_it_was() -> None:
    image = noisy(8, 8)

    mirrored, _ = tile.close(image, mode="mirror")

    assert np.array_equal(mirrored[:4, :4], image[:4, :4])


def test_mirror_handles_an_odd_side_without_losing_the_middle() -> None:
    image = noisy(9, 9)

    mirrored, _ = tile.close(image, mode="mirror")

    assert mirrored.shape == image.shape
    assert np.array_equal(mirrored[:, 0], mirrored[:, -1])
    assert np.array_equal(mirrored[0, :], mirrored[-1, :])


# R1.4 — the input that has no wrap to close.


@pytest.mark.parametrize("shape", [(1, 8), (8, 1), (1, 1)])
def test_an_image_one_pixel_on_a_side_is_refused(shape: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="two pixels"):
        tile.close(np.zeros((*shape, 4), dtype=np.uint8))


def test_a_closed_tile_reports_nothing_moved_when_it_was_already_closed() -> None:
    once, _ = tile.close(gradient(8, 8))

    _, report = tile.close(once)

    assert report["pixels_changed"] == 0


def test_mirror_reports_what_it_moved_rather_than_a_placeholder() -> None:
    image = noisy(8, 8)

    mirrored_image, report = tile.close(image, mode="mirror")

    assert report["pixels_changed"] == tile.pixels_changed(image, mirrored_image)
    assert report["pixels_changed"] > 0


def test_the_floor_the_caller_passes_is_the_floor_that_is_used() -> None:
    """Read off the class instead of the instance, this field is the same expression to
    look at and silently ignores whatever was tuned — worse than not offering it."""
    image = wrapping(16, 16)
    image[-1, :, :3] = 121  # one level away: real, and tiny against any sensible floor

    tight = check_seam(image, SeamParams(floor=0.01))
    loose = check_seam(image, SeamParams(floor=100.0))

    assert tight.measurement["vertical"] > loose.measurement["vertical"]
