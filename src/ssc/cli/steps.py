"""The commands a sweep can vary and a pipeline can run, as data.

One table, two readings. `specs/sweep-and-review/` varies a parameter across a range;
`specs/gates-and-resume/`'s `ssc run` fixes the parameters and runs the step once. Two
tables would let the parameter you swept stop being the parameter the pipeline runs, which
is the failure the whole shape of this module exists to prevent.

**Two registries, and only one of them is free.** `REGISTRY` holds `tool` commands: frames
in, frames out, no money. `PAID_REGISTRY` holds the `gen` verbs a pipeline step may name,
which `adr:0014` made possible — a step may bill, behind a gate opened before the call and a
reservation behind it. They are separate tables because they are separate shapes, and the
one thing they share is the refusal a step gets when it names neither.

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

#: How a template variable travels in a flat `params:` map. A namespace rather than a new
#: syntax: `gen.parse_variables` still decides what a variable may be called, so the closed
#: vocabulary is not restated here.
VARIABLE_PREFIX = "var."


def text(value: str) -> str:
    """A parameter that is prose. The command it reaches does the refusing — a prompt has no
    shape to check, and a model name is checked against the registry where one is loaded."""
    return value


@dataclass(frozen=True)
class Paid:
    """One `gen` verb a pipeline step may name (`specs/generation-gates/` R2.1).

    A second table beside `REGISTRY` rather than a flag inside it, because what the two hold
    is not the same shape: a `Runnable` takes frames and returns frames, and this takes a
    description and returns a bill. A table whose rows mean two things is read wrongly by
    the third person to touch it.
    """

    name: str
    media: str
    parameters: dict[str, Callable[[str], Any]]

    def read(self, given: dict[str, str]) -> dict[str, Any]:
        """Parse every value, refusing a parameter this verb does not take (R2.3).

        `var.<name>` is passed through unparsed: what a variable may be called is
        `gen.parse_variables`' to say, and it says it once the call is built.
        """
        parsed: dict[str, Any] = {}
        for name, value in given.items():
            if name.startswith(VARIABLE_PREFIX):
                parsed[name] = value
                continue
            reader = self.parameters.get(name)
            if reader is None:
                raise UsageError(
                    "unknown-parameter",
                    f"{self.name} takes no parameter {name!r}",
                    fix=f"{self.name} takes: {', '.join(sorted(self.parameters))}, "
                    f"and {VARIABLE_PREFIX}<name> for a template variable",
                )
            parsed[name] = reader(value)
        return parsed


#: What every paid step may say about what it generates and what that costs. `from_stage`
#: and `role` are how a step points at what the step before it produced; the rest are the
#: options a caller would name on the command line.
_GENERATING = {
    "prompt": text,
    "model": text,
    "size": text,
    "count": whole(1, 16),
    "quality": text,
    "from_stage": text,
    "role": one_of(("identity", "palette", "pose", "board")),
}

#: The `gen` verbs a step may name. `gen expand` and `gen bgremove` are deliberately absent:
#: both transform a subject image rather than generating from a description, which makes
#: their input the previous stage rather than something the step declares — the shape the
#: free registry above already has. See `specs/generation-gates/`'s Out of scope.
PAID_REGISTRY: dict[str, Paid] = {
    "gen image": Paid(
        name="gen image",
        media="image",
        parameters={**_GENERATING, "style": text, "board": yes_or_no, "template": text},
    ),
    "gen boxart": Paid(
        name="gen boxart",
        media="image",
        # No style, no board and no reference: the look of the brief is not the look of the
        # deliverable, and a caller holding art has already answered what box art asks.
        parameters={
            name: reader
            for name, reader in _GENERATING.items()
            if name not in ("from_stage", "role")
        },
    ),
    "gen video": Paid(
        name="gen video",
        media="video",
        parameters={**_GENERATING, "seconds": whole(1, 60), "template": text},
    ),
}


def paid(name: str) -> Paid | None:
    """The paid verb by that name, or `None` where the command is not one."""
    return PAID_REGISTRY.get(name)


def bills(command: str) -> bool:
    """Whether this command costs money, whether or not a step may run it.

    `gen` and everything under it: the verb carries the guarantee, which is the property
    `ssc` is built on and the one an agent can act on without inspecting a flag.
    """
    return command == "gen" or command.startswith("gen ")


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

    @property
    def bills(self) -> bool:
        """Whether running this step spends money — which is what decides *when* its gate
        opens. Every other gate asks about output that exists; a paid step's output is the
        thing that costs, so its gate opens first. See `adr:0014`."""
        return bills(self.command)

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

        given = item.get("params")
        given = {} if given is None else given
        if not isinstance(given, dict):
            raise SscError(
                "invalid-pipeline",
                f"step {stage!r} declares params as {type(given).__name__}, not a map",
                fix="write `params:` as a map of name to value",
            )
        asked = item.get("gate")
        if asked is not None and not isinstance(asked, str):
            raise SscError(
                "invalid-pipeline",
                f"step {stage!r} declares a gate that is not a question",
                fix="write `gate:` as the question to put to a person, or leave it out",
            )

        entry: Paid | Runnable | None = paid(command) if bills(command) else None
        if bills(command):
            if asked is None:
                # `specs/gates-and-resume/` R4.9, now a condition rather than a refusal
                # (`adr:0014`): the gate is what stands in front of the money, so a paid step
                # without one is refused exactly as every paid step used to be.
                raise UsageError(
                    "paid-step",
                    f"step {stage!r} runs {command!r}, which costs money, and declares no gate",
                    fix="add `gate:` with the question to put to a person before it is "
                    f"submitted, or run it yourself with `ssc {command}`",
                )
            if entry is None:
                raise UsageError(
                    "paid-step",
                    f"step {stage!r} runs {command!r}, which is not a paid command a step may name",
                    fix=f"one of: {', '.join(sorted(PAID_REGISTRY))} — or run it yourself "
                    f"with `ssc {command}`",
                )
        else:
            entry = runnable(command)
        parsed = entry.read({str(name): as_text(value) for name, value in given.items()})

        read.append(Step(stage=stage, command=command, params=parsed, gate=asked))

    return read


def ask_for(
    step: Step,
    *,
    profile: Any,
    references: tuple[Any, ...] = (),
) -> Any:
    """The `gen.Ask` a paid step becomes (R2.1, R2.2).

    Imported inside the function, not at the top: `cli/gen.py` is the pipeline every paid
    command runs through and this module is data the *sweep* also reads, so the dependency
    is kept to the one function that needs it rather than made a property of importing the
    registry at all.

    `profile` is the `box-art` kind's, and only `gen boxart` uses it: its template and its
    cell are that kind's, whatever kind the asset is. The other two verbs take the asset's
    own, which `gen.build` reads for itself.
    """
    from ssc.cli import gen

    given = dict(step.params)
    variables = {
        name[len(VARIABLE_PREFIX) :]: str(value)
        for name, value in given.items()
        if name.startswith(VARIABLE_PREFIX)
    }
    entry = PAID_REGISTRY[step.command]
    size = given.get("size")
    is_box_art = step.command == gen.BOX_ART_VERB
    return gen.Ask(
        verb=step.command,
        media=entry.media,
        stage=step.stage,
        prompt=given.get("prompt"),
        template=profile.template if is_box_art else given.get("template"),
        cell=profile.cell if is_box_art else None,
        style=given.get("style"),
        references=references,
        board=bool(given.get("board", False)),
        seconds=given.get("seconds"),
        size=_size_for(size, profile.cell if is_box_art else None),
        count=given.get("count"),
        quality=given.get("quality"),
        model=given.get("model"),
        variables=gen.parse_variables(tuple(f"{k}={v}" for k, v in variables.items())),
    )


def _size_for(given: Any, fallback: tuple[int, int] | None) -> tuple[int, int] | None:
    """`WxH` from a step's params, or the cell box art falls back to."""
    if given is None:
        return fallback
    parts = str(given).lower().split("x")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise UsageError(
            "invalid-size",
            f"{given!r} is not a size like 1024x1024",
            fix="write it as WxH — ssc tool board reports the size a layout needs",
        )
    return int(parts[0]), int(parts[1])


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
        if step.bills and step.stage not in recorded:
            # The one step whose gate comes first (`adr:0014`). Every other gate asks about
            # output that exists; here the output is what costs, so the order inverts and
            # so does the reading of this state: no gate means one has to be opened, and an
            # approved one means the call may now be submitted.
            gate = gate_for(step.stage)
            if gate is None:
                standing.append(Planned(step=step, state=OUTSTANDING, needs="gate"))
            elif gate.state == "approved":
                standing.append(Planned(step=step, state=OUTSTANDING, needs="run", gate=gate))
            else:
                standing.append(
                    Planned(
                        step=step,
                        state=BLOCKED,
                        gate=gate,
                        why=gate.why or f"{gate.id} is {gate.state}",
                    )
                )
            continue

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
