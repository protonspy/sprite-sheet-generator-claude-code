"""Where a model runs — the device asked for, the provider that answers, and the GPUs the
machine has whether or not this install can use them.

Two questions that look like one and are not, which is the whole of
``adr:0011-two-extras-for-onnxruntime-and-detection-that-ignores-them``:

- **What can this install run?** `onnxruntime` answers, and a CPU-only install can only
  ever answer `CPUExecutionProvider`.
- **What does this machine have?** The machine answers, through probes that do not import
  the runtime at all. The install that most needs to be told about a GPU is precisely the
  one that cannot see it, so detection never consults the runtime.

`ssc info` reports both, side by side and never conflated, and the gap between them is a
hint carrying the exact install command. Nothing here gates execution: the runtime decides
what runs, detection only explains.
"""

from __future__ import annotations

import os
import platform
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ssc.cli.errors import SscError, UsageError

#: What `--device` accepts. `auto` is the default everywhere: it takes the best provider
#: actually usable, and every other value is a promise the caller wants kept or refused.
DEVICES = ("auto", "cpu", "cuda", "directml", "coreml")

#: The execution provider each device names. One provider per device, because a device that
#: could be served by two providers is a silent fallback wearing a different hat.
PROVIDERS = {
    "cpu": "CPUExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "directml": "DmlExecutionProvider",
    "coreml": "CoreMLExecutionProvider",
}

#: What `auto` prefers, fastest first. CPU is last and always present, so `auto` resolves on
#: any install that has a runtime at all.
PREFERENCE = ("cuda", "directml", "coreml", "cpu")

#: How to get each provider. `directml` is the gap `adr:0011` recorded rather than left to
#: be found by a Windows user: it ships in a third distribution that neither extra installs,
#: so `ssc` accepts the device and names the package instead of pretending an extra covers
#: it. See `docs/stack.md`.
INSTALL = {
    "cpu": "uv pip install 'sprite-sheet-generator-claude-code[cv]'",
    "cuda": "uv pip install 'sprite-sheet-generator-claude-code[cv-gpu]'",
    "directml": "uv pip install onnxruntime-directml",
    "coreml": "uv pip install 'sprite-sheet-generator-claude-code[cv]'",
}

#: A vendor per marker in a device name, so "NVIDIA GeForce RTX 4070" reports `nvidia`
#: rather than the marketing string a hint would have to parse.
_VENDORS = (
    ("nvidia", "nvidia"),
    ("geforce", "nvidia"),
    ("quadro", "nvidia"),
    ("tesla", "nvidia"),
    ("amd", "amd"),
    ("radeon", "amd"),
    ("intel", "intel"),
    ("arc", "intel"),
    ("apple", "apple"),
)

Runner = Callable[[Sequence[str]], "str | None"]


@dataclass(frozen=True)
class Gpu:
    """One graphics device the machine reports, and the vendor its name gives away."""

    name: str
    vendor: str


@dataclass(frozen=True)
class Detection:
    """What the machine said, and how much of it to believe.

    `certain` is the distinction `adr:0011` insists on: "no GPU detected" and "cannot tell"
    are different answers. A probe that could not run leaves `certain` false, and a hint
    built on it says so rather than asserting a machine has nothing.
    """

    gpus: tuple[Gpu, ...]
    certain: bool
    how: str


def _binary(name: str) -> str | None:
    """`name` as an absolute path from `PATH`, or `None` where nothing on it matches.

    `shutil.which` is not used: on Windows it searches the current directory first, which
    is the search this exists to avoid. Empty `PATH` entries mean "the current directory"
    and are dropped for the same reason.
    """
    extensions = [""]
    if platform.system() == "Windows":
        extensions = [suffix for suffix in os.environ.get("PATHEXT", ".EXE").split(os.pathsep)]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry.strip():
            continue
        for extension in extensions:
            candidate = Path(entry) / f"{name}{extension}"
            if candidate.is_file():
                return str(candidate)
    return None


