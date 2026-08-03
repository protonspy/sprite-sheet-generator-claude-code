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

from pydantic import BaseModel, ConfigDict, Field

from ssc.cli.atomic import replace
from ssc.cli.errors import SscError, UsageError

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


class AssetMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: int = Field(default=SCHEMA, alias="schema")
    key: str
    kind: str
    created_at: str = Field(default_factory=now)
    files: list[FileRecord] = Field(default_factory=list)

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
        """The next unused number. Prefixes are never reused, so deleting a `derived`
        file and recomputing it does not shuffle what came after."""
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
    return AssetMeta.model_validate_json(target.read_bytes())


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
