"""Snapping a set — specs/pixel-art-conversion R2.1, R2.2, R2.3, R2.6, R2.7.

The vendored module itself is covered by `tests/test_pixel_snapper_wasm.py`. What is here
is the part this leaf added: one grid across a set, the binding's error contract, and the
cache key.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from wasmtime import Func

from ssc.cli import snapper as snapper_module
from ssc.cli.cache import Cache
from ssc.cli.errors import SscError
from ssc.cli.frames import Frame
from ssc.cli.snap import SnapParams, decode, one_grid, snap_frames
from ssc.cli.snapper import Snapper

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/fake-pixels-8x8-at-12x.png"


@pytest.fixture(scope="module")
def snapper() -> Snapper:
    return Snapper()


@pytest.fixture(scope="module")
def fake_pixels() -> np.ndarray:
    with Image.open(FIXTURE) as handle:
        return np.array(handle.convert("RGBA"))


# R2.1, R2.6 — the binding, and what a refusal looks like.


def test_the_module_is_found_without_being_told_where(snapper: Snapper) -> None:
    assert snapper_module.module_path().is_file()


def test_a_module_that_is_not_there_is_an_error_with_the_rebuild_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapper_module, "MODULE_NAME", "not-a-real-module.wasm")
    with pytest.raises(SscError) as refused:
        snapper_module.module_path()
    assert refused.value.code == "snapper-missing"
    assert refused.value.fix is not None
    assert "wasm/build.py" in refused.value.fix


def test_an_export_that_is_not_there_is_named(snapper: Snapper) -> None:
    """`vendor/` is a binary nobody reads in review, so a swapped module has to say so
    here rather than fail as a TypeError from calling None."""
    with pytest.raises(SscError) as refused:
        snapper.call("ssc_not_an_export")
    assert refused.value.code == "snapper-abi"


def test_the_snapper_reports_its_own_message(snapper: Snapper, fake_pixels: np.ndarray) -> None:
    from ssc.cli.frames import encode

    with pytest.raises(SscError) as refused:
        snapper.snap(encode(fake_pixels), palette="not-a-colour")
    assert refused.value.code == "snap-failed"
    assert "palette" in refused.value.message
    assert refused.value.exit_code == 1


# R2.2 — one grid for the set, chosen deterministically.


def test_the_consensus_grid_is_the_one_most_frames_resolved_to() -> None:
    assert one_grid([(10, 10), (10, 10), (9, 9)]) == (10, 10)


def test_a_tie_breaks_towards_the_larger_grid_not_the_first_seen() -> None:
    """Order-independence matters: the same set read twice must snap the same way."""
    assert one_grid([(9, 9), (10, 10)]) == (10, 10)
    assert one_grid([(10, 10), (9, 9)]) == (10, 10)


def test_every_frame_of_a_set_comes_back_on_one_grid(
    snapper: Snapper, fake_pixels: np.ndarray
) -> None:
    frames = [Frame(f"{i:03d}.png", fake_pixels) for i in range(3)]
    out, measured = snap_frames(frames, SnapParams(grid=True), snapper)
    sizes = {(frame.image.shape[1], frame.image.shape[0]) for frame in out}
    assert len(sizes) == 1
    assert measured["grid"] == {"width": 10, "height": 10}


def test_a_frame_that_resolved_differently_is_brought_onto_the_consensus(
    snapper: Snapper, fake_pixels: np.ndarray
) -> None:
    """Two of three frames agree; the odd one is resampled onto their grid, and the count
    of frames that needed it is reported rather than hidden."""
    odd = np.array(Image.fromarray(fake_pixels, mode="RGBA").crop((0, 0, 48, 48)))
    frames = [
        Frame("001.png", fake_pixels),
        Frame("002.png", fake_pixels),
        Frame("003.png", odd),
    ]
    out, measured = snap_frames(frames, SnapParams(grid=True), snapper)
    sizes = {(frame.image.shape[1], frame.image.shape[0]) for frame in out}
    assert len(sizes) == 1
    assert measured["off_consensus"] == 1


# R2.3, R2.4 — the override, and the return to the size each frame arrived at.


def test_an_explicit_pixel_size_replaces_detection(
    snapper: Snapper, fake_pixels: np.ndarray
) -> None:
    detected, _ = snap_frames([Frame("a.png", fake_pixels)], SnapParams(grid=True), snapper)
    forced, _ = snap_frames(
        [Frame("a.png", fake_pixels)], SnapParams(grid=True, pixel_size=24.0), snapper
    )
    assert detected[0].image.shape != forced[0].image.shape


def test_without_grid_each_frame_returns_at_the_size_it_arrived_at(
    snapper: Snapper, fake_pixels: np.ndarray
) -> None:
    out, _ = snap_frames([Frame("a.png", fake_pixels)], SnapParams(), snapper)
    assert out[0].image.shape == fake_pixels.shape


def test_snapping_reduces_the_colours_that_are_actually_used(
    snapper: Snapper, fake_pixels: np.ndarray
) -> None:
    """R2.5 at the library boundary: the budget reaches the module."""
    out, _ = snap_frames([Frame("a.png", fake_pixels)], SnapParams(colors=4, grid=True), snapper)
    opaque = out[0].image.reshape(-1, 4)
    opaque = opaque[opaque[:, 3] > 0]
    assert len(np.unique(opaque[:, :3], axis=0)) <= 4


# R2.7 — the same frame and parameters are not snapped twice.


def test_a_second_identical_frame_is_reused_from_the_cache(
    snapper: Snapper, fake_pixels: np.ndarray, tmp_path: Path
) -> None:
    cache = Cache(tmp_path / "cache")
    frames = [Frame("a.png", fake_pixels), Frame("b.png", fake_pixels)]
    _, measured = snap_frames(frames, SnapParams(), snapper, cache)
    assert measured["reused"] == 1


def test_a_changed_parameter_is_not_a_cache_hit(
    snapper: Snapper, fake_pixels: np.ndarray, tmp_path: Path
) -> None:
    """The failure a content-only key produces is a stale image that looks plausible."""
    cache = Cache(tmp_path / "cache")
    frame = [Frame("a.png", fake_pixels)]
    snap_frames(frame, SnapParams(colors=16), snapper, cache)
    _, measured = snap_frames(frame, SnapParams(colors=4), snapper, cache)
    assert measured["reused"] == 0


def test_decode_round_trips_what_the_module_returned(
    snapper: Snapper, fake_pixels: np.ndarray
) -> None:
    from ssc.cli.frames import encode

    png = snapper.snap(encode(fake_pixels))
    assert decode(png).shape == (*Image.open(io.BytesIO(png)).size[::-1], 4)


# R2.8, R2.9 — the module's two ways of saying no.


def test_a_refused_allocation_is_an_error_and_nothing_is_written_into_the_module(
    snapper: Snapper, fake_pixels: np.ndarray, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ssc_alloc` returns a null pointer when it cannot allocate. Address zero is inside
    the guest's own memory, so writing there anyway corrupts the module's statics and the
    next result reads back as a perfectly successful conversion."""
    from ssc.cli.frames import encode

    written: list[int] = []
    # Every export answers zero — which for `ssc_alloc` is exactly "I could not allocate".
    monkeypatch.setattr(Snapper, "call", lambda self, name, *args: 0)
    monkeypatch.setattr(
        type(snapper.memory),
        "write",
        lambda self, store, data, start: written.append(start),
    )

    with pytest.raises(SscError) as refused:
        snapper.snap(encode(fake_pixels))
    assert refused.value.code == "snapper-oom"
    assert written == []


def test_a_trap_becomes_this_projects_error_contract(
    snapper: Snapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cli/main.py` catches `SscError` and nothing else, so a raw wasmtime error would
    leave the command as a traceback instead of the JSON object it promises."""
    from wasmtime import WasmtimeError

    def trap(self: object, store: object, *args: object) -> None:
        raise WasmtimeError("out of bounds memory access")

    monkeypatch.setattr(Func, "__call__", trap)
    with pytest.raises(SscError) as refused:
        snapper.call("ssc_result_len")
    assert refused.value.code == "snapper-trapped"
    assert refused.value.exit_code == 1


def test_the_grid_flag_is_not_part_of_the_cache_key(
    snapper: Snapper, fake_pixels: np.ndarray, tmp_path: Path
) -> None:
    """The cache holds the module's raw output, which `--grid` does not change — it only
    decides what happens to it afterwards."""
    cache = Cache(tmp_path / "cache")
    frame = [Frame("a.png", fake_pixels)]
    snap_frames(frame, SnapParams(grid=True), snapper, cache)
    _, measured = snap_frames(frame, SnapParams(grid=False), snapper, cache)
    assert measured["reused"] == 1