def _run(command: Sequence[str]) -> str | None:
    """A probe's output, or `None` where the probe could not run.

    Detection is allowed to be uncertain and is never allowed to fail: a missing binary, a
    non-zero exit and a machine that takes too long to answer are all "cannot tell".

    The binary is resolved to an absolute path off `PATH` first, with the working directory
    deliberately excluded — Windows searches the current directory for a bare command name,
    so `ssc info` run inside a downloaded art pack would otherwise execute an
    `nvidia-smi.exe` that came with it. A probe nothing on `PATH` answers is "cannot tell",
    which is a state this function already has.
    """
    resolved = _binary(command[0])
    if resolved is None:
        return None
    try:
        finished = subprocess.run(
            [resolved, *list(command)[1:]],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            # The probe runs from its own directory rather than inheriting ours, for the
            # second half of the same defect: Windows resolves a DLL against the process's
            # working directory, so a probe started inside an untrusted directory can load
            # a DLL out of it even when the executable itself came from PATH.
            cwd=str(Path(resolved).parent),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if finished.returncode != 0:
        return None
    return finished.stdout


def vendor_of(name: str) -> str:
    """The vendor a device name gives away, or `unknown`."""
    lowered = name.lower()
    for marker, vendor in _VENDORS:
        if marker in lowered:
            return vendor
    return "unknown"


def _from_lines(text: str) -> tuple[Gpu, ...]:
    return tuple(
        Gpu(name=line.strip(), vendor=vendor_of(line))
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("Name")
    )


def detect(run: Runner = _run, system: str | None = None, machine: str | None = None) -> Detection:
    """The GPUs physically present, without importing the runtime.

    `nvidia-smi` first on every platform, because it is the one probe that names a CUDA
    device the same way everywhere. Then the platform's own: `Win32_VideoController` on
    Windows, which sees AMD and Intel too; the architecture on macOS, where an Apple
    Silicon machine always has a GPU CoreML can use; `lspci` on Linux. A machine where none
    of them answers is `certain=False` — unknown, not empty.
    """
    system = system or platform.system()
    machine = machine or platform.machine()

    nvidia = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if nvidia is not None and nvidia.strip():
        return Detection(gpus=_from_lines(nvidia), certain=True, how="nvidia-smi")

    if system == "Windows":
        listed = run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
            ]
        )
        if listed is not None:
            return Detection(gpus=_from_lines(listed), certain=True, how="Win32_VideoController")
        return Detection(gpus=(), certain=False, how="none")

    if system == "Darwin":
        # Every Apple Silicon Mac has a GPU CoreML can use, and the architecture says so
        # without shelling out to `system_profiler`, which is slow and json-shaped.
        if machine == "arm64":
            return Detection(
                gpus=(Gpu(name="Apple Silicon GPU", vendor="apple"),),
                certain=True,
                how="platform.machine",
            )
        return Detection(gpus=(), certain=False, how="none")

    listed = run(["lspci"])
    if listed is not None:
        found = tuple(
            Gpu(name=line.split(": ", 1)[-1].strip(), vendor=vendor_of(line))
            for line in listed.splitlines()
            if "VGA compatible controller" in line or "3D controller" in line
        )
        return Detection(gpus=found, certain=True, how="lspci")
    return Detection(gpus=(), certain=False, how="none")


def _runtime() -> Any | None:
    """The `onnxruntime` module, or `None` where neither extra is installed.

    Imported here rather than at module scope so `ssc` runs, and `ssc info` reports, on an
    install with no runtime at all — which is the install that most needs the report.
    """
    try:
        import onnxruntime  # type: ignore[import-not-found]
    except ImportError:
        return None
    return onnxruntime


