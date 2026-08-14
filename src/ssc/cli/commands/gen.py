"""`ssc gen image|video|expand|bgremove|collect` — the half of the tool that bills.

Every command here is the same pipeline in `cli/gen.py` with different defaults: which media,
which model, which core options, and what the produced file's stage is called. What lives in
this module is the CLI surface and the two things a surface owes — reading `--from-stage` or
`--in` into bytes, and refusing a duration that is not one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from ssc.cli import fal, gen, kinds, listing, meta
from ssc.cli.errors import UsageError
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace

#: Registered here rather than in `cli/fal.py`, so importing that module has no side effect.
#: This module is what `cli/app.py` loads, which makes this the moment `ssc job status` starts
#: being able to reach a provider.
fal.register()


@click.group("gen", help="Paid. Everything under `gen` bills; everything under `tool` is free.")
def gen_group() -> None:
    """The verb carries the guarantee. An agent scanning the command list can tell which
    calls burn credit without inspecting a single flag — see `docs/wiki/`'s reasoning on why
    `gen bgremove` is `gen` even though it plainly does not generate anything."""


def provider() -> fal.Fal:
    return fal.Fal()


def parse_size(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    parts = value.lower().split("x")
    if len(parts) != 2 or not all(part.strip().isdigit() for part in parts):
        raise UsageError(
            "invalid-size",
            f"{value!r} is not a size like 1024x1024",
            fix="write it as WxH — ssc tool board reports the size a layout needs",
        )
    return int(parts[0]), int(parts[1])


def check_wait(timeout: float, poll: float) -> None:
    """The same guard `ssc job wait` needs, for the same reason.

    `--timeout nan` walks through every `<= 0` check, because comparing against `nan` is
    always False — and the command then never returns, which inside a harness is exactly what
    a timeout exists to prevent. `inf` is refused for both, and on the poll side twice over:
    `time.sleep(inf)` is an `OverflowError` rather than a long sleep.
    """
    if not timeout > 0 or not poll > 0 or float("inf") in (timeout, poll):
        raise UsageError(
            "invalid-wait",
            "--timeout and --poll are durations, and both have to be above zero",
            fix="leave them out for the defaults",
        )


def source_image(
    workspace: Workspace,
    asset: str,
    stage: str | None,
    source: Path | None,
    *,
    into_a_sprite: bool = False,
) -> gen.Image:
    """The image being sent, from a stage of the asset or from a loose file (R2.2).

    Exactly one of the two, because naming neither is a call with nothing to work from and
    naming both is two answers to one question. This is the *subject* case — `gen video`,
    `gen expand` and `gen bgremove` each transform one image — and it stays singular for
    that reason; `gen image` takes references instead, through `references_for`.

    `into_a_sprite` is what decides whether box art may be the subject, and the three
    commands answer it differently (R3.1, R3.2). A clip is frames, and frames at box art's
    fidelity are the same unusable frames an anchor drawn from it would be — so `gen video`
    says yes and is refused. `gen expand` widens the concept piece and `gen bgremove` cuts
    the character out of it: both produce box art, which is a roster image somebody may
    legitimately want, so both say no and are allowed.
    """
    if (stage is None) == (source is None):
        raise UsageError(
            "no-input",
            "give exactly one of --from-stage <stage> and --in <path>",
            fix="--from-stage reads the asset's own chain; --in takes any file",
        )
    if source is not None:
        return gen.image_at(source)

    # Held across the record *and* the file it names: the bytes being paid to transform have
    # to come through the binding the address was checked against, so closing it once the
    # record was in hand would have bound the half that costs nothing (R3.7).
    held, record = listing.resolve(workspace, asset)
    with held:
        entry = record.stage(str(stage))
        if into_a_sprite:
            refuse_box_art(entry, str(stage))
        return gen.image_in(held, entry.path)


def split_role(value: str, *, is_path: bool) -> tuple[str, str | None]:
    """`x` or `x:role` into the two, with the role checked against `gen.ROLES`.

    Split on the last colon, and only where what follows is a role this package defines.
    What the rest of the value *is* decides how hard that is: a **stage** is a name, and
    `workspace-foundation`'s naming rules leave no legal colon in one, so any suffix at all
    was meant to be a role and one that is not is refused. A **path** may legitimately hold
    a colon — `C:\\art\\anchor.png` is the ordinary Windows case — so a suffix is only read
    as a role attempt where the head names a file that is really there.

    The distinction is the caller's to state rather than something to infer. Inferring it
    from the filesystem is what the first draft did, and it silently gave up on the stage
    case: no stage name is ever a file in the working directory, so `--from-stage
    gen:identtiy` came back as `unknown-stage` — a true error, about the wrong thing.
    """
    head, separator, tail = value.rpartition(":")
    if not separator or not head:
        return value, None
    if tail in gen.ROLES:
        return head, tail
    if not is_path or Path(head).is_file():
        # The head is a stage, or it names a real file, so the tail was meant to be a role
        # and is not one. Reading it as part of the name instead refuses for the wrong
        # reason and sends the caller looking for something that was never the problem.
        raise UsageError(
            "unknown-role",
            f"{tail!r} is not what a reference can be for",
            fix=f"the roles are: {', '.join(gen.ROLES)} — or drop the suffix",
        )
    return value, None


#: The kind whose profile says what box art is: its cell, and the template it is drawn to.
#: A kind rather than constants here, so a project that redeclares it moves both — and the
#: same kind an asset can be, because a roster piece is a deliverable in its own right.
BOX_ART_KIND = "box-art"

#: The stage box art lands in by default, and the verb its record carries — which is what
#: says a file *is* box art after `--stage` has renamed the stage.
BOX_ART_STAGE = "boxart"
BOX_ART_VERB = "gen boxart"


def refuse_box_art(entry: meta.FileRecord, named: str) -> None:
    """Box art makes a worse anchor, and this is where that stops being a rule nobody
    enforces (`specs/box-art/` R3.1).

    The model honours it, which is the problem: the anchor comes back at box art's fidelity,
    richly shaded and finely detailed, when what a sprite cell needs is the opposite. The
    detail cannot survive the trip down to 64 pixels, so it arrives as noise `tool normalise`
    then has to fight — see `docs/wiki/box-art-and-style.md`.

    Against the provenance rather than the stage name: `--stage` renames the stage, and the
    record is what remembers where a file came from.
    """
    if entry.produced_by.command != BOX_ART_VERB:
        return
    raise UsageError(
        "box-art-as-reference",
        f"{named} is box art, and box art passed as a reference comes back as itself: "
        f"too finely detailed to survive being reduced to a cell",
        fix="box art informs the prompt, not the payload — derive the sprite from it with "
        "ssc tool pixelart, and pass that",
    )


def references_for(
    workspace: Workspace, asset: str, stages: tuple[str, ...], refs: tuple[str, ...]
) -> tuple[gen.Reference, ...]:
    """Every image this call sends, in the order they were named (R1.1, R1.2).

    Stages first, then loose paths — a stable order, and the one that reads the way a caller
    builds a call: the asset's own chain is what a direction derives from, and the board or
    the swatch is the thing added to it.
    """
    if len(stages) + len(refs) > gen.MAX_REFERENCES:
        # Before the first read rather than in `build`, which is where the same ceiling is
        # checked against the finished list: this one is about memory, and by the time the
        # pipeline sees them they are all resident. Both, because they bound different
        # things — the images a caller named, and the images a call ends up carrying.
        raise UsageError(
            "too-many-references",
            f"{len(stages) + len(refs)} references is past {gen.MAX_REFERENCES}",
            fix="a generation derives from a handful of images; send fewer",
        )

    found: list[gen.Reference] = []
    if stages:
        # One hold for every stage, rather than one per stage: the record and the files it
        # names are read through the same binding, which is what R3.7 asks for.
        held, record = listing.resolve(workspace, asset)
        with held:
            for stage in stages:
                name, role = split_role(stage, is_path=False)
                entry = record.stage(name)
                refuse_box_art(entry, name)
                found.append(gen.Reference(gen.image_in(held, entry.path), role))
    for ref in refs:
        path, role = split_role(ref, is_path=True)
        found.append(gen.Reference(gen.image_at(Path(path)), role))
    return tuple(found)


def imaging(command: Any) -> Any:
    """The three options every image-making model has some of (`specs/model-options/` R3.2).

    Named flags rather than `--opt num_images=2`, because an agent driving this tool cannot use
    an option it has to already know exists — and `--count` is the one that multiplies what a
    call costs, so it is the last one to leave to a raw pass-through. Not in `shared`: no video
    model in the registry has any of the three, and a flag that always refuses is worse than
    an absent one.
    """
    for option in reversed(
        [
            click.option(
                "--count",
                type=int,
                default=None,
                help="How many images one call returns. Every one is billed.",
            ),
            click.option(
                "--quality", default=None, help="The model's quality tier, where it has one."
            ),
            click.option("--format", "image_format", default=None, help="jpeg, png or webp."),
        ]
    ):
        command = option(command)
    return command


def shared(command: Any) -> Any:
    """The options every paid command has. Declared once: four copies of `--no-wait` is four
    chances for one of them to mean something slightly different — the shape `recover.py`
    already uses for the options `cut` and `slice` share."""
    for option in reversed(
        [
            click.option("--asset", required=True, help="Record into this <kind>/<key>."),
            click.option("--stage", default=None, help="Name the stage the result becomes."),
            click.option("--model", default=None, help="Override the configured model."),
            click.option(
                "--opt",
                "options",
                multiple=True,
                help="A raw model option as key=value. Repeatable, checked against the "
                "model's schema.",
            ),
            click.option(
                "--upload",
                is_flag=True,
                help="Put the input image on fal's storage instead of inlining it.",
            ),
            click.option(
                "--no-wait", is_flag=True, help="Submit and report the job; collect later."
            ),
            click.option(
                "--timeout",
                type=float,
                default=gen.DEFAULT_TIMEOUT,
                help="Seconds to wait for the job.",
            ),
            click.option(
                "--poll", type=float, default=gen.POLL_SECONDS, help="Seconds between asks."
            ),
        ]
    ):
        command = option(command)
    return command


@ssc_command("image", help="Generate an image into an asset. Costs money.", needs_workspace=True)
@shared
@imaging
@click.option("--seed", type=int, default=None, help="Where the model supports one.")
@click.option("--size", default=None, help="The size the layout needs, as WxH.")
@click.option(
    "--board",
    is_flag=True,
    help="Attach the reference board the resolved style names, generated now.",
)
@click.option(
    "--ref",
    "references",
    multiple=True,
    help="A file to derive from, as <path> or <path>:<role>. Repeatable.",
)
@click.option(
    "--from-stage",
    "stages",
    multiple=True,
    help="A stage of the asset to derive from, as <stage> or <stage>:<role>. Repeatable.",
)
@click.option("--template", default=None, help="Override the prompt template the kind names.")
@click.option(
    "--style",
    default=None,
    help="How it is drawn: a shipped name, or free text. Defaults to what the kind names.",
)
@click.option(
    "--var",
    "variables",
    multiple=True,
    help="Fill a named slot in the template, as key=value. Repeatable.",
)
@click.option("--prompt", required=True, help="What to generate.")
def gen_image(
    asset: str,
    prompt: str,
    stages: tuple[str, ...],
    references: tuple[str, ...],
    board: bool,
    size: str | None,
    style: str | None,
    seed: int | None,
    count: int | None,
    quality: str | None,
    image_format: str | None,
    stage: str | None,
    model: str | None,
    template: str | None,
    variables: tuple[str, ...],
    options: tuple[str, ...],
    upload: bool,
    no_wait: bool,
    timeout: float,
    poll: float,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """R1.1, R1.2, R2.1, R2.7, R3.1 — and the reference, which moves the call to `/edit` (R2.6).

    `--template` is the exception to "the kind names the template", and it exists because one
    kind has more than one job. A `character` asset is generated several times over its life —
    the South anchor with a pixel-grid board, then the other directions, then the poses — and
    those want different words. Making each a kind would be a kind per *stage* rather than per
    *asset*, which is not what a kind is.
    """
    check_wait(timeout, poll)
    ask = gen.Ask(
        verb="gen image",
        media="image",
        stage=stage or "gen",
        prompt=prompt,
        references=references_for(workspace, asset, stages, references),
        board=board,
        size=parse_size(size),
        seed=seed,
        count=count,
        quality=quality,
        image_format=image_format,
        model=model,
        template=template,
        style=style,
        options=gen.parse_options(options),
        variables=gen.parse_variables(variables),
        upload=upload,
    )
    return gen.run(
        workspace,
        ask,
        asset,
        provider=provider(),
        dry_run=dry_run,
        wait=not no_wait,
        timeout=timeout,
        poll=poll,
    )


@ssc_command(
    "boxart",
    help="Generate the concept piece a person approves. Costs money.",
    needs_workspace=True,
)
@shared
@imaging
@click.option("--size", default=None, help="Override the size; the box-art cell by default.")
@click.option(
    "--var",
    "variables",
    multiple=True,
    help="Fill a named slot in the template, as key=value. Repeatable.",
)
@click.option("--prompt", required=True, help="Who the character is.")
def gen_boxart(
    asset: str,
    prompt: str,
    size: str | None,
    count: int | None,
    quality: str | None,
    image_format: str | None,
    stage: str | None,
    model: str | None,
    variables: tuple[str, ...],
    options: tuple[str, ...],
    upload: bool,
    no_wait: bool,
    timeout: float,
    poll: float,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """The first decision in front of a character: what it *is*, before how it is drawn.

    A command rather than a flag on `gen image`, because the flag would have to disable
    `--ref`, `--from-stage`, `--board` and `--style` and override the template and the cell
    — six behaviours conditional on one flag, which is a second command wearing a disguise.
    Here those options are not absent by a check but by not existing, which is how R2.1 and
    R1.4 are met: there is nothing to pass.
    """
    check_wait(timeout, poll)
    profile = kinds.resolve(BOX_ART_KIND, workspace).profile
    ask = gen.Ask(
        verb=BOX_ART_VERB,
        media="image",
        stage=stage or BOX_ART_STAGE,
        prompt=prompt,
        template=profile.template,
        # Both from the `box-art` profile, and neither from the asset's own kind: a
        # character's cell is 64x64 and its concept piece is a portrait at a size no cell
        # ever is. `--size` still overrides, for a caller who wants another shape.
        cell=profile.cell,
        size=parse_size(size) or profile.cell,
        count=count,
        quality=quality,
        image_format=image_format,
        model=model,
        options=gen.parse_options(options),
        variables=gen.parse_variables(variables),
        upload=upload,
    )
    produced = gen.run(
        workspace,
        ask,
        asset,
        provider=provider(),
        dry_run=dry_run,
        wait=not no_wait,
        timeout=timeout,
        poll=poll,
    )
    # What to do with it (R1.5). Box art is a brief, not a draft: the sprite is *derived*
    # from it and never generated again, and the command that derives it is the free one.
    produced.data["derive"] = f"ssc tool pixelart --in <the approved image> --out {ask.stage}/"
    return produced


@ssc_command("video", help="Animate an image into a clip. Costs money.", needs_workspace=True)
@shared
@click.option("--seconds", type=int, default=None, help="Clip length, where the model takes one.")
@click.option("--in", "source", default=None, type=click.Path(path_type=Path))
@click.option("--from-stage", default=None, help="Which stage of the asset to animate.")
@click.option("--template", default=None, help="Which animation template. Defaults to the base.")
@click.option(
    "--var",
    "variables",
    multiple=True,
    help="Fill a named slot in the template, as key=value. Repeatable.",
)
@click.option("--prompt", required=True, help="What the subject does.")
def gen_video(
    asset: str,
    prompt: str,
    from_stage: str | None,
    source: Path | None,
    seconds: int | None,
    stage: str | None,
    model: str | None,
    template: str | None,
    variables: tuple[str, ...],
    options: tuple[str, ...],
    upload: bool,
    no_wait: bool,
    timeout: float,
    poll: float,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """No board, whatever the asset's kind — a video model given a grid paints the grid onto
    the character, and the kind had its say when the image this animates was generated.

    The template is the kind-independent one, because what an animation must not do is the
    same for every kind: hold the direction, hold the camera, and leave the background alone.
    `--template walk` adds the motion of a walk cycle to that base; a different animation is
    a different template rather than a different command.

    Video length stays a per-model fact: nothing here defaults `--seconds`, because the
    sources disagree head-on about what loops well.
    """
    check_wait(timeout, poll)
    ask = gen.Ask(
        verb="gen video",
        media="video",
        stage=stage or "video",
        prompt=prompt,
        template=template or gen.VIDEO_TEMPLATE,
        # One image, and no way to make it two: a video model given a board paints the grid
        # onto the character, and a mistake that cannot be expressed cannot be made under
        # time pressure (`specs/reference-images/` R4.1, docs/wiki/reference-boards.md).
        references=(
            gen.Reference(source_image(workspace, asset, from_stage, source, into_a_sprite=True)),
        ),
        seconds=seconds,
        model=model,
        options=gen.parse_options(options),
        variables=gen.parse_variables(variables),
        upload=upload,
    )
    return gen.run(
        workspace,
        ask,
        asset,
        provider=provider(),
        dry_run=dry_run,
        wait=not no_wait,
        timeout=timeout,
        poll=poll,
    )


@ssc_command(
    "expand", help="Outpaint an image to a larger canvas. Costs money.", needs_workspace=True
)
@shared
@imaging
@click.option("--size", default=None, help="The canvas to reach, as WxH.")
@click.option("--in", "source", default=None, type=click.Path(path_type=Path))
@click.option("--from-stage", default=None, help="Which stage of the asset to expand.")
@click.option("--prompt", required=True, help="What belongs in the new area.")
def gen_expand(
    asset: str,
    prompt: str,
    from_stage: str | None,
    source: Path | None,
    size: str | None,
    count: int | None,
    quality: str | None,
    image_format: str | None,
    stage: str | None,
    model: str | None,
    options: tuple[str, ...],
    upload: bool,
    no_wait: bool,
    timeout: float,
    poll: float,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """A model invents the new area, which is the whole difference from `tool expand` — that
    one pads a canvas, deterministically and for free. One name for both would hide the price
    behind a flag."""
    check_wait(timeout, poll)
    ask = gen.Ask(
        verb="gen expand",
        media="image",
        stage=stage or "expand",
        prompt=prompt,
        references=(gen.Reference(source_image(workspace, asset, from_stage, source)),),
        size=parse_size(size),
        count=count,
        quality=quality,
        image_format=image_format,
        model=model,
        options=gen.parse_options(options),
        upload=upload,
    )
    return gen.run(
        workspace,
        ask,
        asset,
        provider=provider(),
        dry_run=dry_run,
        wait=not no_wait,
        timeout=timeout,
        poll=poll,
    )


@ssc_command(
    "bgremove",
    help="Take the background out with a hosted model. Costs money.",
    needs_workspace=True,
)
@shared
@click.option("--format", "image_format", default=None, help="png, webp or gif.")
@click.option("--in", "source", default=None, type=click.Path(path_type=Path))
@click.option("--from-stage", default=None, help="Which stage of the asset to key.")
def gen_bgremove(
    asset: str,
    from_stage: str | None,
    source: Path | None,
    image_format: str | None,
    stage: str | None,
    model: str | None,
    options: tuple[str, ...],
    upload: bool,
    no_wait: bool,
    timeout: float,
    poll: float,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """`gen` and not `tool`, and it plainly does not generate anything: the verb means the
    provider does it and charges, which is the property an agent can act on. The free path is
    still `ssc tool bgremove`, by chroma."""
    check_wait(timeout, poll)
    ask = gen.Ask(
        verb="gen bgremove",
        media="image",
        stage=stage or "nobg",
        role="background-removal",
        references=(gen.Reference(source_image(workspace, asset, from_stage, source)),),
        image_format=image_format,
        model=model,
        options=gen.parse_options(options),
        upload=upload,
    )
    return gen.run(
        workspace,
        ask,
        asset,
        provider=provider(),
        dry_run=dry_run,
        wait=not no_wait,
        timeout=timeout,
        poll=poll,
    )


@ssc_command(
    "collect", help="File the result of a job that is already paid for.", needs_workspace=True
)
@click.option("--poll", type=float, default=gen.POLL_SECONDS, help="Seconds between asks.")
@click.option(
    "--timeout", type=float, default=gen.DEFAULT_TIMEOUT, help="Seconds to wait for the job."
)
@click.option("--stage", default="gen", help="Name the stage the result becomes.")
@click.option("--asset", required=True, help="Record into this <kind>/<key>.")
@click.argument("job_id")
def gen_collect(
    job_id: str,
    asset: str,
    stage: str,
    timeout: float,
    poll: float,
    *,
    dry_run: bool,
    workspace: Workspace,
) -> Result:
    """R1.5 — the reason `--no-wait` is safe, and the reason a crash costs nothing but time.

    The destination is named here rather than read from the job, because a job record is a
    provider-shaped pair of identifiers and a workspace path in it is the first thing a second
    provider could not honour.
    """
    check_wait(timeout, poll)
    return gen.collect_job(
        workspace,
        job_id,
        asset,
        provider=provider(),
        stage=stage,
        dry_run=dry_run,
        timeout=timeout,
        poll=poll,
    )


gen_group.add_command(gen_image)
gen_group.add_command(gen_boxart)
gen_group.add_command(gen_video)
gen_group.add_command(gen_expand)
gen_group.add_command(gen_bgremove)
gen_group.add_command(gen_collect)
