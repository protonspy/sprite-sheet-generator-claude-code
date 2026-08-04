"""`asset.yaml` — the authored half of an asset.

`meta.json` records what each file is and where it came from. This is the other half: what a
person decided. A frame rate is not provenance, and putting it in `meta.json` would put a
hand-edited value in the file `ssc clean` reads to decide what to delete. See
`adr:0009-authored-intent-lives-in-a-sidecar`.

Playback is all that is here today. `specs/frame-metadata/` adds per-frame boxes and markers
to the same file, which is why the top level is a map of sections rather than the playback
keys themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml

from ssc.cli.atomic import Directory
from ssc.cli.config import StrictLoader
from ssc.cli.errors import SscError

SIDECAR_NAME = "asset.yaml"

#: The three an engine can be told about. `loop` is what a set with nothing declared does.
PLAYBACK_MODES = ("loop", "ping-pong", "reverse")
DEFAULT_MODE = "loop"

#: A sidecar is a few dozen lines of authored intent, like `ssc.yaml` — and, like it, a file
#: an agent may write. The ceiling is on the read rather than on the parse for the same
#: reason `config.py` gives.
MAX_SIDECAR_BYTES = 1 << 20

#: Frames per second. The ceiling is nothing an animation needs and everything a
#: divide-by-frame-rate downstream would rather not be handed. `kinds.py` imports both
#: rather than retyping them: a kind profile carries a frame rate too, and a range that must
#: agree between two modules is the defect class this project keeps hitting.
MAX_FPS = 240
DEFAULT_FPS = 12

#: What the top level may hold. `frames` is claimed by `specs/frame-metadata/` and refused
#: until it lands, because a key ssc ignores is a value the author believes is being used.
TOP_LEVEL = ("playback",)
PLAYBACK_KEYS = ("fps", "mode", "sections")


@dataclass(frozen=True)
class Section:
    """A named range of one animation, both ends inclusive.

    An attack's windup, hit and recovery are three ranges of one set rather than three sets,
    so the range is what is authored and the frames it resolves to are worked out against the
    set that actually exists — see `resolve` in `cli/index.py`.
    """

    name: str
    first: int
    last: int

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "first": self.first, "last": self.last}


@dataclass(frozen=True)
class Playback:
    """How a set is meant to play.

    `fps` is `None` rather than a number when nothing declared one: the fallback is the kind's
    profile (R4.2), and a default filled in here would hide that the author said nothing.
    """

    fps: int | None = None
    mode: str = DEFAULT_MODE
    sections: tuple[Section, ...] = ()


def refuse(where: str, what: str, fix: str) -> SscError:
    """Every refusal from this module names the file and the key at fault (R4.3)."""
    return SscError("invalid-sidecar", f"{where}: {what}", fix=fix)


def parse(raw: bytes, where: str) -> Playback:
    """One sidecar's playback, or a refusal naming what is wrong with it (R4.1, R4.3)."""
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=StrictLoader)
    except (yaml.YAMLError, RecursionError, UnicodeDecodeError) as broken:
        raise refuse(where, f"not valid YAML: {broken}", "fix it by hand") from broken

    if document is None:
        return Playback()
    if not isinstance(document, dict):
        raise refuse(
            where,
            f"is a {type(document).__name__}, not a map",
            f"the file is a map of {', '.join(TOP_LEVEL)}",
        )

    unknown = [key for key in document if key not in TOP_LEVEL]
    if unknown:
        raise refuse(
            where,
            f"declares {', '.join(str(key) for key in sorted(map(str, unknown)))}",
            f"a sidecar holds: {', '.join(TOP_LEVEL)}",
        )

    return _playback(document.get("playback"), where)


def _playback(given: Any, where: str) -> Playback:
    if given is None:
        return Playback()
    if not isinstance(given, dict):
        raise refuse(where, f"playback is a {type(given).__name__}, not a map", "write it as a map")

    unknown = [key for key in given if key not in PLAYBACK_KEYS]
    if unknown:
        raise refuse(
            where,
            f"playback declares {', '.join(str(key) for key in sorted(map(str, unknown)))}",
            f"playback holds: {', '.join(PLAYBACK_KEYS)}",
        )

    return Playback(
        fps=_fps(given.get("fps"), where),
        mode=_mode(given.get("mode"), where),
        sections=_sections(given.get("sections"), where),
    )


def _fps(given: Any, where: str) -> int | None:
    if given is None:
        return None
    # `bool` is an `int` in Python and `fps: true` is a mistake, not a frame rate of one.
    if isinstance(given, bool) or not isinstance(given, int):
        raise refuse(where, f"playback.fps is {given!r}, not a whole number", "write fps: 12")
    if given < 1 or given > MAX_FPS:
        raise refuse(where, f"playback.fps is {given}, outside 1 to {MAX_FPS}", "write fps: 12")
    return given


def _mode(given: Any, where: str) -> str:
    if given is None:
        return DEFAULT_MODE
    if given not in PLAYBACK_MODES:
        raise refuse(
            where,
            f"playback.mode is {given!r}",
            f"one of: {', '.join(PLAYBACK_MODES)}",
        )
    return str(given)


def _sections(given: Any, where: str) -> tuple[Section, ...]:
    """`name: [first, last]`, both ends inclusive and neither checked against a frame count
    here — that is `cli/index.py`'s, because it is the only place the count is known."""
    if given is None:
        return ()
    if not isinstance(given, dict):
        raise refuse(
            where,
            f"playback.sections is a {type(given).__name__}, not a map",
            "write each section as name: [first, last]",
        )

    read: list[Section] = []
    for name, span in given.items():
        label = f"playback.sections.{name}"
        if (
            not isinstance(span, list)
            or len(span) != 2
            or any(isinstance(end, bool) or not isinstance(end, int) for end in span)
        ):
            raise refuse(
                where,
                f"{label} is {span!r}, not a pair of frame numbers",
                "write it as name: [first, last], both inclusive",
            )
        first, last = span
        if first < 0 or last < first:
            raise refuse(
                where,
                f"{label} runs from {first} to {last}",
                "the first frame is 0 or more, and the last is not before the first",
            )
        read.append(Section(name=str(name), first=first, last=last))
    # Sorted so the index is the same whatever order the author wrote them in (R1.8).
    return tuple(sorted(read, key=lambda section: section.name))


def frame_rate(playback: Playback, kind_fps: int) -> int:
    """What this set actually plays at: the author's number, or its kind's (R4.2).

    A function rather than a default on `Playback` so that the fallback happens once, where
    the kind is known, instead of at each of the four emitters — which is how two of them end
    up disagreeing about what an undeclared frame rate means.
    """
    return kind_fps if playback.fps is None else playback.fps


def load(asset_dir: Directory) -> Playback:
    """An asset's playback, read through the held directory, empty where there is no sidecar.

    Through the binding for the reason `meta.load` documents: a read by path resolved after a
    check is a read of something that may no longer be what was checked.
    """
    try:
        raw = asset_dir.read(SIDECAR_NAME, max_bytes=MAX_SIDECAR_BYTES)
    except FileNotFoundError:
        return Playback()
    return parse(raw, str(asset_dir.path / SIDECAR_NAME))
