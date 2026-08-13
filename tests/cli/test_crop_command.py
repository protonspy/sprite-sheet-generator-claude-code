"""`ssc tool crop` — specs/frame-cropping R1, R2, R3."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from click.testing import CliRunner
from conftest import load_meta
from PIL import Image

from ssc.cli.app import main


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def save(path: Path, image: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGBA").save(path)
    return path


def block(width: int = 12, height: int = 12, shade: int = 200) -> np.ndarray:
    """An opaque frame whose pixels say where in the canvas they came from."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[..., 0] = np.arange(width, dtype=np.uint8)
    image[..., 1] = np.arange(height, dtype=np.uint8)[:, None]
    image[..., 2] = shade
    image[..., 3] = 255
    return image


def one(tmp_path: Path, width: int = 12, height: int = 12) -> Path:
    return save(tmp_path / "frame.png", block(width, height))


def a_set(tmp_path: Path, count: int = 3, width: int = 12, height: int = 12) -> Path:
    for index in range(count):
        save(tmp_path / "frames" / f"{index + 1:03d}.png", block(width, height))
    return tmp_path / "frames"


def opened(path: Path) -> np.ndarray:
    with Image.open(path) as handle:
        return np.array(handle.convert("RGBA"))


# R1.1, R1.3 — a stated box, cut out of one image or out of a set.


