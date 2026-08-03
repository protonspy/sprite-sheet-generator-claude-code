"""Reading `--in` and writing `--out` — specs/pixel-art-conversion R1."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ssc.cli import frames
from ssc.cli.errors import SscError


def write_png(path: Path, colour: tuple[int, int, int] = (255, 0, 0)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[..., :3] = colour
    pixels[..., 3] = 255
    Image.fromarray(pixels, mode="RGBA").save(path)
    return path


def a_frame(name: str, colour: tuple[int, int, int] = (0, 255, 0)) -> frames.Frame:
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[..., :3] = colour
    pixels[..., 3] = 255
    return frames.Frame(name, pixels)


# R1.2 — one image, or a directory read in filename order.


def test_a_file_reads_as_one_frame_keeping_its_name(tmp_path: Path) -> None:
    read = frames.read_frames(write_png(tmp_path / "hero.png"))
    assert [frame.name for frame in read] == ["hero.png"]
    assert read[0].image.shape == (4, 4, 4)


def test_a_directory_reads_in_filename_order(tmp_path: Path) -> None:
    for name in ("003_c.png", "001_a.png", "002_b.png"):
        write_png(tmp_path / "set" / name)
    read = frames.read_frames(tmp_path / "set")
    assert [frame.name for frame in read] == ["001_a.png", "002_b.png", "003_c.png"]


def test_a_directory_ignores_what_is_not_an_image(tmp_path: Path) -> None:
    write_png(tmp_path / "set" / "001_a.png")
    (tmp_path / "set" / "notes.txt").write_text("not a frame")
    assert [frame.name for frame in frames.read_frames(tmp_path / "set")] == ["001_a.png"]


def test_a_directory_of_no_images_is_refused(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(SscError) as refused:
        frames.read_frames(tmp_path / "empty")
    assert refused.value.code == "no-images"


def test_a_path_that_is_neither_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SscError) as refused:
        frames.read_frames(tmp_path / "nothing-here")
    assert refused.value.code == "no-input"


def test_an_image_over_the_ceiling_is_refused_before_it_is_decoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_png(tmp_path / "hero.png")
    monkeypatch.setattr(frames, "MAX_PIXELS", 4)
    with pytest.raises(SscError) as refused:
        frames.read_frames(path)
    assert refused.value.code == "image-too-large"


def test_something_that_is_not_an_image_is_an_error_not_a_traceback(tmp_path: Path) -> None:
    path = tmp_path / "hero.png"
    path.write_bytes(b"definitely not a PNG")
    with pytest.raises(SscError) as refused:
        frames.read_frames(path)
    assert refused.value.code == "unreadable-image"


# R1.3 — one file in, one file out; a set in, a set out under the same names.


def test_one_image_writes_one_file_at_the_given_path(tmp_path: Path) -> None:
    source = write_png(tmp_path / "hero.png")
    written = frames.write_frames(source, tmp_path / "out.png", [a_frame("hero.png")])
    assert written == [tmp_path / "out.png"]
    assert Image.open(tmp_path / "out.png").size == (4, 4)


def test_a_set_writes_one_file_per_frame_under_its_own_name(tmp_path: Path) -> None:
    source = tmp_path / "set"
    write_png(source / "001_a.png")
    write_png(source / "002_b.png")
    written = frames.write_frames(
        source, tmp_path / "out", [a_frame("001_a.png"), a_frame("002_b.png")]
    )
    assert [path.name for path in written] == ["001_a.png", "002_b.png"]
    assert all(path.is_file() for path in written)


def test_a_single_frame_written_into_a_directory_keeps_its_name(tmp_path: Path) -> None:
    """`--out` naming a directory rather than a file is the shape a caller reaches for
    when converting one frame of a set into a set that already exists."""
    source = write_png(tmp_path / "hero.png")
    written = frames.write_frames(source, tmp_path / "out", [a_frame("hero.png")])
    assert written == [tmp_path / "out" / "hero.png"]


# R1.4 — an existing output stops the whole command, not just its own frame.


def test_an_existing_output_is_refused(tmp_path: Path) -> None:
    source = write_png(tmp_path / "hero.png")
    write_png(tmp_path / "out.png")
    with pytest.raises(SscError) as refused:
        frames.write_frames(source, tmp_path / "out.png", [a_frame("hero.png")])
    assert refused.value.code == "file-exists"


def test_one_existing_target_writes_none_of_the_set(tmp_path: Path) -> None:
    """The whole reason the targets are checked before the first is written: a set that
    half-landed cannot be rerun, because the frames that landed now refuse it too."""
    source = tmp_path / "set"
    write_png(source / "001_a.png")
    write_png(source / "002_b.png")
    write_png(tmp_path / "out" / "002_b.png")

    with pytest.raises(SscError) as refused:
        frames.write_frames(source, tmp_path / "out", [a_frame("001_a.png"), a_frame("002_b.png")])
    assert refused.value.code == "file-exists"
    assert not (tmp_path / "out" / "001_a.png").exists()


def test_dry_run_reports_the_targets_and_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "set"
    write_png(source / "001_a.png")
    written = frames.write_frames(source, tmp_path / "out", [a_frame("001_a.png")], dry_run=True)
    assert written == [tmp_path / "out" / "001_a.png"]
    assert not (tmp_path / "out").exists()


def test_what_is_written_round_trips(tmp_path: Path) -> None:
    source = write_png(tmp_path / "hero.png")
    frames.write_frames(source, tmp_path / "out.png", [a_frame("hero.png", (1, 2, 3))])
    written = frames.read_frames(tmp_path / "out.png")[0].image
    assert tuple(written[0, 0]) == (1, 2, 3, 255)
