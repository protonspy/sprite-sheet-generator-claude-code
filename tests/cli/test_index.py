"""The index model — specs/engine-index R1, R2, R3."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml
from conftest import load_meta, save_meta

from ssc.cli import index, kinds, meta
from ssc.cli import workspace as ws
from ssc.cli.errors import SscError
from ssc.cli.frames import encode
from ssc.cli.sidecar import Section

WHERE = "character/hero-attack"


def swatch(width: int = 8, height: int = 8, value: int = 200) -> np.ndarray:
    """A solid opaque block. Its pixels never matter here; its size always does."""
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :] = (value, value, value, 255)
    return image


def asset(
    space: ws.Workspace,
    kind: str,
    key: str,
    *,
    frames: list[np.ndarray] | None = None,
    single: np.ndarray | None = None,
    stage: str = "cut",
    sidecar_text: str | None = None,
) -> Path:
    """One asset on disk: either a frame set under `frames/<stage>/` or one image."""
    directory = space.asset_dir(kind, key)
    directory.mkdir(parents=True, exist_ok=True)
    record = meta.AssetMeta(key=key, kind=kind)

    if frames is not None:
        into = directory / meta.FRAMES_DIR / stage
        into.mkdir(parents=True)
        payload = b""
        for number, image in enumerate(frames, start=1):
            data = encode(image)
            (into / f"{number:03d}.png").write_bytes(data)
            payload += data
        meta.record(
            record,
            path=f"{meta.FRAMES_DIR}/{stage}",
            stage=stage,
            file_class="derived",
            data=payload,
            produced_by=meta.Provenance(command="test"),
        )
    if single is not None:
        data = encode(single)
        (directory / f"001_{key}.png").write_bytes(data)
        meta.record(
            record,
            path=f"001_{key}.png",
            stage=stage,
            file_class="derived",
            data=data,
            produced_by=meta.Provenance(command="test"),
        )

    if sidecar_text is not None:
        (directory / "asset.yaml").write_text(sidecar_text, encoding="utf-8")
    save_meta(directory, record)
    return directory


def workspace(tmp_path: Path, declared: dict | None = None) -> ws.Workspace:
    space = ws.create(tmp_path)
    if declared:
        space.config_path.write_text(
            yaml.safe_dump({"schema": 1, "kinds": declared}), encoding="utf-8"
        )
    return space


# R2.4, R2.5 — a section is a pair of inclusive frame numbers, and the set decides whether
# it is a real one. Written before `resolve_sections` existed, and watched fail.


def test_sections_of_a_set_that_has_them() -> None:
    sections = (Section("hit", 3, 4), Section("windup", 0, 2))
    assert index.resolve_sections(sections, frames=8, where=WHERE) == sections


def test_a_section_may_cover_the_whole_set() -> None:
    # Inclusive at both ends: over eight frames the last one is 7, not 8. This is the
    # off-by-one the requirement exists to pin down.
    sections = (Section("all", 0, 7),)
    assert index.resolve_sections(sections, frames=8, where=WHERE) == sections


def test_a_set_with_no_sections() -> None:
    assert index.resolve_sections((), frames=8, where=WHERE) == ()


def test_a_single_frame_section() -> None:
    sections = (Section("impact", 4, 4),)
    assert index.resolve_sections(sections, frames=8, where=WHERE) == sections


def refusal(section: Section, frames: int) -> SscError:
    with pytest.raises(SscError) as raised:
        index.resolve_sections((section,), frames=frames, where=WHERE)
    assert raised.value.code == "section-out-of-range"
    # R2.5 — the section and the count, because "out of range" without both is a message
    # that sends the author back to count the frames themselves.
    assert section.name in raised.value.message
    assert str(frames) in raised.value.message
    assert WHERE in raised.value.message
    return raised.value


def test_a_last_frame_one_past_the_end() -> None:
    refusal(Section("hit", 3, 8), frames=8)


def test_a_first_frame_past_the_end() -> None:
    refusal(Section("hit", 9, 9), frames=8)


def test_any_section_at_all_over_an_empty_set() -> None:
    refusal(Section("hit", 0, 0), frames=0)


def test_the_refusal_names_the_first_section_that_is_wrong() -> None:
    with pytest.raises(SscError) as raised:
        index.resolve_sections(
            (Section("early", 0, 2), Section("late", 6, 9)), frames=8, where=WHERE
        )
    assert "late" in raised.value.message
    assert "early" not in raised.value.message


# R1.2 — which artefact a kind gives an engine, read off the profile.


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("character", "sheet"), ("icon", "atlas"), ("tile", "tileset"), ("ui", "atlas")],
)
def test_the_artefact_a_kind_produces(kind: str, expected: str) -> None:
    assert index.artefact_of(kinds.BUILT_INS[kind]) == expected


def test_a_kind_that_animates_is_a_sheet_whatever_its_atlas_layout() -> None:
    # An animation is addressed by frame number, so `atlas_layout` has nothing to say about
    # it. Asserted because the profile carries both fields and the order of the two checks
    # is the whole of the rule.
    animating_bin = kinds.Profile(name="ghost", animates=True, atlas_layout="bin")
    assert index.artefact_of(animating_bin) == "sheet"


# R1.1, R1.3, R1.5 — walking the workspace.


def test_every_asset_is_grouped_by_its_kind(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(space, "character", "hero", frames=[swatch(), swatch()])
    asset(space, "icon", "potion", single=swatch())
    asset(space, "icon", "sword", single=swatch())

    groups, skipped = index.gather(space)
    assert skipped == []
    assert [(group.kind, [one.key for one in group.assets]) for group in groups] == [
        ("character", ["hero"]),
        ("icon", ["potion", "sword"]),
    ]
    assert [group.artefact for group in groups] == ["sheet", "atlas"]


def test_the_last_recorded_image_stage_is_the_published_one(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    directory = asset(space, "icon", "potion", single=swatch(), stage="gen")
    # A second, later file on the same asset: the end of the chain is what gets published.
    held = load_meta(directory)
    later = encode(swatch(value=10))
    (directory / "002_potion.nobg.png").write_bytes(later)
    meta.record(
        held,
        path="002_potion.nobg.png",
        stage="nobg",
        file_class="derived",
        data=later,
        produced_by=meta.Provenance(command="test"),
    )
    save_meta(directory, held)

    groups, _ = index.gather(space)
    assert groups[0].assets[0].stage == "nobg"


def test_a_named_stage_is_published_instead(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(space, "icon", "potion", single=swatch(), stage="gen")
    groups, skipped = index.gather(space, stage="gen")
    assert groups[0].assets[0].stage == "gen"
    assert skipped == []


def test_an_asset_without_the_named_stage_is_skipped(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(space, "icon", "potion", single=swatch(), stage="gen")
    groups, skipped = index.gather(space, stage="nobg")
    assert groups == []
    assert [(one.kind, one.key) for one in skipped] == [("icon", "potion")]
    assert "nobg" in skipped[0].why


def test_an_asset_with_nothing_publishable_is_skipped_and_the_rest_are_indexed(
    tmp_path: Path,
) -> None:
    space = workspace(tmp_path)
    empty = space.asset_dir("icon", "unmade")
    empty.mkdir(parents=True)
    save_meta(empty, meta.AssetMeta(key="unmade", kind="icon"))
    asset(space, "icon", "potion", single=swatch())

    groups, skipped = index.gather(space)
    assert [one.key for one in groups[0].assets] == ["potion"]
    assert [one.key for one in skipped] == ["unmade"]
    assert "records no image" in skipped[0].why


def test_a_recorded_file_that_is_not_there_is_skipped_with_the_reason(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    directory = asset(space, "icon", "potion", single=swatch())
    (directory / "001_potion.png").unlink()

    groups, skipped = index.gather(space)
    assert groups == []
    assert "stage" in skipped[0].why


def test_an_asset_of_a_kind_nobody_declared_is_skipped(tmp_path: Path) -> None:
    # A directory made by hand, or one left behind by a `kinds:` entry somebody removed.
    # The other kinds still index.
    space = workspace(tmp_path)
    asset(space, "relic", "urn", single=swatch())
    asset(space, "icon", "potion", single=swatch())

    groups, skipped = index.gather(space)
    assert [group.kind for group in groups] == ["icon"]
    assert [one.key for one in skipped] == ["urn"]
    assert "relic" in skipped[0].why


def test_a_malformed_kinds_block_fails_the_run_rather_than_skipping_everything(
    tmp_path: Path,
) -> None:
    # Forty identical skips would bury the one line that needs fixing.
    space = workspace(tmp_path, {"relic": {"cell": "not-a-size"}})
    asset(space, "icon", "potion", single=swatch())
    with pytest.raises(SscError) as refused:
        index.gather(space)
    assert refused.value.code == "invalid-kind"


def test_the_sidecar_travels_with_the_asset(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(
        space,
        "character",
        "hero",
        frames=[swatch(), swatch()],
        sidecar_text="playback:\n  fps: 8\n  mode: reverse\n",
    )
    groups, _ = index.gather(space)
    assert groups[0].assets[0].playback.fps == 8
    assert groups[0].assets[0].playback.mode == "reverse"


def test_a_frame_set_arrives_in_filename_order(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(space, "character", "hero", frames=[swatch(value=1), swatch(value=2), swatch(value=3)])
    groups, _ = index.gather(space)
    frames = groups[0].assets[0].frames
    assert [int(frame[0, 0, 0]) for frame in frames] == [1, 2, 3]