def usable_providers() -> tuple[str, ...]:
    """The execution providers this install can actually use, empty where no `onnxruntime`
    is installed at all."""
    runtime = _runtime()
    if runtime is None:
        return ()
    providers: Any = runtime.get_available_providers()
    return tuple(str(provider) for provider in providers)


def runtime_version() -> str | None:
    """The installed `onnxruntime` version, or `None` where there is none."""
    runtime = _runtime()
    return None if runtime is None else str(runtime.__version__)


def device_of(provider: str) -> str:
    """The device name a provider answers to, for reporting what `auto` chose."""
    for device, named in PROVIDERS.items():
        if named == provider:
            return device
    return provider


def resolve(device: str, providers: Sequence[str] | None = None) -> str:
    """The execution provider `device` gets, or a refusal naming what to install.

    **A device named explicitly never falls back.** `--device cuda` on a CPU-only install
    fails and says which package closes the gap; returning `CPUExecutionProvider` instead
    would be a caller who asked for a GPU quietly waiting thirty times as long. `auto` is
    the only value that chooses, and it chooses among providers that are actually there.
    """
    if device not in DEVICES:
        raise UsageError(
            "unknown-device",
            f"{device!r} is not a device ssc runs on",
            fix=f"use one of: {', '.join(DEVICES)}",
        )
    available = tuple(providers) if providers is not None else usable_providers()

    if device == "auto":
        for candidate in PREFERENCE:
            if PROVIDERS[candidate] in available:
                return PROVIDERS[candidate]
        raise SscError(
            "no-execution-provider",
            "no onnxruntime is installed, so there is no provider to run a model on",
            fix=INSTALL["cpu"],
        )

    provider = PROVIDERS[device]
    if provider not in available:
        raise SscError(
            "device-unavailable",
            f"--device {device} needs {provider}, which this install cannot use"
            f" (usable: {', '.join(available) or 'none'})",
            fix=INSTALL[device],
        )
    return provider


def cache_salt(provider: str) -> dict[str, str]:
    """What a provider adds to a cache key.

    Two providers on the same input can differ in the last bit, so a CPU result and a CUDA
    result are not one entry — `cache_key` folds this through its `salt` argument. The key
    is spelled out rather than passed as a bare string so a cache miss can report which
    provider it was keyed on, which is what stops the re-run after switching extras reading
    as a broken cache.
    """
    return {"execution_provider": provider}


def hints(detection: Detection, providers: Sequence[str]) -> tuple[dict[str, str], ...]:
    """The gap between what the machine has and what this install can use.

    A hint, never a warning: nothing is wrong, something is merely unrealised, and a
    command that is working must not print a failure. Each carries the exact install
    command, because the answer to "your GPU is idle" is a line to paste.
    """
    found: list[dict[str, str]] = []
    if not providers:
        found.append(
            {
                "code": "no-cv-runtime",
                "message": "no onnxruntime is installed, so no model can run locally",
                "fix": INSTALL["cpu"],
            }
        )
    vendors = {gpu.vendor for gpu in detection.gpus}
    if "nvidia" in vendors and PROVIDERS["cuda"] not in providers:
        found.append(
            {
                "code": "cuda-unrealised",
                "message": "an NVIDIA GPU is present and CUDAExecutionProvider is not usable",
                "fix": INSTALL["cuda"],
            }
        )
    if (
        platform.system() == "Windows"
        and vendors & {"amd", "intel"}
        and PROVIDERS["directml"] not in providers
    ):
        found.append(
            {
                "code": "directml-unrealised",
                "message": "a DirectML-capable GPU is present and DmlExecutionProvider "
                "is not usable",
                "fix": INSTALL["directml"],
            }
        )
    if "apple" in vendors and PROVIDERS["coreml"] not in providers:
        found.append(
            {
                "code": "coreml-unrealised",
                "message": "an Apple GPU is present and CoreMLExecutionProvider is not usable",
                "fix": INSTALL["coreml"],
            }
        )
    return tuple(found)
