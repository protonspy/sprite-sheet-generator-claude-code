"""`ssc run` and `ssc status` — the pipeline, and where it has got to.

Neither keeps a run log. A step is done because its output stage is recorded in the asset's
`meta.json`, which is a question about the repository rather than about anything a previous
session remembered to write down. That is the whole of "resume from disk": kill the process
at any point and the next `ssc run` continues from the same place, because the place was
never held in memory.
"""

from __future__ import annotations

from typing import Any

import click

from ssc.cli import budget, config, gates, kinds, meta, models, steps
from ssc.cli import gen as gen
from ssc.cli import workspace as ws
from ssc.cli.atomic import Directory
from ssc.cli.commands import gen as gen_commands
from ssc.cli.commands.recover import asset_dir_for
from ssc.cli.errors import EXIT_GATE_PENDING, SscError
from ssc.cli.frames import encode
from ssc.cli.listing import frames_of
from ssc.cli.main import ssc_command
from ssc.cli.output import Result

#: Where a step's frame set lands: `frames/<stage>/`, inside the one subdirectory an asset
#: is allowed. See the delta on `specs/workspace-foundation/` R2.5 — the alternative was a
#: second top-level directory per stage, which that requirement forbids for good reasons
#: that have nothing to do with this.
FRAMES_DIR = meta.FRAMES_DIR

#: What the first step reads when it does not say. `tool cut` records its output under this
#: stage, so a pipeline that begins after `cut` needs to name nothing.
DEFAULT_SOURCE = "frames"


def source_stage(declared: list[steps.Step], position: int) -> str:
    """What step `position` reads: the step before it, or `frames` for the first.

    Implicit rather than declared, because a pipeline is a chain by definition and making
    every step restate its input is a place for the two to disagree.
    """
    return declared[position - 1].stage if position > 0 else DEFAULT_SOURCE


def write_stage(
    asset_dir: Directory,
    record: meta.AssetMeta,
    step: steps.Step,
    images: list[Any],
    source: str,
) -> str:
    """Write a step's frames as one recorded stage.

    One record for N frames, exactly as `tool cut` does it: a stage is unique per asset and
    a frame set is one stage, not one per file.
    """
    relative = f"{FRAMES_DIR}/{step.stage}"
    with (
        Directory.open(asset_dir.path / FRAMES_DIR) as frames_dir,
        frames_dir.child(step.stage) as into,
    ):
        for index, image in enumerate(images, start=1):
            into.write_new(f"{index:03d}.png", encode(image))

    meta.record(
        record,
        path=relative,
        stage=step.stage,
        file_class="derived",
        data=b"".join(encode(image) for image in images),
        produced_by=meta.Provenance(
            command=f"tool {step.command}",
            params={name: steps.as_text(value) for name, value in step.params.items()},
        ),
        derived_from=[source],
    )
    meta.save(asset_dir, record)
    return relative


def standing(
    workspace: ws.Workspace, address: str
) -> tuple[Directory, meta.AssetMeta, list[steps.Step], list[steps.Planned]]:
    """The asset, the declared pipeline, and where the run stands — read from disk alone."""
    declared = steps.declared(config.document(workspace))
    asset_dir, record = asset_dir_for(address)
    try:
        recorded = {entry.stage for entry in record.files}
        return (
            asset_dir,
            record,
            declared,
            steps.plan(
                declared,
                recorded=recorded,
                gate_for=lambda stage: gates.find(workspace, record.key, stage),
            ),
        )
    except BaseException:
        asset_dir.close()
        raise


@ssc_command(
    "status",
    help="Where an asset is in the pipeline, and what runs next.",
    needs_workspace=True,
)
@click.argument("address")
def status(address: str, *, dry_run: bool, workspace: ws.Workspace) -> Result:
    """R4.6 — exit `0`. A query that exited `3` for reporting a pending gate would make
    "I could not tell you" and "I told you, and it is pending" the same value."""
    asset_dir, _, _, planned = standing(workspace, address)
    with asset_dir:
        upcoming = steps.next_of(planned)
        blocked = steps.blocker_of(planned)
        done = sum(1 for one in planned if one.state == steps.DONE)
        return Result(
            "status",
            f"{address}: {done} of {len(planned)} done"
            + (f", blocked at {blocked.step.stage}" if blocked else "")
            + (f", next {upcoming.step.stage}" if upcoming and not blocked else ""),
            {
                "asset": address,
                "steps": [one.as_dict() for one in planned],
                "done": done,
                "next": None if upcoming is None else upcoming.step.stage,
                "blocked_by": None if blocked is None else blocked.step.stage,
            },
            dry_run=dry_run,
        )


