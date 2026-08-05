"""`asset.yaml`, the authored half of an asset — specs/engine-index R4.1, R4.3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from conftest import save_meta

from ssc.cli import meta, sidecar
from ssc.cli.app import main
from ssc.cli.atomic import Directory
from ssc.cli.errors import SscError, UsageError

WHERE = "assets/character/hero/asset.yaml"


def parse(text: str) -> sidecar.Sidecar:
    return sidecar.parse(text.encode("utf-8"), WHERE)


def playback(text: str) -> sidecar.Playback:
    return parse(text).playback


def refusal(text: str) -> SscError:
    with pytest.raises(SscError) as raised:
        parse(text)
    assert raised.value.code == "invalid-sidecar"
    # R4.3 — the file is named in every refusal, because an author with three assets open
    # needs to know which one is wrong before they need to know what is wrong with it.
    assert WHERE in raised.value.message
    return raised.value


# R4.1 — what a well-formed sidecar says.


def test_a_full_playback_is_read() -> None:
    read = playback(
        """
        playback:
          fps: 12
          mode: ping-pong
          sections:
            windup: [0, 2]
            hit: [3, 4]
        """
    )
    assert read.fps == 12
    assert read.mode == "ping-pong"
    assert [(section.name, section.first, section.last) for section in read.sections] == [
        ("hit", 3, 4),
        ("windup", 0, 2),
    ]


def test_an_empty_file_declares_nothing() -> None:
    # `fps: None` rather than a default, so R4.2's fallback can tell "the author said 12"
    # from "the author said nothing".
    read = parse("")
    assert read.playback.fps is None
    assert read.playback.mode == sidecar.DEFAULT_MODE
    assert read.playback.sections == ()
    assert read.frames is None


def test_sections_are_sorted_by_name() -> None:
    # R1.8 — a byte-identical second run means the order cannot come from the author's
    # keystrokes.
    read = playback("playback:\n  sections:\n    z: [1, 2]\n    a: [0, 0]\n")
    assert [section.name for section in read.sections] == ["a", "z"]


def test_a_section_as_a_dict() -> None:
    assert sidecar.Section("windup", 0, 2).as_dict() == {
        "name": "windup",
        "first": 0,
        "last": 2,
    }


# R4.3 — every way a sidecar can be wrong, and the key each refusal names.


def test_a_document_that_is_not_a_map() -> None:
    assert "not a map" in refusal("- windup\n- hit\n").message


def test_broken_yaml() -> None:
    assert "not valid YAML" in refusal("playback: [1, 2\n").message


def test_an_anchor_is_refused_like_ssc_yaml() -> None:
    # The sidecar reuses `config.StrictLoader`, so the alias bomb that cannot reach
    # `ssc.yaml` cannot reach this file either.
    assert "not valid YAML" in refusal("a: &x [1]\nplayback: *x\n").message


def test_an_unknown_top_level_key() -> None:
    # Refused rather than ignored: a key ssc silently drops is a value the author
    # believes is in effect.
    assert "physics" in refusal("physics: []\n").message


def test_playback_that_is_not_a_map() -> None:
    assert "playback is a str" in refusal("playback: fast\n").message


def test_an_unknown_playback_key() -> None:
    assert "playback declares speed" in refusal("playback:\n  speed: 12\n").message


@pytest.mark.parametrize("given", ["twelve", "12.5", "true"])
def test_a_frame_rate_that_is_not_a_whole_number(given: str) -> None:
    assert "playback.fps" in refusal(f"playback:\n  fps: {given}\n").message


@pytest.mark.parametrize("given", [0, -1, sidecar.MAX_FPS + 1])
def test_a_frame_rate_out_of_range(given: int) -> None:
    assert "outside 1 to" in refusal(f"playback:\n  fps: {given}\n").message


def test_a_mode_that_is_not_one_of_the_three() -> None:
    refused = refusal("playback:\n  mode: bounce\n")
    assert "playback.mode is 'bounce'" in refused.message
    assert refused.fix is not None and "ping-pong" in refused.fix


def test_sections_that_are_not_a_map() -> None:
    assert "playback.sections is a list" in refusal("playback:\n  sections: [a, b]\n").message


@pytest.mark.parametrize("span", ["3", "[1, 2, 3]", "[1, two]", "[true, false]"])
def test_a_section_that_is_not_a_pair_of_frame_numbers(span: str) -> None:
    assert (
        "not a pair of frame numbers"
        in refusal(f"playback:\n  sections:\n    windup: {span}\n").message
    )


@pytest.mark.parametrize("span", ["[-1, 2]", "[4, 3]"])
def test_a_section_that_runs_backwards_or_before_the_start(span: str) -> None:
    assert "windup runs from" in refusal(f"playback:\n  sections:\n    windup: {span}\n").message


# The frames block — hitboxes, hurtboxes and markers, one entry per frame
# (plans/ssc-completion.md 3.1).


def test_a_full_frames_block_is_read() -> None:
    read = parse(
        """
        frames:
          - hitboxes:
              - [18, 8, 12, 10]
            hurtboxes:
              - [12, 4, 20, 24]
            markers: [footstep]
          - ~
        """
    )
    assert read.frames is not None
    first, second = read.frames
    assert first.hitboxes == (sidecar.Box(x=18, y=8, width=12, height=10),)
    assert first.hurtboxes == (sidecar.Box(x=12, y=4, width=20, height=24),)
    assert first.markers == ("footstep",)
    assert second == sidecar.AuthoredFrame()


def test_an_absent_block_and_an_empty_frame_differ() -> None:
    # `None` is nothing to validate; an authored entry is a claim about the set's length.
    assert parse("").frames is None
    assert parse("frames:\n  - ~\n").frames == (sidecar.AuthoredFrame(),)


def test_marker_order_is_the_authors() -> None:
    # Unlike sections there is nothing to sort by: order on one frame carries no meaning,
    # and rewriting it would make the file differ from what the author typed.
    read = parse("frames:\n  - markers: [spawn, footstep]\n")
    assert read.frames is not None
    assert read.frames[0].markers == ("spawn", "footstep")


def test_a_frames_block_that_is_not_a_list() -> None:
    assert "frames is a dict" in refusal("frames:\n  0: {}\n").message


def test_a_frame_entry_that_is_not_a_map() -> None:
    assert "frames[0] is a str" in refusal("frames:\n  - punch\n").message


def test_an_unknown_frame_key() -> None:
    assert "frames[1] declares damage" in refusal("frames:\n  - ~\n  - damage: 3\n").message


@pytest.mark.parametrize("span", ["3", "[1, 2, 3]", "[1, 2, 3, four]", "[true, 0, 1, 1]"])
def test_a_box_that_is_not_four_whole_numbers(span: str) -> None:
    assert "frames[0].hitboxes[0]" in refusal(f"frames:\n  - hitboxes: [{span}]\n").message


@pytest.mark.parametrize("span", ["[-1, 0, 4, 4]", "[0, 0, 0, 4]", "[0, 0, 4, 0]"])
def test_a_box_off_the_cell_or_without_a_pixel(span: str) -> None:
    assert "frames[0].hurtboxes[0]" in refusal(f"frames:\n  - hurtboxes:\n    - {span}\n").message


def test_markers_that_are_not_names() -> None:
    assert "frames[0].markers" in refusal("frames:\n  - markers: [1, 2]\n").message
    assert "frames[0].markers" in refusal("frames:\n  - markers: ['']\n").message


def test_a_box_as_a_dict_and_as_a_span() -> None:
    box = sidecar.Box(x=1, y=2, width=3, height=4)
    assert box.as_dict() == {"x": 1, "y": 2, "width": 3, "height": 4}
    assert box.as_span() == [1, 2, 3, 4]


def test_an_authored_frame_round_trips_to_what_was_written() -> None:
    entry = sidecar.AuthoredFrame(hitboxes=(sidecar.Box(1, 2, 3, 4),), markers=("footstep",))
    assert entry.as_authored() == {"hitboxes": [[1, 2, 3, 4]], "markers": ["footstep"]}
    assert sidecar.AuthoredFrame().as_authored() is None


# R4.2 — the kind's frame rate where the author declared none.


def test_the_authors_frame_rate_wins() -> None:
    assert sidecar.frame_rate(sidecar.Playback(fps=8), kind_fps=24) == 8


def test_the_kinds_frame_rate_where_nothing_was_declared() -> None:
    assert sidecar.frame_rate(sidecar.Playback(), kind_fps=24) == 24


# R4.1 — reading one off disk, through the held directory.


def test_load_reads_the_sidecar_beside_meta_json(tmp_path: Path) -> None:
    (tmp_path / sidecar.SIDECAR_NAME).write_text("playback:\n  fps: 8\n", encoding="utf-8")
    with Directory.open(tmp_path) as held:
        assert sidecar.load(held).playback.fps == 8


def test_load_of_an_asset_with_no_sidecar_is_empty(tmp_path: Path) -> None:
    with Directory.open(tmp_path) as held:
        assert sidecar.load(held) == sidecar.Sidecar()


# R4.4 — authored, so nothing records it and nothing deletes it.


def test_the_sidecar_cannot_be_recorded_in_meta_json() -> None:
    record = meta.AssetMeta(key="hero", kind="character")
    with pytest.raises(UsageError) as refused:
        meta.record(
            record,
            path=sidecar.SIDECAR_NAME,
            stage="playback",
            file_class="derived",
            data=b"playback:\n  fps: 8\n",
            produced_by=meta.Provenance(command="test"),
        )
    assert refused.value.code == "sidecar-not-recorded"


def test_clean_leaves_the_sidecar_where_it_is(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    directory = tmp_path / "assets/character/hero"
    directory.mkdir(parents=True)
    (directory / "001_anchor.snap.png").write_bytes(b"computed")
    (directory / sidecar.SIDECAR_NAME).write_text("playback:\n  fps: 8\n", encoding="utf-8")

    record = meta.AssetMeta(key="hero", kind="character")
    meta.record(
        record,
        path="001_anchor.snap.png",
        stage="snap",
        file_class="derived",
        data=b"computed",
        produced_by=meta.Provenance(command="test"),
    )
    save_meta(directory, record)

    result = CliRunner().invoke(main, ["clean"], catch_exceptions=False)
    assert result.exit_code == 0
    assert not (directory / "001_anchor.snap.png").exists(), "the derived file did go"
    assert (directory / sidecar.SIDECAR_NAME).exists()


def test_load_names_the_file_it_refused(tmp_path: Path) -> None:
    (tmp_path / sidecar.SIDECAR_NAME).write_text("playback:\n  mode: bounce\n", encoding="utf-8")
    with Directory.open(tmp_path) as held, pytest.raises(SscError) as raised:
        sidecar.load(held)
    assert sidecar.SIDECAR_NAME in raised.value.message
