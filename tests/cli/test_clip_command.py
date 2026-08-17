"""`ssc tool clip` — specs/clip-sampling R1, R2, R3, R4."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
import yaml
from click.testing import CliRunner
from conftest import load_meta

from ssc.cli import clip as clip_reader
from ssc.cli.app import main
from ssc.cli.clip import MAX_CLIP_FRAMES

SIZE = 32


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def written_clip(path: Path, shades: list[int], fps: float = 10.0) -> Path:
    """A clip of flat frames, one per shade. Written with the codec opencv ships, so the
    test decodes what it encoded rather than what a fixture froze years ago."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (SIZE, SIZE))
    if not writer.isOpened():  # pragma: no cover - a build with no mp4 writer
        pytest.skip("this opencv build cannot write mp4")
    for shade in shades:
        frame = np.full((SIZE, SIZE, 3), shade, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path


def walking(path: Path, cycles: int = 3, cycle: int = 8, fps: float = 10.0) -> Path:
    """A clip whose motion repeats — the shape of a walk a model returns."""
    shades = [20 + (index % cycle) * 25 for index in range(cycles * cycle)]
    return written_clip(path, shades, fps)


# R1.1, R1.2, R4.1 — the clip becomes a frame set.


def test_a_clip_becomes_the_frames_that_were_asked_for(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4")),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "4",
    )

    assert code == 0, payload
    assert payload["frames"] == 4
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == [
        "001.png",
        "002.png",
        "003.png",
        "004.png",
    ]


def test_the_clip_is_reported_as_it_was_found(tmp_path: Path) -> None:
    _, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=2, cycle=8, fps=12.0)),
        "--out",
        str(tmp_path / "out"),
    )

    assert payload["clip"]["frames"] == 16
    assert payload["clip"]["fps"] == pytest.approx(12.0, abs=0.01)


# R2.1 — the cycle.


def test_the_frames_come_from_one_cycle_and_not_the_whole_clip(tmp_path: Path) -> None:
    """Three cycles in, one cycle out: a sheet wants one repetition of the motion."""
    _, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=3, cycle=8)),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "8",
    )

    assert payload["cycle"] == 8
    assert payload["sampled"] == [0, 1, 2, 3, 4, 5, 6, 7]


def test_the_closing_frame_is_not_taken(tmp_path: Path) -> None:
    """It is the opening frame again, and a sheet holding both stutters at the loop point."""
    _, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=3, cycle=8)),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "4",
    )

    assert payload["cycle"] not in payload["sampled"]
    assert payload["sampled"] == [0, 2, 4, 6]


# R2.3, R2.4 — no cycle, and not looking for one.


def test_a_clip_that_never_returns_says_so_and_gives_the_whole_thing(tmp_path: Path) -> None:
    drifting = written_clip(tmp_path / "death.mp4", [10 + index * 12 for index in range(20)])

    _, payload = run(
        "tool", "clip", "--in", str(drifting), "--out", str(tmp_path / "out"), "--frames", "4"
    )

    assert payload["cycle"] is None
    assert payload["sampled"] == [0, 5, 10, 15]
    assert "no cycle" in payload["summary"]


def test_the_whole_clip_is_sampled_where_that_is_what_was_asked(tmp_path: Path) -> None:
    _, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=3, cycle=8)),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "4",
        "--whole",
    )

    assert payload["cycle"] is None
    assert payload["sampled"] == [0, 6, 12, 18]


# R3.3, R3.4 — a range in seconds, and asking for too much.


def test_a_range_in_seconds_is_read_at_the_clips_own_rate(tmp_path: Path) -> None:
    """Seconds because that is what somebody who watched the clip has; the frame rate comes
    from the container rather than being assumed."""
    _, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=3, cycle=8, fps=10.0)),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "2",
        "--from",
        "0.8",
        "--to",
        "1.6",
        "--whole",
    )

    assert payload["range"] == {"first": 8, "last": 16}
    assert payload["sampled"] == [0, 4]


def test_a_range_outside_the_clip_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=1, cycle=8)),
        "--out",
        str(tmp_path / "out"),
        "--from",
        "5.0",
        "--to",
        "9.0",
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-range"


def test_more_frames_than_the_range_holds_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4", cycles=3, cycle=8)),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "40",
    )

    assert code == 2
    assert payload["error"]["code"] == "too-many-frames"
    assert not (tmp_path / "out").exists()


# R1.3 — what is not a clip.


def test_a_file_that_is_not_a_clip_is_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not a clip", encoding="utf-8")

    code, payload = run(
        "tool", "clip", "--in", str(tmp_path / "notes.txt"), "--out", str(tmp_path / "out")
    )

    assert code == 2
    assert payload["error"]["code"] == "unreadable-clip"
    assert "notes.txt" in payload["error"]["message"]


def test_a_file_that_is_not_there_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "clip", "--in", str(tmp_path / "gone.mp4"), "--out", str(tmp_path / "out")
    )

    assert code == 2
    assert payload["error"]["code"] == "no-input"


def test_the_ceiling_is_several_times_a_generated_clip() -> None:
    """Four seconds at 30fps is 120 frames, and the sources generate 80 to 120."""
    assert MAX_CLIP_FRAMES >= 300


# R1.4, R1.5 — what will not be decoded.