@ssc_command(
    "run",
    help="Run the pipeline for an asset, stopping at the next decision.",
    needs_workspace=True,
)
@click.argument("address")
def run(address: str, *, dry_run: bool, workspace: ws.Workspace) -> Result:
    """R4.1 to R4.5.

    The loop re-reads nothing: `plan` was computed once from disk, and each step that runs
    updates the record in memory and on disk as it goes. A step's own failure is not caught
    — a pipeline that half-ran and reported success is the failure this design is built to
    avoid, and `meta.json` records exactly the stages that landed.
    """
    asset_dir, record, declared, planned = standing(workspace, address)
    with asset_dir:
        ran: list[str] = []
        for position, one in enumerate(planned):
            if one.state == steps.DONE:
                continue

            if one.state == steps.BLOCKED:
                gate = one.gate
                if gate is not None and gate.state == gates.REJECTED:
                    # R4.5 — nothing is pending, so this is not exit `3`. Somebody decided,
                    # and the decision was no.
                    raise SscError(
                        "gate-rejected",
                        f"{gate.id} was rejected: {gate.why or 'no reason given'}",
                        fix="fix what it rejected and open a new gate, or change the pipeline",
                    )
                return _stopped(address, one, ran, planned, dry_run=dry_run)

            step = one.step
            if step.bills:
                stopped = _bill(
                    workspace,
                    asset_dir,
                    record,
                    one,
                    address,
                    ran,
                    planned,
                    dry_run=dry_run,
                )
                if stopped is not None:
                    return stopped
                # `gen.run` files what came back through its own handle on the asset, so the
                # record this loop is holding no longer knows about the stage that just
                # landed. Re-read it: a later free step saving a stale record would drop the
                # paid stage out of `meta.json` — the one file that says what a paid call
                # produced, and the one thing that cannot be recomputed.
                record = meta.load(asset_dir)
                continue

            if one.needs == "run":
                source = source_stage(declared, position)
                if dry_run:
                    return Result(
                        "run",
                        f"would run {step.stage} ({step.command}) on {address}",
                        {"asset": address, "would_run": step.stage, "ran": ran},
                        dry_run=True,
                    )
                images = frames_of(asset_dir, record, source)
                outcome = steps.runnable(step.command).run(images, step.params)
                write_stage(asset_dir, record, step, outcome.frames, source)
                ran.append(step.stage)

            if step.gated:
                # R4.3 — the gate opens once the output exists, so the person has something
                # to look at. Opening it before would be asking about work nobody has done.
                if dry_run:
                    return Result(
                        "run",
                        f"would open the gate on {step.stage}",
                        {"asset": address, "would_gate": step.stage, "ran": ran},
                        dry_run=True,
                    )
                opened = gates.Gate.new(
                    subject=record.key,
                    topic=step.stage,
                    question=step.gate or "",
                    material=str(asset_dir.path / FRAMES_DIR / step.stage),
                    at=gates.now(),
                )
                adopted = gates.defaults(workspace).get(step.stage)
                if adopted is not None:
                    # R3.2 — a topic this workspace has settled does not stop the run again.
                    gates.save(workspace, opened.inheriting(adopted, at=gates.now()))
                    continue
                gates.save(workspace, opened)
                return _stopped(
                    address,
                    steps.Planned(step=step, state=steps.BLOCKED, gate=opened),
                    ran,
                    planned,
                    dry_run=dry_run,
                )

        return Result(
            "run",
            f"{address}: pipeline complete"
            + (f", ran {', '.join(ran)}" if ran else ", nothing left to do"),
            {"asset": address, "ran": ran, "complete": True},
            dry_run=dry_run,
        )


def _reference_for(
    asset_dir: Directory, record: meta.AssetMeta, step: steps.Step
) -> tuple[Any, ...]:
    """The stage a paid step points at, read as a reference (R2.2).

    Through the held directory, like every read of an asset's own file: the bytes a call is
    paid to work from come through the binding the address was checked against.
    """
    named = step.params.get("from_stage")
    if named is None:
        return ()
    entry = record.stage(str(named))
    return (gen.Reference(gen.image_in(asset_dir, entry.path), step.params.get("role")),)


def _standing(workspace: ws.Workspace, topic: str) -> gates.Default | None:
    """The standing approval for this topic, where one was really given here (R4.3).

    `adr:0014` allows a topic to be adopted — a project that has decided it trusts
    unattended generation of, say, direction frames records that once rather than answering
    per asset — and this is where that stops being taken on trust. `defaults.json` is a file
    in the workspace like any other, so one that arrived with a cloned repository would
    otherwise be a standing authorisation to spend that nobody in this workspace ever gave.
    The gate it names has to be here, and approved.
    """
    adopted = gates.defaults(workspace).get(topic)
    if adopted is None:
        return None
    came_from = gates.path_of(workspace, adopted.came_from)
    if not came_from.is_file():
        return None
    origin = gates.load(workspace, adopted.came_from)
    return adopted if origin.state == gates.APPROVED else None


