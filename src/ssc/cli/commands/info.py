"""`ssc info` — what this machine has, and what this install can use.

Two lists and the gap between them. It works with neither extra installed, and that is the
point: the machine that cannot run a model is the one that has to be told what it would
take. See `ssc.cli.devices` and `adr:0011`.
"""

from __future__ import annotations

from typing import Any

import click

from ssc.cli import devices
from ssc.cli.main import ssc_command
from ssc.cli.output import Result


@ssc_command("info", help="The GPUs this machine has, and the providers this install can use.")
@click.option(
    "--device",
    type=click.Choice(devices.DEVICES),
    default=None,
    help="Report the provider this device would run on, refusing where it is not usable.",
)
def info(device: str | None, *, dry_run: bool) -> Result:
    detection = devices.detect()
    providers = devices.usable_providers()
    found = devices.hints(detection, providers)

    payload: dict[str, Any] = {
        "gpus": [{"name": gpu.name, "vendor": gpu.vendor} for gpu in detection.gpus],
        "detection": {"certain": detection.certain, "how": detection.how},
        "providers": list(providers),
        "runtime": {"onnxruntime": devices.runtime_version()},
        "devices": list(devices.DEVICES),
        "hints": [dict(hint) for hint in found],
    }
    if device is not None:
        # Resolving here is what makes `--device` testable before a model-backed command
        # exists to carry it: the refusal a caller would meet at `bgremove` is the refusal
        # they meet here, from the same function.
        provider = devices.resolve(device, providers)
        payload["device"] = {
            "asked": device,
            "provider": provider,
            "resolved": devices.device_of(provider),
        }

    if detection.certain:
        seen = f"{len(detection.gpus)} GPU{'' if len(detection.gpus) == 1 else 's'}"
    else:
        seen = "GPUs unknown"
    usable = f"{len(providers)} provider{'' if len(providers) == 1 else 's'} usable"
    return Result("info", f"{seen}, {usable}", payload, dry_run=dry_run)