def test_a_clip_past_the_frame_ceiling_is_refused_before_it_is_decoded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(clip_reader, "MAX_CLIP_FRAMES", 4)
    long_clip = written_clip(tmp_path / "long.mp4", [10 + index for index in range(12)])

    code, payload = run("tool", "clip", "--in", str(long_clip), "--out", str(tmp_path / "out"))

    assert code == 2
    assert payload["error"]["code"] == "clip-too-long"
    assert not (tmp_path / "out").exists()


class Lying:
    """A container that reports nothing about itself — which some really do, and which is
    what makes the in-loop ceiling the one that has to hold."""

    def __init__(self, frames: int, size: int = SIZE) -> None:
        self.left = frames
        self.size = size
        self.released = False

    def isOpened(self) -> bool:  # cv2's own spelling
        return True

    def get(self, prop: int) -> float:
        return 0.0

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.left <= 0:
            return False, None
        self.left -= 1
        return True, np.zeros((self.size, self.size, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True


def test_a_container_that_declares_nothing_is_still_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lying = Lying(frames=50)
    monkeypatch.setattr(clip_reader, "MAX_CLIP_FRAMES", 4)
    monkeypatch.setattr(clip_reader.cv2, "VideoCapture", lambda _: lying)
    (tmp_path / "walk.mp4").write_bytes(b"not really a clip")

    code, payload = run(
        "tool", "clip", "--in", str(tmp_path / "walk.mp4"), "--out", str(tmp_path / "out")
    )

    assert code == 2
    assert payload["error"]["code"] == "clip-too-long"
    assert lying.released


def test_a_frame_larger_than_will_be_held_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The video shape of the decompression bomb `frames.MAX_PIXELS` exists for: the header
    is the attacker's to write, so the frame in hand is checked too."""
    monkeypatch.setattr(clip_reader, "MAX_PIXELS", 100)
    monkeypatch.setattr(clip_reader.cv2, "VideoCapture", lambda _: Lying(frames=2, size=64))
    (tmp_path / "bomb.mp4").write_bytes(b"not really a clip")

    code, payload = run(
        "tool", "clip", "--in", str(tmp_path / "bomb.mp4"), "--out", str(tmp_path / "out")
    )

    assert code == 2
    assert payload["error"]["code"] == "clip-too-large"


def test_a_header_field_that_is_not_a_number_is_read_as_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`nan` is truthy, survives every `<=` comparison, and raises inside `int()`. A
    container's metadata is not this project's to trust — the same trap `check_wait` closes
    for a flag."""
    lying = Lying(frames=4)
    monkeypatch.setattr(lying, "get", lambda prop: float("nan"))
    monkeypatch.setattr(clip_reader.cv2, "VideoCapture", lambda _: lying)
    (tmp_path / "odd.mp4").write_bytes(b"not really a clip")

    code, payload = run(
        "tool",
        "clip",
        "--in",
        str(tmp_path / "odd.mp4"),
        "--out",
        str(tmp_path / "out"),
        "--frames",
        "2",
    )

    assert code == 0, payload
    assert payload["clip"]["fps"] == 0.0
    assert payload["frames"] == 2


# R3.5 — a range that is not a number of seconds.


@pytest.mark.parametrize("given", ["nan", "inf", "-inf"])
def test_a_range_that_is_not_a_number_is_refused(tmp_path: Path, given: str) -> None:
    code, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4")),
        "--out",
        str(tmp_path / "out"),
        "--from",
        given,
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-range"


# R4.1, R4.2 — into the asset.


def test_neither_destination_or_both_is_refused(tmp_path: Path) -> None:
    code, payload = run("tool", "clip", "--in", str(walking(tmp_path / "walk.mp4")))

    assert code == 2
    assert payload["error"]["code"] == "no-destination"


def test_the_frames_land_as_one_recorded_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = walking(tmp_path / "walk.mp4", cycles=3, cycle=8)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    CliRunner().invoke(main, ["asset", "new", "hero", "--kind", "character"])

    code, payload = run(
        "tool", "clip", "--in", str(clip), "--asset", "character/hero", "--frames", "4"
    )

    assert code == 0, payload
    record = load_meta(tmp_path / "assets/character/hero")
    entries = [entry for entry in record.files if entry.stage == "clip"]
    assert len(entries) == 1
    assert entries[0].produced_by.command == "tool clip"
    # what was sampled, so the set is reproducible from the record alone
    assert entries[0].produced_by.params["cycle"] == 8
    assert payload["written"] == [f"frames/clip/{index:03d}.png" for index in range(1, 5)]


def test_a_dry_run_writes_nothing(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "clip",
        "--in",
        str(walking(tmp_path / "walk.mp4")),
        "--out",
        str(tmp_path / "out"),
        "--dry-run",
    )

    assert code == 0, payload
    assert payload["written"]
    assert not (tmp_path / "out").exists()


def test_the_sidecar_is_left_alone_where_there_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = walking(tmp_path / "walk.mp4")
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    CliRunner().invoke(main, ["asset", "new", "hero", "--kind", "character"])

    _, payload = run("tool", "clip", "--in", str(clip), "--asset", "character/hero")

    assert payload["sidecar"] is None
    assert not yaml.safe_load((tmp_path / "ssc.yaml").read_text(encoding="utf-8")).get("frames")