def _bill(
    workspace: ws.Workspace,
    asset_dir: Directory,
    record: meta.AssetMeta,
    one: steps.Planned,
    address: str,
    ran: list[str],
    planned: list[steps.Planned],
    *,
    dry_run: bool,
) -> Result | None:
    """A step that costs money: the gate first, then the call (`adr:0014`).

    `None` back means the step ran and the loop carries on; a `Result` means the run stopped,
    either at the gate or because the caller asked for a dry run.

    The call is built before the gate is opened even though nothing is submitted yet, and
    that is the point: `gen.build` touches no network — which is what makes `--dry-run`
    possible and what makes this possible — so the question put to a person can name the
    model that would run and what it is estimated to cost (R1.4). A gate that said only
    "this step bills" would be asking somebody to approve a number they cannot see.
    """
    step = one.step
    profile = kinds.resolve(gen.BOX_ART_KIND, workspace).profile
    ask = steps.ask_for(step, profile=profile, references=_reference_for(asset_dir, record, step))
    registry = models.load()
    settings = config.document(workspace)
    call = gen.build(registry, ask, kinds.resolve(record.kind, workspace).profile, settings)
    estimate = budget.estimate_for(registry, call)

    if one.needs == "run" and (one.gate is None or one.gate.authorises != call.key()):
        # The approval is bound to the call it was shown, not to the asset and the stage.
        # `ssc.yaml` is re-read every run and is workspace data — it arrives with a cloned
        # repository as often as it is written by whoever runs the command — so between
        # `gate approve` and the next `ssc run` the model, the prompt or `count` can change
        # under a signature given for something else. A gate that does not name this call
        # authorises nothing, and the question is put again.
        one = steps.Planned(step=step, state=steps.OUTSTANDING, needs="gate")

    if one.needs == "gate":
        if dry_run:
            return Result(
                "run",
                f"would open the gate on {step.stage} before calling {call.endpoint}",
                {
                    "asset": address,
                    "would_gate": step.stage,
                    "ran": ran,
                    "estimate_usd": estimate,
                    # The whole resolved call, not just the model (R2.4). This is the branch
                    # a dry run normally lands in — checking a paid step *before* opening a
                    # gate is what somebody uses it for — so reporting less here than after
                    # an approval would answer the question in the case nobody asks it in.
                    **call.report(),
                },
                dry_run=True,
            )
        opened = gates.Gate.new(
            subject=record.key,
            topic=step.stage,
            question=f"{step.gate or ''} — {step.command} on {call.endpoint}"
            + (f", about ${estimate:.2f}" if estimate is not None else ", price unknown"),
            material=None,
            at=gates.now(),
            authorises=call.key(),
        )
        adopted = _standing(workspace, step.stage)
        if adopted is None:
            gates.save(workspace, opened)
            return _stopped(
                address,
                steps.Planned(step=step, state=steps.BLOCKED, gate=opened),
                ran,
                planned,
                dry_run=dry_run,
            )
        # R3.2 of `gates-and-resume` — a topic this workspace has settled does not stop the
        # run again. Here that is a standing authorisation to spend, which is the blast
        # radius `adr:0014` names and `ssc gate list` is where somebody sees it.
        gates.save(workspace, opened.inheriting(adopted, at=gates.now()))

    if dry_run:
        return Result(
            "run",
            f"would call {call.endpoint} for {step.stage} on {address}",
            {"asset": address, "would_run": step.stage, "ran": ran, **call.report()},
            dry_run=True,
        )

    # The same path a hand-typed call takes: the job record before submission, the
    # reservation, the cache, and the result filed as a `source`. `budget.reserve` raises to
    # refuse, which stops the run with nothing submitted (R3.1, R3.2).
    # Through `commands/gen.py`'s own accessor rather than constructing a client here: one
    # seam for the provider means a test that stands a fake in front of `gen image` stands
    # the same fake in front of a step that runs it.
    gen.run(workspace, ask, address, provider=gen_commands.provider(), registry=registry)
    ran.append(step.stage)
    return None


def _stopped(
    address: str,
    at: steps.Planned,
    ran: list[str],
    planned: list[steps.Planned],
    *,
    dry_run: bool,
) -> Result:
    """R4.3 — stopped at a gate, reporting what did run.

    Exit `3` on the `Result` rather than by raising, so the steps that landed are in the
    payload. A caller resuming needs to know how far it got, and an exception cannot say.
    """
    gate = at.gate
    return Result(
        "run",
        f"{address}: stopped at {at.step.stage} — {gate.question if gate else at.why}",
        {
            "asset": address,
            "ran": ran,
            "complete": False,
            "stopped_at": at.step.stage,
            "gate": None if gate is None else gate.as_dict(),
            "steps": [one.as_dict() for one in planned],
        },
        dry_run=dry_run,
        exit_code=EXIT_GATE_PENDING,
    )
