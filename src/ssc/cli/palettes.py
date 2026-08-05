"""The project palette and dither — a workspace's look, decided once.

`tool pixelart` takes colours per call; `tool style` reads them from `palette.json`, which
is locked once from a preset and then never re-picked. Dither is the same kind of
decision and lives the same place the rest of the workspace's settings do — in `ssc.yaml`
under `style:` — never as a flag on the call. That is what makes the look a *project*
decision rather than a per-asset one: two assets generated a week apart agree because they
were quantized against the same file with the same dither.

`palette.json` lives at the workspace root and is written through ``atomic.write_new``,
which refuses an existing path — so "locked" is enforced by the write itself, not by a
check a caller could forget. To change the palette you delete the file and lock again;
that is the palette-lock gate (see ``docs/wiki/pages/agent-workflow.md``), not a flag.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, cast

import numpy as np

from ssc.cli import config
from ssc.cli.args import parse_hex
from ssc.cli.atomic import write_new
from ssc.cli.errors import UsageError
from ssc.cli.workspace import Workspace
from ssc.core.pixelart import Dither

#: The one file a workspace's colours hang off, at the workspace root.
PALETTE_FILE = "palette.json"

#: The dither modes a workspace may record under `style:` in `ssc.yaml`. A project
#: decision, not a per-call argument (task 5.2) — two assets generated a week apart agree
#: because the dither is the same, the way the palette is the same.
DITHER_VALUES = ("none", "ordered", "floyd-steinberg")


@dataclass(frozen=True)
class LockedPalette:
    """The colours a workspace has committed to.

    `preset` is informational — which preset was locked — and plays no part in applying
    the palette; the colours are the contract. Dither is a separate workspace decision
    (see :func:`workspace_dither`), not a property of the palette.
    """

    colours: np.ndarray
    preset: str | None


def _shipped() -> dict[str, list[str]]:
    """The preset palettes shipped in ``ssc.data``."""
    text = resources.files("ssc.data").joinpath("palettes.json").read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(text)
    presets: dict[str, list[str]] = data["presets"]
    return presets


def preset_names() -> tuple[str, ...]:
    """The presets a workspace can lock, in shipping order."""
    return tuple(_shipped().keys())


def preset_colours(name: str) -> list[str]:
    """The hex colours of one preset, refusing a name that is not shipped."""
    presets = _shipped()
    if name not in presets:
        raise UsageError(
            "unknown-preset",
            f"{name!r} is not a shipped palette preset",
            fix=f"lock one of: {', '.join(presets)}",
        )
    return list(presets[name])


def lock(path: Path, preset: str) -> list[str]:
    """Write `palette.json` for `preset`, refusing if one is already locked.

    Refusal on an existing path is `write_new`'s own behaviour, and it is the
    mechanism behind "the palette is locked" — a second `--preset` against a
    workspace that already has a palette is a no-op a caller could mistake for
    success, so the write itself rejects it.
    """
    colours = preset_colours(preset)
    document = {"preset": preset, "palette": colours}
    write_new(path, (json.dumps(document, indent=2) + "\n").encode("utf-8"))
    return colours


def read_locked(path: Path) -> LockedPalette:
    """The locked palette at `path`, refusing a missing or malformed file.

    A missing `palette.json` is not an error a `tool style` caller can fix by
    reading the message: it is the state "no palette locked yet", which the
    command turns into the exact lock command to run.
    """
    if not path.is_file():
        raise UsageError(
            "no-palette",
            f"no {PALETTE_FILE} in this workspace",
            fix="lock one first: ssc tool style --preset <pico8|nes|gameboy|sweetie16> "
            "--in <src> --out <out>",
        )
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        colours = [parse_hex(part) for part in data["palette"]]
    except (json.JSONDecodeError, KeyError, TypeError) as broken:
        raise UsageError(
            "invalid-palette",
            f"{path} is not a valid locked palette: {broken}",
            fix="delete it and lock again with ssc tool style --preset <name>",
        ) from broken
    return LockedPalette(
        colours=np.array(colours, dtype=np.uint8),
        preset=data.get("preset"),
    )


def workspace_dither(workspace: Workspace) -> Dither:
    """The dither recorded under ``style:`` in ``ssc.yaml``, defaulting to none.

    Dither is a project decision, recorded in the workspace like `pipeline:` and
    `models:` are — hand-edited in `ssc.yaml`, never a flag on `tool style`. Two assets
    generated a week apart agree because the dither is the same, the way the palette is.
    """
    section = config.document(workspace).get("style")
    if section is None:
        return "none"
    if not isinstance(section, dict):
        raise UsageError(
            "invalid-config",
            "ssc.yaml `style:` must be a map of settings",
            fix="write it as:\n  style:\n    dither: ordered",
        )
    dither = section.get("dither", "none")
    if dither not in DITHER_VALUES:
        raise UsageError(
            "invalid-dither",
            f"style.dither {dither!r} is not one of {', '.join(DITHER_VALUES)}",
            fix="set style.dither to none, ordered or floyd-steinberg in ssc.yaml",
        )
    return cast("Dither", dither)
