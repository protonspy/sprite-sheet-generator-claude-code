"""The vendored snapper is a build artifact, so it is tested as one.

These tests do not exercise `ssc tool snap` — that command belongs to
`specs/pixel-art-conversion/`. They prove the thing task 0.1 of `plans/ssc-pipeline.md`
was blocked on: that `vendor/pixel-snapper.wasm` loads under `wasmtime` with nothing but
WASI to satisfy, and that it snaps a fixture.

The `Snapper` class they drive used to live here. It moved into `ssc.cli.snapper` when
`ssc tool snap` needed it, and these tests import it rather than keeping a second copy: the
binary's ABI gets one reader, so a change to it fails here as well as in the command.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from wasmtime import Engine, Module

from ssc.cli.errors import SscError
from ssc.cli.snapper import Snapper

REPO = Path(__file__).resolve().parent.parent
WASM = REPO / "vendor/pixel-snapper.wasm"
DIGEST = REPO / "vendor/pixel-snapper.wasm.sha256"
FIXTURE = REPO / "tests/fixtures/fake-pixels-8x8-at-12x.png"

# The fixture is an 8x8 sprite bicubic-upscaled to 96x96 — fake pixels with soft edges.
# Upstream auto-detects an 11px grid there and emits 10x10; both numbers are measured
# against the pinned build, not chosen. See tests/fixtures/README.md.
DETECTED_SIZE = (10, 10)


@pytest.fixture(scope="module")
def snapper() -> Iterator[Snapper]:
    yield Snapper(WASM)


@pytest.fixture(scope="module")
def fake_pixels() -> bytes:
    return FIXTURE.read_bytes()


def test_the_committed_module_matches_its_recorded_digest() -> None:
    """CI does not rebuild the module, so nothing else here would notice it being
    replaced. This does not prove the binary came from the pinned source — only
    `wasm/build.py --check` does that — but it makes swapping it a visible one-line diff
    rather than 350KB nobody can read."""
    recorded = DIGEST.read_text(encoding="utf-8").split()[0]
    assert hashlib.sha256(WASM.read_bytes()).hexdigest() == recorded


def test_module_needs_nothing_but_wasi() -> None:
    """wasm-bindgen glue would show up here as a `__wbindgen_*` import."""
    module = Module.from_file(Engine(), str(WASM))
    modules = {imp.module for imp in module.imports}
    assert modules == {"wasi_snapshot_preview1"}


def test_module_exports_the_flat_abi() -> None:
    module = Module.from_file(Engine(), str(WASM))
    names = {export.name for export in module.exports}
    assert {
        "memory",
        "ssc_alloc",
        "ssc_dealloc",
        "ssc_snap",
        "ssc_result_ptr",
        "ssc_result_len",
        "ssc_error_ptr",
        "ssc_error_len",
    } <= names


def test_snapping_recovers_the_grid(snapper: Snapper, fake_pixels: bytes) -> None:
    """96x96 of fake pixels comes back as a genuinely small image."""
    out = Image.open(io.BytesIO(snapper.snap(fake_pixels)))
    assert out.size == DETECTED_SIZE


def test_snapping_honours_the_colour_budget(snapper: Snapper, fake_pixels: bytes) -> None:
    out = Image.open(io.BytesIO(snapper.snap(fake_pixels, colors=4)))
    opaque = np.array(out.convert("RGBA")).reshape(-1, 4)
    opaque = opaque[opaque[:, 3] > 0]
    assert len(np.unique(opaque[:, :3], axis=0)) <= 4


def test_pixel_size_override_is_obeyed(snapper: Snapper, fake_pixels: bytes) -> None:
    """An override replaces detection, so the result is smaller than the detected grid."""
    out = Image.open(io.BytesIO(snapper.snap(fake_pixels, pixel_size=12.0)))
    assert out.size == (9, 9)


def test_a_palette_constrains_the_output(snapper: Snapper, fake_pixels: bytes) -> None:
    out = Image.open(io.BytesIO(snapper.snap(fake_pixels, palette="0d2b45,ffecd6")))
    opaque = np.array(out.convert("RGBA")).reshape(-1, 4)
    opaque = opaque[opaque[:, 3] > 0]
    assert {tuple(c) for c in np.unique(opaque[:, :3], axis=0)} <= {
        (0x0D, 0x2B, 0x45),
        (0xFF, 0xEC, 0xD6),
    }


def test_a_bad_palette_is_an_error_not_a_trap(snapper: Snapper, fake_pixels: bytes) -> None:
    """The module reports failure through the ABI; the instance stays usable."""
    with pytest.raises(SscError, match="palette"):
        snapper.snap(fake_pixels, palette="not-a-colour")
    assert snapper.snap(fake_pixels)


def test_empty_input_is_an_error_not_a_trap(snapper: Snapper) -> None:
    with pytest.raises(SscError, match="no input bytes"):
        snapper.snap(b"")


def test_a_failed_call_clears_the_previous_result(snapper: Snapper, fake_pixels: bytes) -> None:
    """One instance serves many frames, so a failure must not leave the previous frame
    readable — a caller that ignored the return code would otherwise get stale output."""
    assert snapper.snap(fake_pixels)
    with pytest.raises(SscError):
        snapper.snap(b"not an image at all")
    assert snapper.result_len() == 0


def test_the_instance_is_reusable_across_frames(snapper: Snapper, fake_pixels: bytes) -> None:
    """`snap` runs per frame, so one instantiation has to serve many calls."""
    first = snapper.snap(fake_pixels)
    assert all(snapper.snap(fake_pixels) == first for _ in range(3))
