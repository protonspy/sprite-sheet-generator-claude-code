"""The three commands — specs/pixel-art-conversion R1.1, R2.4, R2.5, R2.7."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/fake-pixels-8x8-at-12x.png"


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


@pytest.fixture
def art(tmp_path: Path) -> Path:
    shutil.copy(FIXTURE, tmp_path / "hero.png")
    return tmp_path / "hero.png"


@pytest.fixture
def art_set(tmp_path: Path) -> Path:
    source = tmp_path / "frames"
    source.mkdir()
    for name in ("001_a.png", "002_b.png"):
        shutil.copy(FIXTURE, source / name)
    return source


# R1.1 — no workspace anywhere in sight.


def test_snap_runs_outside_a_workspace(art: Path, tmp_path: Path) -> None:
    code, _ = run("tool", "snap", "--in", str(art), "--out", str(tmp_path / "out.png"))
    assert code == 0
    assert (tmp_path / "out.png").is_file()


# R2.4 — the size that comes back.


def test_by_default_a_frame_comes_back_at_the_size_it_arrived_at(art: Path, tmp_path: Path) -> None:
    run("tool", "snap", "--in", str(art), "--out", str(tmp_path / "out.png"))
    assert Image.open(tmp_path / "out.png").size == Image.open(art).size


def test_grid_emits_the_recovered_grid_itself(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "snap", "--grid", "--in", str(art), "--out", str(tmp_path / "out.png")
    )
    assert code == 0
    assert Image.open(tmp_path / "out.png").size == (10, 10)
    assert payload["grid"] == {"width": 10, "height": 10}


def test_a_set_writes_one_file_per_frame_on_one_grid(art_set: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "snap", "--grid", "--in", str(art_set), "--out", str(tmp_path / "out")
    )
    assert code == 0
    written = sorted((tmp_path / "out").iterdir())
    assert [path.name for path in written] == ["001_a.png", "002_b.png"]
    assert len({Image.open(path).size for path in written}) == 1
    assert payload["frames"] == 2


# R2.5 — the colour constraints reach the module.


def test_a_colour_budget_is_obeyed(art: Path, tmp_path: Path) -> None:
    import numpy as np

    run(
        "tool",
        "snap",
        "--colors",
        "4",
        "--grid",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "out.png"),
    )
    pixels = np.array(Image.open(tmp_path / "out.png").convert("RGBA")).reshape(-1, 4)
    opaque = pixels[pixels[:, 3] > 0]
    assert len(np.unique(opaque[:, :3], axis=0)) <= 4


def test_a_bad_palette_is_the_snappers_message_and_exit_one(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "snap",
        "--palette",
        "not-a-colour",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 1
    assert payload["error"]["code"] == "snap-failed"
    assert "palette" in payload["error"]["message"]
    assert not (tmp_path / "out.png").exists()


@pytest.mark.parametrize(
    ("flag", "value", "code"),
    [("--colors", "1", "invalid-colors"), ("--pixel-size", "0", "invalid-pixel-size")],
)
def test_a_parameter_outside_its_range_is_a_usage_error(
    art: Path, tmp_path: Path, flag: str, value: str, code: str
) -> None:
    exit_code, payload = run(
        "tool", "snap", flag, value, "--in", str(art), "--out", str(tmp_path / "out.png")
    )
    assert exit_code == 2
    assert payload["error"]["code"] == code


# R1.4, and the contract every command inherits.


def test_an_existing_output_is_refused_and_nothing_is_written(art: Path, tmp_path: Path) -> None:
    (tmp_path / "out.png").write_bytes(b"already here")
    code, payload = run("tool", "snap", "--in", str(art), "--out", str(tmp_path / "out.png"))
    assert code == 1
    assert payload["error"]["code"] == "file-exists"
    assert (tmp_path / "out.png").read_bytes() == b"already here"


def test_dry_run_reports_the_grid_and_writes_nothing(art: Path, tmp_path: Path) -> None:
    """The grid is what a caller runs this to find out, so --dry-run still answers it."""
    code, payload = run(
        "tool", "snap", "--dry-run", "--in", str(art), "--out", str(tmp_path / "out.png")
    )
    assert code == 0
    assert payload["dry_run"] is True
    assert payload["grid"] == {"width": 10, "height": 10}
    assert payload["written"] == [str(tmp_path / "out.png")]
    assert not (tmp_path / "out.png").exists()


# R2.7 — the cache is the workspace's, and only when there is one.


def test_inside_a_workspace_a_repeated_frame_is_reused(
    art_set: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    code, payload = run("tool", "snap", "--in", str(art_set), "--out", str(tmp_path / "out"))
    assert code == 0
    # The two frames are the same bytes, so the second is the first's cache hit.
    assert payload["reused"] == 1
    assert payload["cached"] is True


def test_outside_a_workspace_nothing_is_cached(art_set: Path, tmp_path: Path) -> None:
    code, payload = run("tool", "snap", "--in", str(art_set), "--out", str(tmp_path / "out"))
    assert code == 0
    assert payload["reused"] == 0
    assert payload["cached"] is False


# R3 — `ssc tool pixelart`.


def test_pixelart_writes_a_frame_on_the_computed_palette(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool", "pixelart", "--colors", "4", "--in", str(art), "--out", str(tmp_path / "out.png")
    )
    assert code == 0
    assert len(payload["palette"]) <= 4
    assert (tmp_path / "out.png").is_file()


def test_pixelart_computes_one_palette_for_the_whole_set(art_set: Path, tmp_path: Path) -> None:
    """R3.1 through the command: both frames report the same palette, because there is
    only one."""
    code, payload = run(
        "tool", "pixelart", "--colors", "6", "--in", str(art_set), "--out", str(tmp_path / "out")
    )
    assert code == 0
    assert payload["frames"] == 2

    import numpy as np

    reported = {tuple(int(entry[i : i + 2], 16) for i in (0, 2, 4)) for entry in payload["palette"]}
    written = sorted((tmp_path / "out").iterdir())
    for path in written:
        pixels = np.array(Image.open(path).convert("RGBA")).reshape(-1, 4)
        used = {tuple(colour) for colour in pixels[pixels[:, 3] > 0][:, :3]}
        # Every frame draws from the one palette, so no frame can hold a colour the set's
        # palette does not — which is exactly what per-frame quantization would produce.
        assert used <= reported


def test_a_given_palette_is_what_comes_out(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pixelart",
        "--palette",
        "0d2b45,ffecd6",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 0
    assert payload["palette"] == ["0d2b45", "ffecd6"]


def test_a_bad_palette_colour_is_a_usage_error(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pixelart",
        "--palette",
        "nothex",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-colour"


def test_dither_is_reported_so_a_caller_knows_what_it_got(art: Path, tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "pixelart",
        "--dither",
        "ordered",
        "--in",
        str(art),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 0
    assert payload["dither"] == "ordered"


def test_an_unknown_dither_mode_is_refused_by_the_parser(art: Path, tmp_path: Path) -> None:
    result = CliRunner().invoke(
        main,
        [
            "tool",
            "pixelart",
            "--dither",
            "invented",
            "--in",
            str(art),
            "--out",
            str(tmp_path / "o.png"),
        ],
    )
    assert result.exit_code == 2


def test_an_outline_reaches_the_written_file(tmp_path: Path) -> None:
    import numpy as np

    source = tmp_path / "sprite.png"
    pixels = np.zeros((8, 8, 4), dtype=np.uint8)
    pixels[3:5, 3:5] = (200, 30, 30, 255)
    Image.fromarray(pixels, mode="RGBA").save(source)

    code, _ = run(
        "tool",
        "pixelart",
        "--outline",
        "000000",
        "--colors",
        "2",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 0
    written = np.array(Image.open(tmp_path / "out.png").convert("RGBA"))
    assert tuple(written[2, 3]) == (0, 0, 0, 255)


# R4 — `ssc tool board`.


def test_a_checkerboard_is_written_with_its_layout(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "board",
        "checker",
        "--square",
        "8",
        "--size",
        "64x32",
        "--out",
        str(tmp_path / "board.png"),
    )
    assert code == 0
    assert payload["layout"] == {
        "columns": 8,
        "rows": 4,
        "cell": 8,
        "width": 64,
        "height": 32,
    }
    assert Image.open(tmp_path / "board.png").size == (64, 32)


def test_a_checkerboard_actually_alternates(tmp_path: Path) -> None:
    import numpy as np

    run(
        "tool",
        "board",
        "checker",
        "--square",
        "4",
        "--size",
        "16x16",
        "--out",
        str(tmp_path / "board.png"),
    )
    board_image = np.array(Image.open(tmp_path / "board.png").convert("RGBA"))
    assert tuple(board_image[0, 0, :3]) == (0, 0, 0)
    assert tuple(board_image[0, 4, :3]) == (255, 255, 255)
    assert tuple(board_image[4, 0, :3]) == (255, 255, 255)


def test_a_one_pixel_checkerboard_is_the_other_reading_of_the_sources(tmp_path: Path) -> None:
    """The two sources disagree on what a checkerboard is; `--square 1` is the other one,
    and which works is what `tool sweep` will answer."""
    import numpy as np

    run(
        "tool",
        "board",
        "checker",
        "--square",
        "1",
        "--size",
        "8x8",
        "--out",
        str(tmp_path / "board.png"),
    )
    board_image = np.array(Image.open(tmp_path / "board.png").convert("RGBA"))
    assert tuple(board_image[0, 0, :3]) != tuple(board_image[0, 1, :3])


def test_a_pose_board_reports_the_layout_the_generation_step_needs(tmp_path: Path) -> None:
    code, payload = run(
        "tool",
        "board",
        "poses",
        "--grid",
        "3x2",
        "--cell",
        "64",
        "--out",
        str(tmp_path / "poses.png"),
    )
    assert code == 0
    assert payload["layout"] == {
        "columns": 3,
        "rows": 2,
        "cell": 64,
        "width": 192,
        "height": 128,
    }
    assert Image.open(tmp_path / "poses.png").size == (192, 128)


def test_a_pose_board_draws_every_boundary(tmp_path: Path) -> None:
    import numpy as np

    run(
        "tool",
        "board",
        "poses",
        "--grid",
        "2x2",
        "--cell",
        "8",
        "--out",
        str(tmp_path / "poses.png"),
    )
    drawn = np.array(Image.open(tmp_path / "poses.png").convert("RGBA"))
    assert tuple(drawn[0, 0, :3]) == (0, 0, 0)
    assert tuple(drawn[8, 4, :3]) == (0, 0, 0)
    assert tuple(drawn[4, 4, :3]) == (255, 255, 255)
    assert tuple(drawn[-1, 4, :3]) == (0, 0, 0)


@pytest.mark.parametrize(
    ("argv", "code"),
    [
        (("checker", "--size", "notasize"), "invalid-size"),
        (("checker", "--square", "999", "--size", "64x64"), "invalid-square"),
        (("poses", "--grid", "3x2", "--cell", "99999"), "invalid-cell"),
        (("poses", "--grid", "0x2"), "invalid-size"),
    ],
)
def test_a_board_outside_its_bounds_is_a_usage_error(
    tmp_path: Path, argv: tuple[str, ...], code: str
) -> None:
    exit_code, payload = run("tool", "board", *argv, "--out", str(tmp_path / "b.png"))
    assert exit_code == 2
    assert payload["error"]["code"] == code


def test_a_board_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "board.png").write_bytes(b"already here")
    code, payload = run(
        "tool", "board", "checker", "--size", "16x16", "--out", str(tmp_path / "board.png")
    )
    assert code == 1
    assert payload["error"]["code"] == "file-exists"


# specs/background-removal — `ssc tool bgremove`.


def green_scene(path: Path) -> Path:
    """A green backdrop, a subject, and a green gem the subject encloses."""
    import numpy as np

    from ssc.core.bgremove import PRESETS

    image = np.zeros((10, 10, 4), dtype=np.uint8)
    image[..., :3] = PRESETS["green"]
    image[..., 3] = 255
    image[2:8, 2:8, :3] = (220, 180, 150)
    image[4:6, 4:6, :3] = PRESETS["green"]
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGBA").save(path)
    return path


def test_bgremove_defaults_to_flood_so_the_gem_survives(tmp_path: Path) -> None:
    import numpy as np

    source = green_scene(tmp_path / "hero.png")
    code, payload = run(
        "tool", "bgremove", "--tol", "10", "--in", str(source), "--out", str(tmp_path / "out.png")
    )
    assert code == 0
    assert payload["mode"] == "flood"

    written = np.array(Image.open(tmp_path / "out.png").convert("RGBA"))
    assert written[0, 0, 3] == 0
    assert written[4, 4, 3] == 255


def test_global_mode_takes_the_gem(tmp_path: Path) -> None:
    import numpy as np

    source = green_scene(tmp_path / "hero.png")
    run(
        "tool",
        "bgremove",
        "--mode",
        "global",
        "--tol",
        "10",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "out.png"),
    )
    written = np.array(Image.open(tmp_path / "out.png").convert("RGBA"))
    assert written[4, 4, 3] == 0


def test_the_written_frame_passes_this_projects_own_halo_check(tmp_path: Path) -> None:
    """R3.1 end to end. Deliberately *without* `--edge-pass`: the alpha is binary whatever
    flags are passed, and a version of this test that passed the flag would have looked like
    it proved the flag mattered while proving only this."""
    import numpy as np

    from ssc.core.doctor import check_halo

    source = green_scene(tmp_path / "hero.png")
    run("tool", "bgremove", "--tol", "90", "--in", str(source), "--out", str(tmp_path / "o.png"))
    written = np.array(Image.open(tmp_path / "o.png").convert("RGBA"))
    assert check_halo(written).clean


def test_the_edge_pass_is_what_takes_the_cast_out_through_the_cli(tmp_path: Path) -> None:
    """What `--edge-pass` actually changes, which `check_halo` cannot see: `halo` reads
    alpha only, and alpha is already binary by R3.1. The flag is about colour."""
    import numpy as np

    from ssc.core.bgremove import PRESETS

    image = np.zeros((6, 6, 4), dtype=np.uint8)
    image[..., :3] = PRESETS["green"]
    image[..., 3] = 255
    image[2:4, 2:4, :3] = (220, 180, 150)
    image[2, 2, :3] = (90, 200, 80)  # a subject pixel carrying green spill
    source = tmp_path / "spill.png"
    Image.fromarray(image, mode="RGBA").save(source)

    def cast_at(out: Path, *flags: str) -> tuple[int, int, int]:
        run("tool", "bgremove", "--tol", "40", *flags, "--in", str(source), "--out", str(out))
        written = np.array(Image.open(out).convert("RGBA"))
        return tuple(int(value) for value in written[2, 2, :3])  # type: ignore[return-value]

    kept = cast_at(tmp_path / "kept.png")
    cleaned = cast_at(tmp_path / "cleaned.png", "--edge-pass")

    assert kept == (90, 200, 80), "without the flag the cast is left alone"
    assert cleaned[1] <= max(cleaned[0], cleaned[2]), "with it the green is clamped down"
    assert cleaned != kept


def test_a_magenta_preset_is_named_not_remembered(tmp_path: Path) -> None:
    import numpy as np

    from ssc.core.bgremove import PRESETS

    image = np.zeros((6, 6, 4), dtype=np.uint8)
    image[..., :3] = PRESETS["magenta"]
    image[..., 3] = 255
    image[2:4, 2:4, :3] = (10, 20, 30)
    source = tmp_path / "hero.png"
    Image.fromarray(image, mode="RGBA").save(source)

    code, payload = run(
        "tool",
        "bgremove",
        "--chroma",
        "magenta",
        "--tol",
        "10",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 0
    assert payload["opaque_px"] == 4


def test_a_hex_key_works_too(tmp_path: Path) -> None:
    source = green_scene(tmp_path / "hero.png")
    code, _ = run(
        "tool",
        "bgremove",
        "--chroma",
        "00b140",
        "--tol",
        "10",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 0


def test_a_key_that_is_neither_is_a_usage_error(tmp_path: Path) -> None:
    source = green_scene(tmp_path / "hero.png")
    code, payload = run(
        "tool",
        "bgremove",
        "--chroma",
        "chartreuse",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-chroma"
    assert not (tmp_path / "out.png").exists()


@pytest.mark.parametrize(
    ("flag", "value", "code"),
    [
        ("--tol", "-1", "invalid-tolerance"),
        ("--tol", "9999", "invalid-tolerance"),
        ("--edge-trim", "-1", "invalid-amount"),
        ("--despeckle", "-2", "invalid-amount"),
    ],
)
def test_a_parameter_outside_its_range_is_refused(
    tmp_path: Path, flag: str, value: str, code: str
) -> None:
    source = green_scene(tmp_path / "hero.png")
    exit_code, payload = run(
        "tool", "bgremove", flag, value, "--in", str(source), "--out", str(tmp_path / "out.png")
    )
    assert exit_code == 2
    assert payload["error"]["code"] == code


def test_a_set_is_keyed_frame_by_frame_and_counted_across_them(tmp_path: Path) -> None:
    source = tmp_path / "frames"
    green_scene(source / "001_a.png")
    green_scene(source / "002_b.png")
    code, payload = run(
        "tool", "bgremove", "--tol", "10", "--in", str(source), "--out", str(tmp_path / "out")
    )
    assert code == 0
    assert payload["frames"] == 2
    assert payload["transparent_px"] + payload["opaque_px"] == 2 * 100
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == ["001_a.png", "002_b.png"]


def test_an_absurd_edge_trim_is_refused_rather_than_run(tmp_path: Path) -> None:
    """The one dial whose cost is set independently of the input size."""
    source = green_scene(tmp_path / "hero.png")
    code, payload = run(
        "tool",
        "bgremove",
        "--edge-trim",
        "2000000000",
        "--in",
        str(source),
        "--out",
        str(tmp_path / "out.png"),
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-amount"
    assert not (tmp_path / "out.png").exists()
