"""`ssc image list|show` and `ssc video list|show` — what exists, and what one file is.

Two nouns, because generation has exactly two modalities and everything `ssc` writes is one
or the other. They differ in exactly one value, so both are built by one factory: `ssc video
list` drifting from `ssc image list` by an edit applied to only one of two copies is the
failure this shape makes impossible rather than merely unlikely.
"""

from __future__ import annotations

from typing import Any

import click

from ssc.cli.errors import UsageError
from ssc.cli.listing import Entry, Media, chain_order, entries, lineage, media_of, resolve
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.cli.workspace import Workspace

CLASSES = ("source", "derived", "output")


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def build(noun: Media) -> click.Group:
    """The two commands for one medium."""

    @ssc_command("list", help=f"List the {noun}s recorded in this workspace.", needs_workspace=True)
    @click.option("--stage", default=None, help="Only files carrying this stage.")
    @click.option(
        "--class",
        "file_class",
        type=click.Choice(CLASSES),
        default=None,
        help="Only files of this class.",
    )
    @click.argument("kind", required=False)
    def list_files(
        kind: str | None,
        file_class: str | None,
        stage: str | None,
        *,
        dry_run: bool,
        workspace: Workspace,
    ) -> Result:
        matched = [
            entry
            for entry in entries(workspace)
            if (kind is None or entry.kind == kind)
            and (stage is None or entry.record.stage == stage)
            and (file_class is None or entry.record.file_class == file_class)
        ]
        files = [entry for entry in matched if entry.media == noun]
        # A recorded file in neither medium is reported rather than dropped: this is the
        # command an agent uses instead of `ls`, and a file it can never see is worse than
        # a file it has to ask about.
        unclassified = [entry for entry in matched if entry.media is None]

        summary = plural(len(files), noun)
        if unclassified:
            summary += f", {len(unclassified)} unclassified"
        return Result(
            f"{noun} list",
            summary,
            {
                "count": len(files),
                "files": [entry.as_dict() for entry in files],
                "unclassified": [entry.as_dict() for entry in unclassified],
            },
            dry_run=dry_run,
        )

    @ssc_command(
        "show",
        help=f"Show one {noun} of an asset, with its lineage.",
        needs_workspace=True,
    )
    @click.option("--stage", default=None, help="Which stage to show. Defaults to the last.")
    @click.option("--no-doctor", is_flag=True, help="Report the file without measuring it.")
    @click.argument("key")
    def show_file(
        key: str,
        no_doctor: bool,
        stage: str | None,
        *,
        dry_run: bool,
        workspace: Workspace,
    ) -> Result:
        directory, record = resolve(workspace, key)
        candidates = [
            candidate
            for candidate in sorted(record.files, key=chain_order)
            if media_of(candidate.path) == noun
        ]
        if not candidates:
            raise UsageError(
                "no-file",
                f"{record.kind}/{record.key} records no {noun}",
                fix=f"ssc {noun} list {record.kind}",
            )

        if stage is None:
            target = candidates[-1]
        else:
            found = [candidate for candidate in candidates if candidate.stage == stage]
            if not found:
                known = ", ".join(candidate.stage for candidate in candidates)
                raise UsageError(
                    "unknown-stage",
                    f"{record.kind}/{record.key} has no {noun} at stage {stage!r}; it has: {known}",
                )
            target = found[0]

        entry = Entry(record.kind, record.key, directory, target)
        report, skipped = measure_or_say_why(entry, no_doctor=no_doctor)
        defects = "" if report is None else f", {plural(int(report['defects']), 'defect')}"

        return Result(
            f"{noun} show",
            f"{record.kind}/{record.key} at stage {target.stage}: {target.path}{defects}",
            {
                "file": entry.as_dict(),
                "lineage": [
                    Entry(record.kind, record.key, directory, ancestor).as_dict()
                    for ancestor in lineage(record, target)
                ],
                "doctor": report,
                "doctor_skipped": skipped,
            },
            dry_run=dry_run,
        )

    group = click.Group(
        noun,
        help=f"Observe the {noun}s in this workspace. Neither command writes anything.",
    )
    group.add_command(list_files)
    group.add_command(show_file)
    return group


def measure_or_say_why(
    entry: Entry, *, no_doctor: bool
) -> tuple[dict[str, Any] | None, str | None]:
    """`doctor` on the file, or `None` and the reason there is none (R3.8, R3.9, R3.10).

    Reported as two fields rather than as an absent key, because a caller reading JSON
    cannot tell a check that was not run from a check that found nothing — the same
    argument `doctor` itself settles by reporting a skipped finding with its reason.
    """
    if no_doctor:
        return None, "--no-doctor was given"
    if entry.media != "image":
        return None, f"doctor measures images, and {entry.record.path} is not one"

    # Resolved once and reused: `entry.file` re-runs the containment check on every
    # access, so testing one `Path` and opening another would let a link retargeted in
    # between be checked and then not read.
    target = entry.file
    if not target.exists():
        return None, f"{entry.record.path} is recorded but not on disk"

    # Imported here rather than at module scope: `doctor` pulls in numpy and Pillow, and
    # `list` — the command an agent runs most — has no use for either.
    from ssc.cli.commands.doctor import load_input, measure

    return measure(load_input(target)).as_dict(), None


image = build("image")
video = build("video")
