"""`--device`, detection that ignores the installed runtime, and the provider in the cache
key — plan tasks 8.1, 8.3 and 8.4, against `adr:0011`."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from ssc.cli import devices
from ssc.cli.app import main
from ssc.cli.cache import cache_key
from ssc.cli.errors import SscError, UsageError

CPU = devices.PROVIDERS["cpu"]
CUDA = devices.PROVIDERS["cuda"]
DML = devices.PROVIDERS["directml"]
COREML = devices.PROVIDERS["coreml"]


def runner(answers: dict[str, str | None]):  # type: ignore[no-untyped-def]
    """A probe runner answering by the binary a command starts with."""

    def run(command: Sequence[str]) -> str | None:
        return answers.get(command[0])

    return run


def test_auto_takes_the_best_provider_that_is_actually_there() -> None:
    assert devices.resolve("auto", [CPU, CUDA]) == CUDA
    assert devices.resolve("auto", [CPU, DML]) == DML
    assert devices.resolve("auto", [CPU]) == CPU


def test_auto_with_no_runtime_at_all_refuses_with_the_install_command() -> None:
    with pytest.raises(SscError) as raised:
        devices.resolve("auto", [])
    assert raised.value.code == "no-execution-provider"
    assert "[cv]" in (raised.value.fix or "")


def test_a_device_named_explicitly_never_falls_back() -> None:
    """The defect this exists to stop: a caller asks for a GPU and waits on a CPU."""
    with pytest.raises(SscError) as raised:
        devices.resolve("cuda", [CPU])
    assert raised.value.code == "device-unavailable"
    assert "[cv-gpu]" in (raised.value.fix or "")


def test_directml_names_its_own_distribution() -> None:
    """Neither extra carries DirectML — `adr:0011` recorded the gap, and the refusal is
    where a Windows user meets it."""
    with pytest.raises(SscError) as raised:
        devices.resolve("directml", [CPU])
    assert "onnxruntime-directml" in (raised.value.fix or "")


def test_an_explicit_device_that_is_there_is_used() -> None:
    assert devices.resolve("cuda", [CPU, CUDA]) == CUDA
    assert devices.resolve("cpu", [CPU, CUDA]) == CPU


def test_an_unknown_device_is_a_usage_error() -> None:
    with pytest.raises(UsageError) as raised:
        devices.resolve("tpu", [CPU])
    assert raised.value.code == "unknown-device"


def test_detection_reads_nvidia_smi_on_any_platform() -> None:
    detection = devices.detect(
        run=runner({"nvidia-smi": "NVIDIA GeForce RTX 4070\n"}), system="Linux", machine="x86_64"
    )
    assert detection.certain is True
    assert detection.how == "nvidia-smi"
    assert detection.gpus[0].vendor == "nvidia"


def test_detection_falls_to_the_platform_probe_when_nvidia_smi_is_absent() -> None:
    detection = devices.detect(
        run=runner({"nvidia-smi": None, "powershell": "AMD Radeon RX 6600\n"}),
        system="Windows",
        machine="AMD64",
    )
    assert detection.how == "Win32_VideoController"
    assert detection.gpus[0].vendor == "amd"


def test_apple_silicon_is_a_gpu_coreml_can_use() -> None:
    detection = devices.detect(run=runner({"nvidia-smi": None}), system="Darwin", machine="arm64")
    assert detection.gpus[0].vendor == "apple"


def test_a_machine_no_probe_answers_for_is_unknown_not_empty() -> None:
    """ "No GPU detected" and "cannot tell" are different answers (adr:0011)."""
    detection = devices.detect(
        run=runner({"nvidia-smi": None, "lspci": None}), system="Linux", machine="x86_64"
    )
    assert detection.gpus == ()
    assert detection.certain is False


def test_a_probe_that_cannot_run_never_raises() -> None:
    """Detection explains; it is never allowed to gate execution."""
    detection = devices.detect(system="Linux", machine="x86_64")
    assert isinstance(detection, devices.Detection)


def test_a_probe_is_taken_from_path_and_never_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows searches the working directory for a bare command name, so `ssc info` run
    inside a downloaded art pack must not execute the `nvidia-smi` that came with it."""
    on_path = tmp_path / "bin"
    on_path.mkdir()
    (on_path / "nvidia-smi").write_text("", encoding="utf-8")
    (on_path / "nvidia-smi.EXE").write_text("", encoding="utf-8")
    cwd = tmp_path / "art-pack"
    cwd.mkdir()
    (cwd / "nvidia-smi").write_text("", encoding="utf-8")
    (cwd / "nvidia-smi.EXE").write_text("", encoding="utf-8")
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", f"{os.pathsep}{on_path}")
    monkeypatch.setenv("PATHEXT", ".EXE")

    found = devices._binary("nvidia-smi")

    assert found is not None
    assert Path(found).parent == on_path