def test_a_stated_box_cuts_one_image(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "crop", "--box", "2,3,4x5", "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 0, payload
    assert payload["box"] == {"x": 2, "y": 3, "width": 4, "height": 5}
    cut = opened(tmp_path / "o" / "frame.png")
    assert cut.shape[:2] == (5, 4)
    # the pixels are the ones that stood at (2, 3), not a resample of the whole frame
    assert cut[0, 0, 0] == 2
    assert cut[0, 0, 1] == 3


def test_a_stated_box_cuts_every_frame_of_a_set(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--box",
        "0,0,6x6",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["frames"] == 3
    assert payload["size"] == {"width": 6, "height": 6}
    assert sorted(path.name for path in (tmp_path / "o").iterdir()) == [
        "001.png",
        "002.png",
        "003.png",
    ]
    assert all(opened(path).shape[:2] == (6, 6) for path in (tmp_path / "o").iterdir())


# R1.6 — crop never invents a pixel, and the frame that did not fit is named.


@pytest.mark.parametrize("box", ["8,0,8x4", "0,8,4x8", "-1,0,4x4"])
def test_a_box_that_is_not_wholly_inside_the_frame_is_refused(tmp_path: Path, box: str) -> None:
    code, payload = run(
        "tool", "crop", "--box", box, "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 2
    assert payload["error"]["code"] == "box-outside-frame"
    assert "frame.png" in payload["error"]["message"]
    assert "expand" in payload["error"]["fix"]
    assert not (tmp_path / "o").exists()


def test_the_frame_named_is_the_one_that_did_not_fit(tmp_path: Path) -> None:
    """A set of ninety says nothing without the name of the one that refused."""
    a_set(tmp_path, count=3)
    save(tmp_path / "frames" / "004.png", block(width=6, height=6))

    code, payload = run(
        "tool",
        "crop",
        "--box",
        "0,0,10x10",
        "--in",
        str(tmp_path / "frames"),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 2
    assert "004.png" in payload["error"]["message"]


@pytest.mark.parametrize("box", ["4,4", "4,4,16", "a,4,4x4", "4,4,0x4", "4,4,4x"])
def test_a_box_that_is_not_a_box_is_refused(tmp_path: Path, box: str) -> None:
    code, payload = run(
        "tool", "crop", "--box", box, "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-box"


@pytest.mark.parametrize(
    ("flag", "value", "code"),
    [
        ("--box", "0,0,99999999999x4", "invalid-box"),
        ("--aspect", "99999999999:9", "invalid-aspect"),
        ("--inset", "99999999999", "invalid-inset"),
    ],
)
def test_a_number_far_past_any_image_is_refused_at_the_flag(
    tmp_path: Path, flag: str, value: str, code: str
) -> None:
    """`args.parse_guides` bounds its numbers for the same reason: a refusal naming the
    flag beats whatever the arithmetic does with a coordinate of a few hundred digits."""
    exit_code, payload = run(
        "tool", "crop", flag, value, "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert exit_code == 2
    assert payload["error"]["code"] == code


# R1.2 — exactly one way of stating the box, and the other two ways reach the frames.


def test_an_aspect_cuts_the_largest_rectangle_of_that_ratio(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--aspect",
        "16:9",
        "--in",
        str(one(tmp_path, width=32, height=32)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["size"] == {"width": 32, "height": 18}
    # centred by default: 14 rows left over, 7 above
    assert payload["box"] == {"x": 0, "y": 7, "width": 32, "height": 18}


def test_a_gravity_moves_where_the_aspect_box_sits(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--aspect",
        "16:9",
        "--gravity",
        "bottom",
        "--in",
        str(one(tmp_path, width=32, height=32)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["box"]["y"] + payload["box"]["height"] == 32


def test_one_inset_comes_off_every_side(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "crop", "--inset", "2", "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 0, payload
    assert payload["box"] == {"x": 2, "y": 2, "width": 8, "height": 8}


def test_four_insets_are_read_clockwise_from_the_top(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--inset",
        "1,2,3,4",
        "--in",
        str(one(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["box"] == {"x": 4, "y": 1, "width": 6, "height": 8}


def test_nothing_stating_the_box_is_refused(tmp_path: Path) -> None:
    code, payload = run("tool", "crop", "--in", str(one(tmp_path)), "--out", str(tmp_path / "o"))

    assert code == 2
    assert payload["error"]["code"] == "no-box"
    assert "--aspect" in payload["error"]["fix"]


@pytest.mark.parametrize(
    "extra",
    [("--box", "0,0,4x4", "--inset", "2"), ("--aspect", "1:1", "--inset", "2")],
)
def test_two_ways_of_stating_the_box_are_refused(tmp_path: Path, extra: tuple[str, ...]) -> None:
    """Both would produce a rectangle, and nothing says which one the caller meant."""
    code, payload = run(
        "tool", "crop", *extra, "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 2
    assert payload["error"]["code"] == "two-boxes"


def test_an_inset_that_leaves_nothing_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "crop", "--inset", "6", "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-box"
    assert "no pixels" in payload["error"]["message"]


def test_a_negative_inset_is_refused_rather_than_padding(tmp_path: Path) -> None:
    code, payload = run(
        "tool", "crop", "--inset", "-2", "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 2
    assert "tool expand" in payload["error"]["message"]


@pytest.mark.parametrize(
    ("flag", "value", "code"),
    [("--aspect", "16x9", "invalid-aspect"), ("--inset", "1,2", "invalid-inset")],
)
def test_a_ratio_or_an_inset_that_does_not_parse_is_refused(
    tmp_path: Path, flag: str, value: str, code: str
) -> None:
    exit_code, payload = run(
        "tool", "crop", flag, value, "--in", str(one(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert exit_code == 2
    assert payload["error"]["code"] == code


# R2.1, R2.2 — one box for the set, or one for each frame.


def mixed(tmp_path: Path) -> Path:
    """A directory nobody normalised: two frames at two canvas sizes."""
    save(tmp_path / "frames" / "001.png", block(width=20, height=20))
    save(tmp_path / "frames" / "002.png", block(width=10, height=10))
    return tmp_path / "frames"


def test_one_box_for_the_set_refuses_a_frame_it_does_not_fit(tmp_path: Path) -> None:
    """The default keeps the frames registered, so a set at mixed sizes is a refusal."""
    code, payload = run(
        "tool", "crop", "--inset", "2", "--in", str(mixed(tmp_path)), "--out", str(tmp_path / "o")
    )

    assert code == 2
    assert payload["error"]["code"] == "box-outside-frame"
    assert "002.png" in payload["error"]["message"]


def test_per_frame_computes_the_box_against_each_frame(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--inset",
        "2",
        "--per-frame",
        "--in",
        str(mixed(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert opened(tmp_path / "o" / "001.png").shape[:2] == (16, 16)
    assert opened(tmp_path / "o" / "002.png").shape[:2] == (6, 6)


def test_per_frame_over_one_canvas_is_the_same_crop(tmp_path: Path) -> None:
    """Every frame on one canvas, so the two modes agree — the flag costs nothing there."""
    code, payload = run(
        "tool",
        "crop",
        "--aspect",
        "1:2",
        "--per-frame",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["box"] == {"x": 3, "y": 0, "width": 6, "height": 12}
    assert all(opened(path).shape[:2] == (12, 6) for path in (tmp_path / "o").iterdir())


# R2.4 — what was cut, and what came out.


def test_a_set_cropped_to_one_box_reports_it_once(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--inset",
        "1",
        "--in",
        str(a_set(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["box"] == {"x": 1, "y": 1, "width": 10, "height": 10}
    assert payload["size"] == {"width": 10, "height": 10}
    assert "boxes" not in payload


def test_boxes_that_differ_are_reported_one_by_one(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--inset",
        "2",
        "--per-frame",
        "--in",
        str(mixed(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert [entry["frame"] for entry in payload["boxes"]] == ["001.png", "002.png"]
    assert payload["boxes"][1]["box"] == {"x": 2, "y": 2, "width": 6, "height": 6}


# R2.3, R3.5 — the two calls --per-frame cannot be part of.


def test_per_frame_with_a_stated_box_is_refused(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--box",
        "0,0,4x4",
        "--per-frame",
        "--in",
        str(one(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 2
    assert payload["error"]["code"] == "per-frame-with-box"


@pytest.mark.parametrize(
    "extra",
    [("--asset", "character/hero"), ("--out", "o", "--anchor", "4,4")],
)
def test_per_frame_with_a_record_for_the_whole_set_is_refused(
    tmp_path: Path, extra: tuple[str, ...]
) -> None:
    """One move for the authored boxes and one anchor, so neither follows a per-frame crop."""
    code, payload = run(
        "tool", "crop", "--inset", "2", "--per-frame", "--in", str(one(tmp_path)), *extra
    )

    assert code == 2
    assert payload["error"]["code"] == "per-frame-with-a-record"


# R3.1 — exactly one destination, the same choice every command with an --asset makes.


@pytest.mark.parametrize("extra", [(), ("--asset", "character/hero", "--out", "x")])
def test_neither_destination_or_both_is_refused(tmp_path: Path, extra: tuple[str, ...]) -> None:
    code, payload = run("tool", "crop", "--box", "0,0,4x4", "--in", str(one(tmp_path)), *extra)

    assert code == 2
    assert payload["error"]["code"] == "no-destination"


# R3.2, R3.3, R3.4 — a crop into an asset is a recorded stage, and it takes the authored
# geometry with it.


def in_a_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = a_set(tmp_path)
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    CliRunner().invoke(
        main, ["asset", "new", "hero", "--kind", "character"], catch_exceptions=False
    )
    return source


def test_a_crop_into_an_asset_records_the_stage_and_its_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = in_a_workspace(tmp_path, monkeypatch)

    code, payload = run(
        "tool", "crop", "--box", "2,2,8x8", "--in", str(source), "--asset", "character/hero"
    )

    assert code == 0, payload
    record = load_meta(tmp_path / "assets/character/hero")
    entries = [entry for entry in record.files if entry.stage == "crop"]
    assert len(entries) == 1
    assert entries[0].path == "frames/crop"
    assert entries[0].file_class == "derived"
    assert entries[0].produced_by.command == "tool crop"
    assert entries[0].produced_by.params == {"box": {"x": 2, "y": 2, "width": 8, "height": 8}}
    assert payload["written"] == [
        "frames/crop/001.png",
        "frames/crop/002.png",
        "frames/crop/003.png",
    ]


def test_a_crop_moves_the_authored_boxes_by_the_same_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = in_a_workspace(tmp_path, monkeypatch)
    sidecar = tmp_path / "assets/character/hero/asset.yaml"
    sidecar.write_text(
        yaml.safe_dump({"frames": [{"hitboxes": [[4, 5, 2, 2]]}, None, None]}), encoding="utf-8"
    )

    code, payload = run(
        "tool", "crop", "--box", "2,3,8x8", "--in", str(source), "--asset", "character/hero"
    )

    assert code == 0, payload
    assert payload["sidecar"] == str(sidecar)
    document = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    # cropping to (2, 3) moves every pixel — and every box — by the box's origin
    assert document["frames"][0]["hitboxes"] == [[2, 2, 2, 2]]


def test_a_box_outside_the_crop_is_dropped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = in_a_workspace(tmp_path, monkeypatch)
    sidecar = tmp_path / "assets/character/hero/asset.yaml"
    sidecar.write_text(
        yaml.safe_dump({"frames": [{"hurtboxes": [[0, 0, 2, 2]]}, None, None]}), encoding="utf-8"
    )

    code, payload = run(
        "tool", "crop", "--box", "6,6,4x4", "--in", str(source), "--asset", "character/hero"
    )

    assert code == 0, payload
    document = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    assert document["frames"] == [None, None, None]


def test_the_anchor_moves_by_the_box_origin(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--box",
        "2,3,8x8",
        "--anchor",
        "6,7",
        "--in",
        str(one(tmp_path)),
        "--out",
        str(tmp_path / "o"),
    )

    assert code == 0, payload
    assert payload["anchor"] == {"x": 4, "y": 4}


def test_a_dry_run_writes_nothing_and_says_what_it_would(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "crop",
        "--box",
        "0,0,4x4",
        "--in",
        str(one(tmp_path)),
        "--out",
        str(tmp_path / "o"),
        "--dry-run",
    )

    assert code == 0, payload
    assert payload["written"]
    assert not (tmp_path / "o").exists()
