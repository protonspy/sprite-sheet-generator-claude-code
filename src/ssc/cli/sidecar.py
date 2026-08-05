"""`asset.yaml` — the authored half of an asset.

`meta.json` records what each file is and where it came from. This is the other half: what a
person decided. A frame rate is not provenance, and putting it in `meta.json` would put a
hand-edited value in the file `ssc clean` reads to decide what to delete. See
`adr:0009-authored-intent-lives-in-a-sidecar`.

Two sections: `playback`, and the per-frame `frames` block — hitboxes, hurtboxes and
markers, one entry per frame of the set. `ssc` carries these values into the index and
never gives them meaning: nothing here invents damage or knockback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
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

#: What the top level may hold. Anything else is refused rather than ignored, because a key
#: ssc silently drops is a value the author believes is being used.
TOP_LEVEL = ("playback", "frames")
PLAYBACK_KEYS = ("fps", "mode", "sections")
FRAME_KEYS = ("hitboxes", "hurtboxes", "markers")


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


@dataclass(frozen=True)
class Box:
    """One authored rectangle on one frame, in pixels within the cell."""

    x: int
    y: int
    width: int
    height: int

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    def as_span(self) -> list[int]:
        """The `[x, y, width, height]` shape the sidecar authors it in."""
        return [self.x, self.y, self.width, self.height]


@dataclass(frozen=True)
class AuthoredFrame:
    """What a person said about one frame: what deals, what receives, what happens.

    `ssc` moves these values and never gives them meaning — a hitbox deals and a hurtbox
    receives by the game's reading, not this tool's.
    """

    hitboxes: tuple[Box, ...] = ()
    hurtboxes: tuple[Box, ...] = ()
    markers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "hitboxes": [box.as_dict() for box in self.hitboxes],
            "hurtboxes": [box.as_dict() for box in self.hurtboxes],
            "markers": list(self.markers),
        }

    def as_authored(self) -> dict[str, Any] | None:
        """The YAML shape this entry was written in, or `None` for a frame with nothing —
        which is what lets a rewritten sidecar say `~` where the author said `~`."""
        entry: dict[str, Any] = {}
        if self.hitboxes:
            entry["hitboxes"] = [box.as_span() for box in self.hitboxes]
        if self.hurtboxes:
            entry["hurtboxes"] = [box.as_span() for box in self.hurtboxes]
        if self.markers:
            entry["markers"] = list(self.markers)
        return entry or None


@dataclass(frozen=True)
class Sidecar:
    """Everything one `asset.yaml` says.

    `frames` is `None` when the author wrote no `frames:` block at all, and a tuple — one
    entry per frame, possibly empty ones — when they did. The difference matters: an absent
    block is nothing to validate, while an authored one must match the set's frame count.
    """

    playback: Playback = field(default_factory=Playback)
    frames: tuple[AuthoredFrame, ...] | None = None


def refuse(where: str, what: str, fix: str) -> SscError:
    """Every refusal from this module names the file and the key at fault (R4.3)."""
    return SscError("invalid-sidecar", f"{where}: {what}", fix=fix)


def parse(raw: bytes, where: str) -> Sidecar:
    """One sidecar, or a refusal naming what is wrong with it (R4.1, R4.3)."""
    try:
        document = yaml.load(raw.decode("utf-8"), Loader=StrictLoader)
    except (yaml.YAMLError, RecursionError, UnicodeDecodeError) as broken:
        raise refuse(where, f"not valid YAML: {broken}", "fix it by hand") from broken

    if document is None:
        return Sidecar()
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

    return Sidecar(
        playback=_playback(document.get("playback"), where),
        frames=_frames(document.get("frames"), where),
    )


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


def _frames(given: Any, where: str) -> tuple[AuthoredFrame, ...] | None:
    """The `frames:` block — a list with one entry per frame, in frame order.

    A list rather than a map keyed by number, so that its length *is* its claim about the
    set: how many frames the author was looking at. Whether that matches the frames that
    exist is `cli/index.py`'s question, because the count is only known there.
    """
    if given is None:
        return None
    if not isinstance(given, list):
        raise refuse(
            where,
            f"frames is a {type(given).__name__}, not a list",
            "write one entry per frame, ~ for a frame with nothing",
        )

    read: list[AuthoredFrame] = []
    for number, entry in enumerate(given):
        label = f"frames[{number}]"
        if entry is None:
            read.append(AuthoredFrame())
            continue
        if not isinstance(entry, dict):
            raise refuse(
                where,
                f"{label} is a {type(entry).__name__}, not a map",
                f"a frame entry holds: {', '.join(FRAME_KEYS)}",
            )
        unknown = [key for key in entry if key not in FRAME_KEYS]
        if unknown:
            raise refuse(
                where,
                f"{label} declares {', '.join(str(key) for key in sorted(map(str, unknown)))}",
                f"a frame entry holds: {', '.join(FRAME_KEYS)}",
            )
        read.append(
            AuthoredFrame(
                hitboxes=_boxes(entry.get("hitboxes"), f"{label}.hitboxes", where),
                hurtboxes=_boxes(entry.get("hurtboxes"), f"{label}.hurtboxes", where),
                markers=_markers(entry.get("markers"), f"{label}.markers", where),
            )
        )
    return tuple(read)


def _boxes(given: Any, label: str, where: str) -> tuple[Box, ...]:
    if given is None:
        return ()
    if not isinstance(given, list):
        raise refuse(
            where,
            f"{label} is a {type(given).__name__}, not a list",
            "write each box as [x, y, width, height]",
        )

    read: list[Box] = []
    for number, span in enumerate(given):
        if (
            not isinstance(span, list)
            or len(span) != 4
            or any(isinstance(part, bool) or not isinstance(part, int) for part in span)
        ):
            raise refuse(
                where,
                f"{label}[{number}] is {span!r}, not four whole numbers",
                "write it as [x, y, width, height], in pixels within the cell",
            )
        x, y, width, height = span
        if x < 0 or y < 0 or width < 1 or height < 1:
            raise refuse(
                where,
                f"{label}[{number}] is [{x}, {y}, {width}, {height}]",
                "x and y are 0 or more, and the box is at least a pixel each way",
            )
        read.append(Box(x=x, y=y, width=width, height=height))
    return tuple(read)


def _markers(given: Any, label: str, where: str) -> tuple[str, ...]:
    """Marker names, in the order the author wrote them — an order on one frame carries no
    meaning, so there is nothing to sort by."""
    if given is None:
        return ()
    if not isinstance(given, list) or any(not isinstance(name, str) or not name for name in given):
        raise refuse(
            where,
            f"{label} is {given!r}, not a list of names",
            "write markers: [footstep, spawn]",
        )
    return tuple(given)


def frame_rate(playback: Playback, kind_fps: int) -> int:
    """What this set actually plays at: the author's number, or its kind's (R4.2).

    A function rather than a default on `Playback` so that the fallback happens once, where
    the kind is known, instead of at each of the four emitters — which is how two of them end
    up disagreeing about what an undeclared frame rate means.
    """
    return kind_fps if playback.fps is None else playback.fps


def carried_document(asset_dir: Directory, *, kept: list[int], total: int) -> bytes | None:
    """The sidecar as it should read once curation keeps only `kept` — or `None`.

    An authored entry belongs to the frame it was written on. Curation shortens the set, and
    a list left at its old length would land every later entry on the wrong frame — a hitbox
    that deals on the wrong pose. Carrying means keeping exactly the kept frames' entries, in
    the kept order, by editing the parsed document rather than the model, so the author's own
    values survive as written.

    Computed before anything is dropped and written by the caller after, so a refusal here —
    a block whose length does not match the set being curated — costs nothing on disk.
    Lining a mismatched block up with the frames would be a guess about which entries the
    author meant. A missing sidecar or an absent block is nothing to carry.
    """
    where = str(asset_dir.path / SIDECAR_NAME)
    try:
        raw = asset_dir.read(SIDECAR_NAME, max_bytes=MAX_SIDECAR_BYTES)
    except FileNotFoundError:
        return None
    parsed = parse(raw, where)
    if parsed.frames is None:
        return None
    if len(parsed.frames) != total:
        raise refuse(
            where,
            f"authors {len(parsed.frames)} frame entr"
            f"{'y' if len(parsed.frames) == 1 else 'ies'}, and the set being curated "
            f"has {total}",
            "one entry per frame of the set; fix the sidecar before curating",
        )

    document = yaml.load(raw.decode("utf-8"), Loader=StrictLoader)
    authored = document["frames"]
    document["frames"] = [authored[number] for number in kept]
    return yaml.safe_dump(document, sort_keys=False, default_flow_style=None).encode("utf-8")


def transformed_document(
    asset_dir: Directory,
    *,
    total: int,
    move: Callable[[tuple[int, int, int, int]], tuple[int, int, int, int] | None],
) -> bytes | None:
    """The sidecar with every authored box moved by the transform its frames just took —
    or `None` where there is nothing to move (plans/ssc-completion.md 7.8).

    A mirrored frame with an unmirrored hurt box takes damage on the wrong side, so a
    transform that lands in an asset moves the asset's boxes with it. Markers name moments,
    not places, so they ride their frame untouched. `move` returning `None` is a box the
    transform dropped with the pixels it covered — clipped off the canvas by an offset, or
    outside a trim's crop — and it leaves the document the way an author's empty entry does.

    Computed before the frames are written and applied by the caller after, like
    `carried_document`: a block that cannot be lined up refuses the whole transform, and a
    refusal costs nothing on disk.
    """
    where = str(asset_dir.path / SIDECAR_NAME)
    try:
        raw = asset_dir.read(SIDECAR_NAME, max_bytes=MAX_SIDECAR_BYTES)
    except FileNotFoundError:
        return None
    parsed = parse(raw, where)
    if parsed.frames is None:
        return None
    if len(parsed.frames) != total:
        raise refuse(
            where,
            f"authors {len(parsed.frames)} frame entr"
            f"{'y' if len(parsed.frames) == 1 else 'ies'}, and the set being transformed "
            f"has {total}",
            "one entry per frame of the set; fix the sidecar before transforming",
        )

    document = yaml.load(raw.decode("utf-8"), Loader=StrictLoader)
    rewritten: list[Any] = []
    for entry in document["frames"]:
        if not isinstance(entry, dict):
            rewritten.append(entry)
            continue
        for key in ("hitboxes", "hurtboxes"):
            if key in entry:
                moved = [move((span[0], span[1], span[2], span[3])) for span in entry[key]]
                entry[key] = [list(span) for span in moved if span is not None]
                if not entry[key]:
                    del entry[key]
        rewritten.append(entry or None)
    document["frames"] = rewritten
    return yaml.safe_dump(document, sort_keys=False, default_flow_style=None).encode("utf-8")


def load(asset_dir: Directory) -> Sidecar:
    """An asset's sidecar, read through the held directory, empty where there is none.

    Through the binding for the reason `meta.load` documents: a read by path resolved after a
    check is a read of something that may no longer be what was checked.
    """
    try:
        raw = asset_dir.read(SIDECAR_NAME, max_bytes=MAX_SIDECAR_BYTES)
    except FileNotFoundError:
        return Sidecar()
    return parse(raw, str(asset_dir.path / SIDECAR_NAME))
