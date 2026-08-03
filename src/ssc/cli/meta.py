"""`meta.json` — what each file in an asset is, and where it came from.

This is the record the rest of the tool reads instead of parsing filenames. A file is
addressed by its **stage**, never by its numbered prefix (R2.4, R3.3): inserting one step
in the middle of a chain would otherwise renumber everything downstream and break every
script that hard-coded `003`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ssc.cli.atomic import replace
from ssc.cli.errors import SscError, UsageError
from ssc.cli.names import check_name, check_relative_path

SCHEMA = 1
META_NAME = "meta.json"

#: `frames/` is the only subdirectory an asset may have, because a frame set is the one
#: thing inside an asset that is genuinely a set rather than a step (R2.5).
FRAMES_DIR = "frames"

FileClass = Literal["source", "derived", "output"]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Provenance(BaseModel):
    """How a file came to exist. `cache_key` is `None` for anything not computed."""

    model_config = ConfigDict(extra="forbid")

    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    cache_key: str | None = None


class FileRecord(BaseModel):
    """One file in an asset.

    `path` is relative to the asset directory, so an asset survives being moved. `class`
    is the field — and the only field — that `ssc clean` reads.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    path: str
    stage: str
    file_class: FileClass = Field(alias="class")
    sha256: str
    produced_by: Provenance
    derived_from: list[str] = Field(default_factory=list)
    written_at: str = Field(default_factory=now)

    @field_validator("path", "derived_from", mode="after")
    @classmethod
    def _paths_stay_inside_the_asset(cls, value: str | list[str]) -> str | list[str]:
        """`meta.json` survives hand-editing and a crash, and `ssc clean` deletes what it
        names. A recorded `../../..` is a delete outside the workspace, so the constraint
        belongs on the model rather than on each reader."""
        for candidate in [value] if isinstance(value, str) else value:
            try:
                check_relative_path(candidate, "a recorded path")
            except UsageError as refused:
                # Re-raised as a ValueError so pydantic collects it: a bad path found
                # while *loading* is a corrupt file (exit 1), not a caller mistake, and
                # `load` below is what turns it into that.
                raise ValueError(refused.message) from refused
        return value


class AssetMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=SCHEMA, alias="schema")
    key: str
    kind: str
    created_at: str = Field(default_factory=now)
    files: list[FileRecord] = Field(default_factory=list)

    @field_validator("key", "kind", mode="after")
    @classmethod
    def _names_are_names(cls, value: str) -> str:
        """Both end up as directory names under `assets/`, so both are single segments."""
        try:
            return check_name(value, "a recorded name")
        except UsageError as refused:
            raise ValueError(refused.message) from refused

    def stage(self, name: str) -> FileRecord:
        """Resolve a stage to its file without the caller counting prefixes (R3.3)."""
        for record in self.files:
            if record.stage == name:
                return record
        known = ", ".join(sorted(record.stage for record in self.files)) or "none yet"
        raise UsageError(
            "unknown-stage",
            f"{self.kind}/{self.key} has no stage {name!r}; it has: {known}",
        )

    def next_prefix(self) -> int:
        """One past the highest prefix on record.

        The guarantee is narrower than "never reused", and it is worth stating exactly:
        **deleting a file never renumbers the files that remain.** A gap in the middle
        stays a gap, which is what keeps a chain readable after `ssc clean`. The number
        freed by deleting the *last* file is handed out again, and that is harmless
        precisely because R2.4 makes the prefix presentation and never an address.
        """
        used = [prefix for prefix in (prefix_of(record.path) for record in self.files) if prefix]
        return max(used, default=0) + 1


def prefix_of(path: str) -> int | None:
    head = path.split("_", 1)[0]
    return int(head) if head.isdigit() else None


def filename(prefix: int, label: str, stages: list[str], extension: str) -> str:
    """`002_anchor_s.snap.png` — the number orders one `ls`, the stages read as a chain."""
    suffix = "".join(f".{stage}" for stage in stages)
    return f"{prefix:03d}_{label}{suffix}.{extension.lstrip('.')}"


def path_of(asset_dir: Path) -> Path:
    return asset_dir / META_NAME


def load(asset_dir: Path) -> AssetMeta:
    target = path_of(asset_dir)
    if not target.is_file():
        raise UsageError(
            "no-asset",
            f"{asset_dir} holds no {META_NAME}",
            fix="ssc asset new <key> --kind <kind>",
        )
    try:
        return AssetMeta.model_validate_json(target.read_bytes())
    except ValidationError as invalid:
        # A record ssc will not act on beats a record it half-believes: `clean` deletes
        # what this file names, so a malformed one stops the command rather than being
        # repaired into something plausible.
        # The reason is in hand; reporting only a count would send an operator to "fix it
        # against the schema" without saying what in the schema is wrong.
        problems = "; ".join(
            f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg']}"
            for problem in invalid.errors()
        )
        raise SscError(
            "meta-invalid",
            f"{target} is not a valid {META_NAME}: {problems}",
            fix="fix it by hand, or restore it from git",
        ) from invalid


def save(asset_dir: Path, meta: AssetMeta) -> Path:
    """Rewritten whole, atomically (R3.6). At tens of files per asset the cost is nothing
    and the failure mode — half a record — is the one worth spending to avoid."""
    payload = meta.model_dump_json(indent=2, by_alias=True) + "\n"
    return replace(path_of(asset_dir), payload.encode())


def record(
    meta: AssetMeta,
    *,
    path: str,
    stage: str,
    file_class: FileClass,
    data: bytes,
    produced_by: Provenance,
    derived_from: list[str] | None = None,
) -> FileRecord:
    """Add a file to the record, refusing a stage the asset already has (R3.4).

    Two files sharing a stage would make `--stage nobg` ambiguous, and an ambiguity
    resolved by picking the first match is the kind that goes unnoticed for months.
    """
    # Checked here as well as on the model, so a caller passing a path that walks out of
    # the asset gets the usage error it is, rather than a validation error from pydantic.
    check_relative_path(path)
    check_name(stage, "stage")
    for existing in meta.files:
        if existing.stage == stage:
            raise UsageError(
                "stage-taken",
                f"{meta.kind}/{meta.key} already records stage {stage!r} as {existing.path}",
                fix="choose another stage name, or ssc clean if that file is derived",
            )
        if existing.path == path:
            raise SscError("file-recorded", f"{path} is already recorded in {META_NAME}")

    entry = FileRecord(
        path=path,
        stage=stage,
        file_class=file_class,
        sha256=digest(data),
        produced_by=produced_by,
        derived_from=derived_from or [],
    )
    meta.files.append(entry)
    return entry


def check_layout(asset_dir: Path) -> None:
    """`frames/` and nothing else (R2.5)."""
    unexpected = sorted(
        child.name for child in asset_dir.iterdir() if child.is_dir() and child.name != FRAMES_DIR
    )
    if unexpected:
        raise SscError(
            "unexpected-subdirectory",
            f"{asset_dir} holds {', '.join(unexpected)}; "
            f"only {FRAMES_DIR}/ belongs inside an asset",
            fix=f"move it out, or put its files in {FRAMES_DIR}/",
        )