def test_a_probe_that_is_on_no_path_entry_is_not_run() -> None:
    assert devices._binary("a-binary-that-is-not-installed-anywhere") is None


def test_a_capable_gpu_under_a_cpu_only_install_is_a_hint_carrying_the_command() -> None:
    detection = devices.Detection(
        gpus=(devices.Gpu(name="NVIDIA GeForce RTX 4070", vendor="nvidia"),),
        certain=True,
        how="nvidia-smi",
    )
    hints = devices.hints(detection, [CPU])
    codes = {hint["code"] for hint in hints}
    assert "cuda-unrealised" in codes
    assert all(hint["fix"] for hint in hints)


def test_no_runtime_is_its_own_hint() -> None:
    detection = devices.Detection(gpus=(), certain=True, how="lspci")
    assert devices.hints(detection, [])[0]["code"] == "no-cv-runtime"


def test_a_realised_gpu_produces_no_hint() -> None:
    detection = devices.Detection(
        gpus=(devices.Gpu(name="NVIDIA GeForce RTX 4070", vendor="nvidia"),),
        certain=True,
        how="nvidia-smi",
    )
    assert devices.hints(detection, [CPU, CUDA]) == ()


def test_the_provider_is_part_of_the_cache_key() -> None:
    """A CPU result and a CUDA result are not one entry (task 8.3)."""
    on_cpu = cache_key("tool bgremove", params={}, inputs=["a"], salt=devices.cache_salt(CPU))
    on_cuda = cache_key("tool bgremove", params={}, inputs=["a"], salt=devices.cache_salt(CUDA))
    assert on_cpu != on_cuda


def test_the_same_provider_keys_the_same_entry() -> None:
    first = cache_key("tool bgremove", params={}, inputs=["a"], salt=devices.cache_salt(COREML))
    second = cache_key("tool bgremove", params={}, inputs=["a"], salt=devices.cache_salt(COREML))
    assert first == second


def test_a_provider_reports_the_device_it_answers_to() -> None:
    assert devices.device_of(CUDA) == "cuda"
    assert devices.device_of("SomeOtherProvider") == "SomeOtherProvider"


def test_info_reports_both_lists_and_the_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    detection = devices.Detection(
        gpus=(devices.Gpu(name="NVIDIA GeForce RTX 4070", vendor="nvidia"),),
        certain=True,
        how="nvidia-smi",
    )
    monkeypatch.setattr(devices, "detect", lambda *a, **k: detection)
    monkeypatch.setattr(devices, "usable_providers", lambda: (CPU,))
    monkeypatch.setattr(devices, "runtime_version", lambda: "1.18.0")

    result = CliRunner().invoke(main, ["info", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["gpus"] == [{"name": "NVIDIA GeForce RTX 4070", "vendor": "nvidia"}]
    assert payload["providers"] == [CPU]
    assert payload["hints"][0]["code"] == "cuda-unrealised"
    assert payload["runtime"]["onnxruntime"] == "1.18.0"


def test_info_works_with_neither_extra_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The machine that cannot run a model is the one that has to be told what it takes."""
    monkeypatch.setattr(devices, "usable_providers", lambda: ())
    monkeypatch.setattr(devices, "runtime_version", lambda: None)

    result = CliRunner().invoke(main, ["info", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["providers"] == []
    assert payload["runtime"]["onnxruntime"] is None
    assert "no-cv-runtime" in {hint["code"] for hint in payload["hints"]}


def test_info_device_auto_reports_what_it_chose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(devices, "usable_providers", lambda: (CPU, CUDA))

    asked = ["info", "--device", "auto", "--json"]
    payload = json.loads(CliRunner().invoke(main, asked, catch_exceptions=False).output)

    assert payload["device"] == {"asked": "auto", "provider": CUDA, "resolved": "cuda"}


def test_info_device_named_and_missing_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(devices, "usable_providers", lambda: (CPU,))

    asked = ["info", "--device", "cuda", "--json"]
    result = CliRunner().invoke(main, asked, catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["error"]["code"] == "device-unavailable"
    assert "[cv-gpu]" in payload["error"]["fix"]


def test_info_says_when_it_cannot_tell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        devices, "detect", lambda *a, **k: devices.Detection(gpus=(), certain=False, how="none")
    )
    monkeypatch.setattr(devices, "usable_providers", lambda: (CPU,))

    result = CliRunner().invoke(main, ["info", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert payload["detection"] == {"certain": False, "how": "none"}
    assert "unknown" in payload["summary"]
