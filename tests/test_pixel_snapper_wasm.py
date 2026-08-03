"""The vendored snapper is a build artifact, so it is tested as one.

These tests do not exercise `ssc tool snap` — that command belongs to
`specs/pixel-art-conversion/`. They prove the thing task 0.1 of `plans/ssc-pipeline.md`
was blocked on: that `vendor/pixel-snapper.wasm` loads under `wasmtime` with nothing but
WASI to satisfy, and that it snaps a fixture.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from wasmtime import Engine, Linker, Module, Store, WasiConfig

REPO = Path(__file__).resolve().parent.parent
WASM = REPO / "vendor/pixel-snapper.wasm"
FIXTURE = REPO / "tests/fixtures/fake-pixels-8x8-at-12x.png"

# The fixture is an 8x8 sprite bicubic-upscaled to 96x96 — fake pixels with soft edges.
# Upstream auto-detects an 11px grid there and emits 10x10; both numbers are measured
# against the pinned build, not chosen. See tests/fixtures/README.md.
DETECTED_SIZE = (10, 10)


class Snapper:
    """One instantiation of the module, driving the flat ABI in wasm/README.md."""

    def __init__(self) -> None:
        engine = Engine()
        self.module = Module.from_file(engine, str(WASM))
        linker = Linker(engine)
        linker.define_wasi()
        self.store = Store(engine)
        self.store.set_wasi(WasiConfig())
        self.exports = linker.instantiate(self.store, self.module).exports(self.store)
        self.memory = self.exports["memory"]

    def _read(self, ptr: int, length: int) -> bytes:
        return bytes(self.memory.read(self.store, ptr, ptr + length))

    def snap(
        self,
        png: bytes,
        k_colors: int = 16,
        pixel_size: float = 0.0,
        palette: str = "",
    ) -> bytes:
        """Return the snapped PNG, or raise with the module's own message."""
        in_ptr = self.exports["ssc_alloc"](self.store, len(png))
        self.memory.write(self.store, png, in_ptr)
        pal = palette.encode()
        pal_ptr = self.exports["ssc_alloc"](self.store, len(pal)) if pal else 0
        if pal:
            self.memory.write(self.store, pal, pal_ptr)
        try:
            rc = self.exports["ssc_snap"](
                self.store, in_ptr, len(png), k_colors, pixel_size, pal_ptr, len(pal)
            )
            if rc != 0:
                message = self._read(
                    self.exports["ssc_error_ptr"](self.store),
                    self.exports["ssc_error_len"](self.store),
                )
                raise RuntimeError(message.decode())
            return self._read(
                self.exports["ssc_result_ptr"](self.store),
                self.exports["ssc_result_len"](self.store),
            )
        finally:
            self.exports["ssc_dealloc"](self.store, in_ptr, len(png))
            if pal:
                self.exports["ssc_dealloc"](self.store, pal_ptr, len(pal))


@pytest.fixture(scope="module")
def snapper() -> Iterator[Snapper]:
    yield Snapper()


@pytest.fixture(scope="module")
def fake_pixels() -> bytes:
    return FIXTURE.read_bytes()


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
    out = Image.open(io.BytesIO(snapper.snap(fake_pixels, k_colors=4)))
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
    with pytest.raises(RuntimeError, match="palette"):
        snapper.snap(fake_pixels, palette="not-a-colour")
    assert snapper.snap(fake_pixels)


def test_empty_input_is_an_error_not_a_trap(snapper: Snapper) -> None:
    with pytest.raises(RuntimeError, match="no input bytes"):
        snapper.snap(b"")


def test_the_instance_is_reusable_across_frames(snapper: Snapper, fake_pixels: bytes) -> None:
    """`snap` runs per frame, so one instantiation has to serve many calls."""
    first = snapper.snap(fake_pixels)
    assert all(snapper.snap(fake_pixels) == first for _ in range(3))
