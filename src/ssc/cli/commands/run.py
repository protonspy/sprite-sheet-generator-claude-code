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

from ssc.cli import config, gates, meta, steps
from ssc.cli import workspace as ws
from ssc.cli.atomic import Directory
from ssc.cli.commands.recover import asset_dir_for
from ssc.cli.errors import EXIT_GATE_PENDING, SscError
from ssc.cli.frames import encode, read_frames
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


def frames_of(asset_dir: Directory, record: meta.AssetMeta, stage: str) -> list[Any]:
    """The frames of a recorded stage, read off disk."""
    entry = record.stage(stage)
    where = asset_dir.path / entry.path
    if not where.exists():
        raise SscError(
            "stage-missing",
            f"{record.kind}/{record.key} records stage {stage!r} at {entry.path}, "
            "which is not there",
            fix="ssc clean removed it, or it was deleted by hand; rerun the step that made it",
        )
    return [frame.image for frame in read_frames(where)]


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
