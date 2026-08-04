"""`ssc preview` and the GIF encoder — specs/engine-index R6."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from conftest import save_meta
from PIL import Image

from ssc.cli import meta, preview
from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.errors import SscError
from ssc.cli.frames import encode
from ssc.core import preview as core_preview


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def swatch(width: int = 16, height: int = 16, value: int = 200) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :] = (value, value, value, 255)
    return image


# R6.1 — the encoder.


def test_a_gif_carries_every_frame_at_the_declared_rate() -> None:
    frames = [swatch(value=40), swatch(value=120), swatch(value=200)]
    data = preview.animated_gif(frames, fps=10)

    with Image.open(io.BytesIO(data)) as opened:
        assert opened.format == "GIF"
        assert opened.n_frames == 3
        assert opened.info["duration"] == 100


def test_a_gif_keeps_the_pixels_it_was_given() -> None:
    # No dithering: a preview that invents pixels is a preview of something else.
    art = np.zeros((4, 4, 4), dtype=np.uint8)
    art[:, :] = (10, 200, 30, 255)
    art[0, 0] = (250, 10, 10, 255)

    with Image.open(io.BytesIO(preview.animated_gif([art], fps=12))) as opened:
        seen = np.array(opened.convert("RGBA"))
    assert tuple(seen[0, 0][:3]) == (250, 10, 10)
    assert tuple(seen[1, 1][:3]) == (10, 200, 30)


def test_a_transparent_pixel_stays_transparent() -> None:
    art = np.zeros((4, 4, 4), dtype=np.uint8)
    art[2:, :] = (10, 200, 30, 255)

    with Image.open(io.BytesIO(preview.animated_gif([art], fps=12))) as opened:
        seen = np.array(opened.convert("RGBA"))
    assert seen[0, 0][3] == 0
    assert seen[3, 0][3] == 255


def test_a_frame_rate_faster_than_gif_can_hold_is_clamped() -> None:
    # Distinct frames on purpose: Pillow merges identical adjacent ones and adds their
    # durations together, which would make this assert 40 for reasons that are not the clamp.
    data = preview.animated_gif([swatch(value=10), swatch(value=200)], fps=200)
    with Image.open(io.BytesIO(data)) as opened:
        assert opened.info["duration"] == preview.MIN_FRAME_MS


@pytest.mark.parametrize(("frames", "fps"), [([], 12), ([swatch()], 0)])
def test_the_encoder_refuses_what_it_cannot_animate(frames: list[np.ndarray], fps: int) -> None:
    with pytest.raises(SscError):
        preview.animated_gif(frames, fps)


# R6.2, R6.3 — the two compositions.


def test_a_contact_sheet_holds_every_frame() -> None:
    laid_out = core_preview.contact([swatch(8, 8), swatch(8, 8), swatch(8, 8)])
    assert laid_out.ndim == 3
    # Two columns for three cells, and room under each for its label.
    assert laid_out.shape[0] > 8 and laid_out.shape[1] >= 16


def test_a_contact_sheet_of_nothing_is_refused() -> None:
    with pytest.raises(ValueError):
        core_preview.contact([])


def test_a_tile_is_repeated_rather_than_resampled() -> None:
    art = np.zeros((4, 4, 4), dtype=np.uint8)
    art[0, 0] = (255, 0, 0, 255)
    four = core_preview.tiled(art)

    assert four.shape == (8, 8, 4)
    for top in (0, 4):
        for left in (0, 4):
            assert tuple(four[top, left]) == (255, 0, 0, 255)


def test_a_tiling_of_less_than_once_is_refused() -> None:
    with pytest.raises(ValueError):
        core_preview.tiled(swatch(), times=0)


# The command, over a real workspace.


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ws.Workspace:
    monkeypatch.chdir(tmp_path)
    space = ws.create(tmp_path)

    hero = space.asset_dir("character", "hero")
    (hero / meta.FRAMES_DIR / "cut").mkdir(parents=True)
    record = meta.AssetMeta(key="hero", kind="character")
    payload = b""
    for number in (1, 2, 3, 4):
        data = encode(swatch(value=number * 50))
        (hero / meta.FRAMES_DIR / "cut" / f"{number:03d}.png").write_bytes(data)
        payload += data
    meta.record(
        record,
        path=f"{meta.FRAMES_DIR}/cut",
        stage="cut",
        file_class="derived",
        data=payload,
        produced_by=meta.Provenance(command="test"),
    )
    (hero / "asset.yaml").write_text(
        "playback:\n  fps: 8\n  mode: ping-pong\n  sections:\n    windup: [0, 1]\n",
        encoding="utf-8",
    )
    save_meta(hero, record)

    grass = space.asset_dir("tile", "grass")
    grass.mkdir(parents=True)
    one = meta.AssetMeta(key="grass", kind="tile")
    data = encode(swatch(32, 32))
    (grass / "001_grass.png").write_bytes(data)
    meta.record(
        one,
        path="001_grass.png",
        stage="gen",
        file_class="derived",
        data=data,
        produced_by=meta.Provenance(command="test"),
    )
    save_meta(grass, one)
    return space


def frames_in(path: Path) -> int:
    with Image.open(path) as opened:
        return int(getattr(opened, "n_frames", 1))


# R6.1, R6.6 — the GIF, under dist/preview/ and nowhere else.


def test_preview_renders_a_gif_in_the_declared_order(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "character/hero")
    assert code == 0
    assert payload["written"] == ["preview/character/hero.gif"]
    assert payload["fps"] == 8
    assert payload["mode"] == "ping-pong"
    # Four frames ping-ponged is six.
    assert frames_in(workspace.dist / "preview/character/hero.gif") == 6


def test_preview_writes_nowhere_but_dist_preview(workspace: ws.Workspace) -> None:
    run("index")
    before = sorted(path.relative_to(workspace.dist) for path in workspace.dist.rglob("*"))
    run("preview", "hero")
    after = sorted(path.relative_to(workspace.dist) for path in workspace.dist.rglob("*"))
    added = set(after) - set(before)
    assert all(str(one).startswith("preview") for one in added), added


# R6.2 — the contact sheet.


def test_preview_contact_writes_a_labelled_sheet(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "hero", "--contact")
    assert code == 0
    assert payload["written"] == ["preview/character/hero.png"]
    assert (workspace.dist / "preview/character/hero.png").is_file()


# R6.3 — a kind that declares `seam`.


def test_a_tile_is_previewed_tiled(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "grass")
    assert code == 0
    assert payload["written"] == ["preview/tile/grass.png"]
    with Image.open(workspace.dist / "preview/tile/grass.png") as opened:
        assert opened.size == (64, 64), "a 32x32 tile, 2x2"


# R6.4 — one section.


def test_a_named_section_is_the_only_thing_rendered(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "hero", "--section", "windup")
    assert code == 0
    assert payload["written"] == ["preview/character/hero-windup.gif"]
    # Two frames ping-ponged is two.
    assert frames_in(workspace.dist / "preview/character/hero-windup.gif") == 2


def test_a_section_nobody_declared_is_refused(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "hero", "--section", "recovery")
    assert code == 2
    assert payload["error"]["code"] == "unknown-section"
    assert "windup" in payload["error"]["message"]


# R6.5 — no index.


def test_preview_without_an_index_names_the_command_that_makes_one(
    workspace: ws.Workspace,
) -> None:
    code, payload = run("preview", "hero")
    assert code == 2
    assert payload["error"]["code"] == "no-index"
    assert payload["error"]["fix"] == "ssc index"


def test_preview_will_not_read_back_an_engine_format(workspace: ws.Workspace) -> None:
    run("index", "--format", "pixi")
    code, payload = run("preview", "hero")
    assert code == 2
    assert payload["error"]["code"] == "index-not-generic"


def test_an_asset_the_index_does_not_carry_is_refused(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "nobody")
    assert code == 2
    assert payload["error"]["code"] == "not-indexed"


# The index is a file between two processes, so `ssc preview` validates it on read.


def rewrite_index(space: ws.Workspace, change: Any) -> None:
    where = space.dist / "index.json"
    payload = json.loads(where.read_text(encoding="utf-8"))
    change(payload)
    where.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "spoil",
    [
        pytest.param(lambda entry: entry.update(columns=0), id="a grid with no columns"),
        pytest.param(lambda entry: entry.update(frames=10**9), id="more frames than pixels"),
        pytest.param(lambda entry: entry.update(frames="lots"), id="a frame count that is text"),
        pytest.param(lambda entry: entry["cell"].update(width=10**6), id="a cell past the image"),
        pytest.param(lambda entry: entry["playback"].update(fps="fast"), id="a rate that is text"),
        pytest.param(
            lambda entry: entry["playback"].update(mode="bounce"), id="a mode nobody defined"
        ),
        pytest.param(lambda entry: entry.pop("rows"), id="a missing field"),
    ],
)
def test_an_index_that_says_something_ssc_did_not_write_is_refused(
    workspace: ws.Workspace, spoil: Any
) -> None:
    # A hand-edited index reaches arithmetic otherwise: `columns: 0` divides by zero and a
    # billion frames is a list nobody can allocate. Both are answers, not tracebacks.
    run("index")
    rewrite_index(workspace, lambda payload: spoil(payload["sheets"][0]))

    code, payload = run("preview", "hero")
    assert code == 1
    assert payload["error"]["code"] == "index-invalid"


def test_an_entry_placed_off_its_own_atlas_is_refused(workspace: ws.Workspace) -> None:
    run("index")
    rewrite_index(workspace, lambda payload: payload["tilesets"][0]["tiles"][0].update(column=1000))
    code, payload = run("preview", "grass")
    assert code == 1
    assert payload["error"]["code"] == "index-invalid"


def test_a_dist_directory_that_is_really_somewhere_else_is_refused(
    workspace: ws.Workspace, tmp_path: Path, link_dir: Any
) -> None:
    # The finding this closes: a junction planted under `dist/` redirects a write out of the
    # workspace. `check_relative_path` validates a string and cannot see it.
    run("index")
    elsewhere = tmp_path.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    hijacked = workspace.dist / "sheets" / "character"
    for child in hijacked.iterdir():
        child.unlink()
    hijacked.rmdir()
    link_dir(hijacked, elsewhere)

    code, payload = run("index")
    assert code == 1
    assert payload["error"]["code"] == "dist-displaced"
    assert not any(elsewhere.iterdir()), "nothing was written through the link"


def test_a_dry_run_writes_nothing(workspace: ws.Workspace) -> None:
    run("index")
    code, payload = run("preview", "hero", "--dry-run")
    assert code == 0
    assert payload["dry_run"] is True
    assert not (workspace.dist / "preview").exists()
