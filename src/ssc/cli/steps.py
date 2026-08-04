"""The commands a sweep can vary and a pipeline can run, as data.

One table, two readings. `specs/sweep-and-review/` varies a parameter across a range;
`specs/gates-and-resume/`'s `ssc run` fixes the parameters and runs the step once. Two
tables would let the parameter you swept stop being the parameter the pipeline runs, which
is the failure the whole shape of this module exists to prevent.

**Everything here is free.** The registry holds `tool` commands and nothing else, so a
pipeline step naming a `gen` verb finds no entry — which is what makes
`specs/gates-and-resume/` R4.9 a property of this table rather than a check somebody has to
remember to write.

The transforms are the same code the commands run, not a copy of it. `commands/convert.py`
imports them from here; a sweep whose variants did not match what the command would produce
is worse than no sweep, because the point of a sweep is to choose a parameter you then pass
to that command.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ssc.cli.args import parse_hex
from ssc.cli.errors import SscError, UsageError
from ssc.cli.names import check_name
from ssc.core.bgremove import PRESETS, BgRemoveParams, remove
from ssc.core.pixelart import (
    PaletteParams,
    build_palette,
    clean_clusters,
    map_to_palette,
    outline,
)

#: A colour budget outside this is not a budget. The floor is 2 because one colour is not an
#: image, and the ceiling is the largest indexed palette a PNG can carry.
MIN_COLORS, MAX_COLORS = 2, 256

#: The distance from black to white in RGB. A tolerance at it keys every pixel of every
#: frame, which is not a background removal but an erasure, so it is the ceiling.
MAX_TOLERANCE = 442

#: `cv2.erode` costs one pass per iteration *regardless of image size*, so this is the one
#: dial whose cost a caller sets independently of the input: a 1x1 PNG and a large enough
#: number runs for hours. A trim wider than the largest sprite anyone packs has removed the
#: whole silhouette long before it gets here.
MAX_TRIM = 512

#: `--despeckle` and `--min-cluster` cost one pass over the image whatever the number is, so
#: neither needs a ceiling for cost. This one is here so a swept value stays a number rather
#: than becoming an overflow inside the label pass.
MAX_CLUSTER = 1 << 20


def parse_key(value: str) -> tuple[int, int, int]:
    """A preset name or a hex colour.

    Presets are named rather than remembered: nobody should have to recall that green screen
    is `00b140` in order to take a background out.
    """
    if value.lower() in PRESETS:
        return PRESETS[value.lower()]
    try:
        return parse_hex(value)
    except UsageError as refused:
        raise UsageError(
            "invalid-chroma",
            f"{value!r} is neither a preset nor a 6-digit hex colour",
            fix=f"use one of {', '.join(sorted(PRESETS))}, or write it as rrggbb",
        ) from refused


def whole(low: int, high: int) -> Callable[[str], int]:
    """A parameter that is a whole number inside a bound (R1.7).

    The bound is carried by the parameter rather than checked inside the transform, because
    a sweep has to refuse *before running anything*: discovering at variant 11 of 12 that a
    value was out of range has already spent the eleven.
    """

    def read(text: str) -> int:
        try:
            value = int(text)
        except ValueError:
            raise UsageError(
                "invalid-value",
                f"{text!r} is not a whole number",
                fix=f"pass a whole number between {low} and {high}",
            ) from None
        if not low <= value <= high:
            raise UsageError(
                "invalid-value",
                f"{value} is outside {low}..{high}",
                fix=f"pass a whole number between {low} and {high}",
            )
        return value

    return read


def one_of(options: Sequence[str]) -> Callable[[str], str]:
    def read(text: str) -> str:
        if text not in options:
            raise UsageError(
                "invalid-value",
                f"{text!r} is not one of {', '.join(options)}",
                fix=f"use one of {', '.join(options)}",
            )
        return text

    return read


def yes_or_no(text: str) -> bool:
    if text not in ("true", "false"):
        raise UsageError(
            "invalid-value",
            f"{text!r} is not true or false",
            fix="write true or false",
        )
    return text == "true"


@dataclass(frozen=True)
class Outcome:
    """What running one step produced: the frames, and what it measured doing it."""

    frames: list[np.ndarray]
    measurement: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Runnable:
    """One command the registry can run, and the parameters it takes."""

    name: str
    parameters: dict[str, Callable[[str], Any]]
    run: Callable[[list[np.ndarray], dict[str, Any]], Outcome]

    def read(self, given: dict[str, str]) -> dict[str, Any]:
        """Parse and bound-check every value, refusing an unknown name (R1.6, R1.7)."""
        parsed: dict[str, Any] = {}
        for name, text in given.items():
            reader = self.parameters.get(name)
            if reader is None:
                raise UsageError(
                    "unknown-parameter",
                    f"{self.name} takes no parameter {name!r}",
                    fix=f"{self.name} takes: {', '.join(sorted(self.parameters))}",
                )
            parsed[name] = reader(text)
        return parsed


def pixelart_frames(images: list[np.ndarray], given: dict[str, Any]) -> Outcome:
    """`tool pixelart`'s per-frame work, over a whole set.

    One palette, computed from every frame at once. That is the whole reason this takes a
    set rather than an image: quantizing frame by frame is what produces `flicker`.
    """
    colors = given.get("colors", 16)
    fixed = given.get("palette", ())
    dither = given.get("dither", "none")
    min_cluster = given.get("min_cluster", 0)
    ring = given.get("outline")

    palette = build_palette(images, PaletteParams(colors, fixed))
    converted = []
    for image in images:
        made = map_to_palette(image, palette, dither)
        if min_cluster > 1:
            made = clean_clusters(made, min_cluster)
        if ring is not None:
            made = outline(made, ring)
        converted.append(made)
    return Outcome(
        frames=converted,
        measurement={
            "palette": [f"{r:02x}{g:02x}{b:02x}" for r, g, b in palette],
            "dither": dither,
        },
    )


def bgremove_frames(images: list[np.ndarray], given: dict[str, Any]) -> Outcome:
    """`tool bgremove`'s per-frame work, over a whole set."""
    params = BgRemoveParams(
        key=given.get("chroma", PRESETS["green"]),
        tolerance=given.get("tol", 60),
        mode=given.get("mode", "flood"),
        edge_pass=given.get("edge_pass", False),
        edge_trim=given.get("edge_trim", 0),
        despeckle=given.get("despeckle", 0),
    )
    keyed = []
    transparent = opaque = 0
    for image in images:
        made, measured = remove(image, params)
        transparent += measured["transparent_px"]
        opaque += measured["opaque_px"]
        keyed.append(made)
    return Outcome(
        frames=keyed,
        measurement={
            "transparent_px": transparent,
            "opaque_px": opaque,
            "mode": params.mode,
        },
    )


