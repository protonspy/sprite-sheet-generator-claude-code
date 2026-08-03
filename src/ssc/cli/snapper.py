"""The binding to `vendor/pixel-snapper.wasm`.

It lives in `cli/` and not `core/` because it loads a file from disk and holds a `wasmtime`
store — exactly the two things `core/` is defined not to do. The flat ABI it drives, and
the reason there is one at all rather than wasm-bindgen glue, are in `wasm/README.md` and
`adr:0003-patch-upstream-and-call-it-over-a-flat-abi`.

One instance serves a whole frame set. `snap` runs per frame and twice per pipeline, so
instantiating the module per frame is the difference between a fast command and a slow one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wasmtime import Engine, Func, Linker, Memory, Module, Store, WasiConfig, WasmtimeError

from ssc.cli.errors import SscError

MODULE_NAME = "pixel-snapper.wasm"


def module_path() -> Path:
    """Where the vendored module is, installed or in a checkout.

    Two locations because there are two ways this package exists: a wheel, where the binary
    is force-included beside the package as `ssc/vendor/`, and a source tree, where it stays
    in the repository's own `vendor/` next to the `wasm/build.py` that produces it.
    """
    here = Path(__file__).resolve()
    installed = here.parents[1] / "vendor" / MODULE_NAME
    checkout = here.parents[3] / "vendor" / MODULE_NAME
    for candidate in (installed, checkout):
        if candidate.is_file():
            return candidate
    raise SscError(
        "snapper-missing",
        f"{MODULE_NAME} is not beside the package or in this checkout's vendor/",
        fix="reinstall ssc, or rebuild the module with: python wasm/build.py",
    )


class Snapper:
    """One instantiation of the module, driving the flat ABI."""

    def __init__(self, path: Path | None = None) -> None:
        engine = Engine()
        self.module = Module.from_file(engine, str(path or module_path()))
        linker = Linker(engine)
        linker.define_wasi()
        self.store = Store(engine)
        self.store.set_wasi(WasiConfig())
        self.exports = linker.instantiate(self.store, self.module).exports(self.store)

        memory = self.exports.get("memory")
        if not isinstance(memory, Memory):
            raise SscError(
                "snapper-abi",
                f"{MODULE_NAME} exports no linear memory",
                fix="rebuild the module with: python wasm/build.py",
            )
        self.memory = memory

    def call(self, name: str, *args: Any) -> Any:
        """Invoke one export by name.

        The lookup is checked rather than assumed: a module swapped for one that does not
        export this ABI should say so, not fail as a `TypeError` from calling `None` — and
        `vendor/` is a binary nobody reads in review, so this is the only place that can
        notice.
        """
        function = self.exports.get(name)
        if not isinstance(function, Func):
            raise SscError(
                "snapper-abi",
                f"{MODULE_NAME} exports no function {name!r}",
                fix="rebuild the module with: python wasm/build.py",
            )
        try:
            return function(self.store, *args)
        except WasmtimeError as trapped:
            # A trap inside the guest is not an `SscError`, and `cli/main.py` catches only
            # those — so without this the command exits as a Python traceback instead of
            # the JSON object every command promises. This is the boundary to foreign
            # code, so it is the place that owes the translation.
            raise SscError(
                "snapper-trapped",
                f"{MODULE_NAME} trapped during {name!r}: {trapped}",
                fix="try a smaller input, or rebuild the module with: python wasm/build.py",
            ) from trapped

    def allocate(self, data: bytes) -> int:
        """Reserve room inside the module for `data` and write it there.

        A null pointer is the ABI's own way of saying no — for an empty length, for a
        length past `isize::MAX`, and for an allocation that simply failed, which a
        several-hundred-megabyte frame under memory pressure is a real way to reach.
        Writing at address zero regardless is not a crash: it lands inside the guest's own
        linear memory and corrupts whatever the linker put there, and the module's next
        `ssc_result_ptr` can then hand back a pointer and length that read as a perfectly
        successful conversion. Silent wrong output is the outcome worth spending a branch
        to avoid.
        """
        if not data:
            return 0
        pointer = int(self.call("ssc_alloc", len(data)))
        if pointer == 0:
            raise SscError(
                "snapper-oom",
                f"the snapper could not reserve {len(data):,} bytes for this frame",
                fix="convert fewer frames at once, or scale the input down first",
            )
        self.memory.write(self.store, data, pointer)
        return pointer

    def _read(self, ptr: int, length: int) -> bytes:
        return bytes(self.memory.read(self.store, ptr, ptr + length))

    def result_len(self) -> int:
        """How many bytes the last call left readable. Zero after a failure."""
        return int(self.call("ssc_result_len"))

    def snap(
        self,
        png: bytes,
        *,
        colors: int = 16,
        pixel_size: float = 0.0,
        palette: str = "",
    ) -> bytes:
        """Return the snapped PNG (R2.1), or raise with the module's own message (R2.6).

        A `pixel_size` of `0.0` means "detect the grid". The module reports failure through
        the ABI rather than trapping, so the instance stays usable afterwards — which is
        what lets one bad frame not take the rest of the set with it.
        """
        encoded = palette.encode()
        in_ptr = self.allocate(png)
        try:
            # Nested rather than side by side: if the palette fails to allocate, the frame
            # it was going to accompany still has to be handed back to the module.
            pal_ptr = self.allocate(encoded)
            try:
                code = self.call(
                    "ssc_snap", in_ptr, len(png), colors, pixel_size, pal_ptr, len(encoded)
                )
                if code != 0:
                    message = self._read(
                        self.call("ssc_error_ptr"), self.call("ssc_error_len")
                    ).decode(errors="replace")
                    raise SscError(
                        "snap-failed",
                        f"the snapper refused this frame: {message}",
                        fix="check --palette and --pixel-size, or that --in is an image",
                    )
                return self._read(self.call("ssc_result_ptr"), self.result_len())
            finally:
                if pal_ptr:
                    self.call("ssc_dealloc", pal_ptr, len(encoded))
        finally:
            if in_ptr:
                self.call("ssc_dealloc", in_ptr, len(png))