def _palette(text: str) -> tuple[tuple[int, int, int], ...]:
    return tuple(parse_hex(part) for part in text.split(",")) if text else ()


#: What a sweep may vary and a pipeline may run. A parameter absent from a command's map is
#: a parameter that command does not take — R1.6's refusal is this dictionary's `get`
#: returning `None`, not a list maintained somewhere else.
REGISTRY: dict[str, Runnable] = {
    "pixelart": Runnable(
        name="pixelart",
        parameters={
            "colors": whole(MIN_COLORS, MAX_COLORS),
            "dither": one_of(("none", "ordered", "floyd-steinberg")),
            "min_cluster": whole(0, MAX_CLUSTER),
            "palette": _palette,
            "outline": parse_hex,
        },
        run=pixelart_frames,
    ),
    "bgremove": Runnable(
        name="bgremove",
        parameters={
            "tol": whole(0, MAX_TOLERANCE),
            "mode": one_of(("flood", "global")),
            "edge_pass": yes_or_no,
            "edge_trim": whole(0, MAX_TRIM),
            "despeckle": whole(0, MAX_CLUSTER),
            "chroma": parse_key,
        },
        run=bgremove_frames,
    ),
}


def runnable(name: str) -> Runnable:
    """The command by that name, or a refusal naming the ones there are (R1.5)."""
    found = REGISTRY.get(name)
    if found is None:
        raise UsageError(
            "unknown-command",
            f"{name!r} is not a command that can be swept or run as a step",
            fix=f"one of: {', '.join(sorted(REGISTRY))}",
        )
    return found


# ---------------------------------------------------------------------------------------
# The pipeline. `specs/gates-and-resume/` R4.1, R4.7, R4.8, R4.9.
# ---------------------------------------------------------------------------------------

#: What a `gen` step would be. Named so R4.9 can refuse with the reason rather than with
#: "unknown command", which is true but tells a caller nothing about why.
PAID = ("gen", "gen image", "gen video", "gen expand", "gen bgremove")


def as_text(value: Any) -> str:
    """A YAML scalar in the spelling the registry's parsers expect.

    `pipeline:` is hand-written YAML, so `tol: 60` arrives as an int and `edge_pass: true`
    as a bool, while `--vary` delivers the same values as strings. One parser per parameter
    means one spelling, so the YAML side converts rather than the parsers growing a second
    accepted type each.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


@dataclass(frozen=True)
class Step:
    """One declared step of a workspace's pipeline."""

    stage: str
    command: str
    params: dict[str, Any]
    gate: str | None = None

    @property
    def gated(self) -> bool:
        return self.gate is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "command": self.command,
            "params": {name: as_text(value) for name, value in self.params.items()},
            "gate": self.gate,
        }


def declared(document: dict[str, Any]) -> list[Step]:
    """`pipeline:` out of an already-read `ssc.yaml` (R4.7, R4.8, R4.9).

    Everything is validated here, before the first step runs. A pipeline whose fourth step
    names a parameter that does not exist must not run the first three and then stop: the
    asset is left half-converted, and the caller who reruns is refused by the stages that
    did land.
    """
    found = document.get("pipeline")
    if found is None:
        raise UsageError(
            "no-pipeline",
            "this workspace declares no pipeline",
            fix="add a `pipeline:` list to ssc.yaml, each item a stage and a command",
        )
    if not isinstance(found, list) or not found:
        raise SscError(
            "invalid-pipeline",
            f"`pipeline` is {type(found).__name__}, not a list of steps",
            fix="write it as a list, each item with `stage:` and `command:`",
        )

    read: list[Step] = []
    seen: set[str] = set()
    for position, item in enumerate(found, start=1):
        if not isinstance(item, dict):
            raise SscError(
                "invalid-pipeline",
                f"step {position} is a {type(item).__name__}, not a map",
                fix="write each step with `stage:` and `command:`",
            )
        stage = item.get("stage")
        command = item.get("command")
        if not isinstance(stage, str) or not isinstance(command, str):
            raise SscError(
                "invalid-pipeline",
                f"step {position} needs a `stage:` and a `command:`, both names",
                fix="write each step with `stage:` and `command:`",
            )
        check_name(stage, "a stage")
        if stage in seen:
            # Two steps writing one stage is `meta.record`'s `stage-taken` arriving at the
            # end of a long run instead of before it starts, and it also makes R4.2's
            # "is this step done" a question with two subjects.
            raise SscError(
                "invalid-pipeline",
                f"two steps write stage {stage!r}",
                fix="a stage addresses one file; give each step its own",
            )
        seen.add(stage)

        if command in PAID or command.startswith("gen "):
            # R4.9 — refused by name, before the registry gets a chance to say "unknown".
            raise UsageError(
                "paid-step",
                f"step {stage!r} runs {command!r}, which costs money",
                fix=f"run it yourself with `ssc {command}`; `ssc run` is unattended and free",
            )

        entry = runnable(command)
        given = item.get("params")
        given = {} if given is None else given
        if not isinstance(given, dict):
            raise SscError(
                "invalid-pipeline",
                f"step {stage!r} declares params as {type(given).__name__}, not a map",
                fix="write `params:` as a map of name to value",
            )
        parsed = entry.read({str(name): as_text(value) for name, value in given.items()})

        asked = item.get("gate")
        if asked is not None and not isinstance(asked, str):
            raise SscError(
                "invalid-pipeline",
                f"step {stage!r} declares a gate that is not a question",
                fix="write `gate:` as the question to put to a person, or leave it out",
            )
        read.append(Step(stage=stage, command=command, params=parsed, gate=asked))

    return read


DONE, BLOCKED, OUTSTANDING = "done", "blocked", "outstanding"


@dataclass(frozen=True)
class Planned:
    """One step, and where the run stands on it.

    `needs` distinguishes the two ways a step can be outstanding: it has not run, or it ran
    and its gate has not been opened. Both mean `ssc run` has work to do at this step, and
    they are different work.
    """

    step: Step
    state: str
    needs: str | None = None
    gate: Any | None = None
    why: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.step.as_dict(),
            "state": self.state,
            "needs": self.needs,
            "why": self.why,
            "gate_state": None if self.gate is None else self.gate.state,
        }


def plan(
    declared_steps: list[Step],
    *,
    recorded: set[str],
    gate_for: Callable[[str], Any],
) -> list[Planned]:
    """Where a run stands, from the asset's recorded stages and the gates (R4.2, R4.4 to R4.6).

    **This is the whole of "resume from disk".** There is no run log: a step is done because
    its output stage is in the asset's `meta.json`, which is a question about the repository
    rather than about anything a previous session remembered to write down. A log would be a
    second record of a fact `meta.json` already holds, and the two disagree the moment
    somebody deletes a derived file.

    Each step is judged on its own — the sequencing is the caller's, and `blocker_of` is
    what says where the run actually stops. Judging them independently is what lets `status`
    report a whole pipeline rather than only as far as the first obstacle.
    """
    standing: list[Planned] = []
    for step in declared_steps:
        if step.stage not in recorded:
            standing.append(Planned(step=step, state=OUTSTANDING, needs="run"))
            continue

        if not step.gated:
            standing.append(Planned(step=step, state=DONE))
            continue

        gate = gate_for(step.stage)
        if gate is None:
            # The step produced its output and nobody has been asked yet. R4.3 says the gate
            # opens *after* the output exists, so this is the ordinary state a run reaches
            # mid-step rather than an anomaly.
            standing.append(Planned(step=step, state=OUTSTANDING, needs="gate"))
        elif gate.state == "approved":
            standing.append(Planned(step=step, state=DONE, gate=gate))
        else:
            standing.append(
                Planned(
                    step=step,
                    state=BLOCKED,
                    gate=gate,
                    why=gate.why or f"{gate.id} is {gate.state}",
                )
            )
    return standing


def next_of(standing: list[Planned]) -> Planned | None:
    """The first step that is not done — what `ssc run` would do next (R4.6)."""
    return next((one for one in standing if one.state != DONE), None)


def blocker_of(standing: list[Planned]) -> Planned | None:
    """The first step a decision is outstanding on, if any (R4.4, R4.5)."""
    return next((one for one in standing if one.state == BLOCKED), None)
