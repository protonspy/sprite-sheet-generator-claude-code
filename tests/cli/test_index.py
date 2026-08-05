"""The index model — specs/engine-index R1, R2, R3."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml
from conftest import load_meta, save_meta

from ssc.cli import index, kinds, meta
from ssc.cli import workspace as ws
from ssc.cli.errors import SscError
from ssc.cli.frames import encode
from ssc.cli.sidecar import AuthoredFrame, Box, Playback, Section

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


# plans/ssc-completion.md 3.1 — an authored frames block is one entry per frame, and the
# set decides whether its length is right.


def test_an_authored_block_matching_the_set() -> None:
    authored = (AuthoredFrame(markers=("footstep",)), AuthoredFrame())
    assert index.resolve_authored(authored, frames=2, where=WHERE) == authored


def test_nothing_authored_is_nothing_to_check() -> None:
    assert index.resolve_authored(None, frames=8, where=WHERE) is None


@pytest.mark.parametrize("entries", [1, 3])
def test_a_block_of_the_wrong_length_is_refused_with_both_counts(entries: int) -> None:
    authored = tuple(AuthoredFrame() for _ in range(entries))
    with pytest.raises(SscError) as raised:
        index.resolve_authored(authored, frames=2, where=WHERE)
    assert raised.value.code == "frames-block-mismatch"
    assert str(entries) in raised.value.message
    assert "2" in raised.value.message
    assert WHERE in raised.value.message


# plans/ssc-completion.md 3.2 — the alpha bounding box, derived and never authored.


def test_bounds_of_an_inset_figure() -> None:
    frame = np.zeros((8, 8, 4), dtype=np.uint8)
    frame[2:6, 3:5, :] = 255
    assert index.bounds_of(frame) == Box(x=3, y=2, width=2, height=4)


def test_bounds_of_a_fully_opaque_frame_is_the_frame() -> None:
    assert index.bounds_of(swatch(8, 8)) == Box(x=0, y=0, width=8, height=8)


def test_bounds_of_a_single_pixel() -> None:
    frame = np.zeros((8, 8, 4), dtype=np.uint8)
    frame[5, 6, :] = 255
    assert index.bounds_of(frame) == Box(x=6, y=5, width=1, height=1)


def test_a_transparent_frame_has_no_bounds() -> None:
    assert index.bounds_of(np.zeros((8, 8, 4), dtype=np.uint8)) is None


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


# R2.1, R2.2, R2.3 — one animation, as an engine addresses it.


def published(
    frames: list[np.ndarray],
    *,
    kind: str = "character",
    key: str = "hero",
    authored: tuple[AuthoredFrame, ...] | None = None,
    **playback: object,
) -> index.Published:
    return index.Published(
        kind=kind,
        key=key,
        stage="cut",
        frames=frames,
        playback=Playback(**playback),  # type: ignore[arg-type]
        authored=authored,
    )


def test_a_sheet_carries_its_cell_grid_frames_and_anchor() -> None:
    profile = kinds.BUILT_INS["character"]
    entry, pixels = index.build_sheet(published([swatch(), swatch(), swatch()]), profile)

    assert entry.cell == profile.cell
    # Three frames go near-square: two columns and two rows, with one cell left empty.
    assert (entry.columns, entry.rows) == (2, 2)
    assert entry.frames == 3
    assert pixels.shape == (2 * profile.cell[1], 2 * profile.cell[0], 4)
    assert entry.image == "sheets/character/hero.png"
    assert 0 <= entry.anchor[0] < profile.cell[0]
    assert 0 <= entry.anchor[1] < profile.cell[1]


def test_a_sheet_reports_an_anchor_its_frames_do_not_share() -> None:
    # R2.2 — the two frames put their pixels in different places, so no anchor is the set's.
    left, right = swatch(), swatch()
    tall = np.zeros((16, 16, 4), dtype=np.uint8)
    tall[0:4, 0:4] = (255, 0, 0, 255)
    other = np.zeros((16, 16, 4), dtype=np.uint8)
    other[12:16, 12:16] = (255, 0, 0, 255)
    entry, _ = index.build_sheet(published([tall, other]), kinds.BUILT_INS["character"])
    assert entry.aligned is False

    aligned, _ = index.build_sheet(published([left, right]), kinds.BUILT_INS["character"])
    assert aligned.aligned is True


def test_a_sheet_takes_its_frame_rate_from_the_kind_and_then_from_the_sidecar() -> None:
    profile = kinds.BUILT_INS["character"]
    silent, _ = index.build_sheet(published([swatch()]), profile)
    assert silent.fps == profile.fps
    assert silent.mode == "loop"

    declared, _ = index.build_sheet(published([swatch()], fps=8, mode="reverse"), profile)
    assert (declared.fps, declared.mode) == (8, "reverse")


def test_a_sheets_sections_are_resolved_against_its_frame_count() -> None:
    profile = kinds.BUILT_INS["character"]
    entry, _ = index.build_sheet(
        published([swatch()] * 4, sections=(Section("windup", 0, 1),)), profile
    )
    assert entry.as_dict()["playback"]["sections"] == [{"name": "windup", "first": 0, "last": 1}]

    with pytest.raises(SscError) as refused:
        index.build_sheet(published([swatch()] * 2, sections=(Section("windup", 0, 5),)), profile)
    assert refused.value.code == "section-out-of-range"


# plans/ssc-completion.md 3.3 — the per-frame data behind the index's schema: derived
# bounds always, authored boxes and markers carried and never invented.


def test_a_sheet_carries_derived_bounds_with_no_authoring_at_all() -> None:
    frame = np.zeros((8, 8, 4), dtype=np.uint8)
    frame[2:6, 3:5, :] = 255
    entry, _ = index.build_sheet(published([frame, swatch()]), kinds.BUILT_INS["character"])
    first, second = entry.as_dict()["per_frame"]
    assert first["bounds"] == {"x": 3, "y": 2, "width": 2, "height": 4}
    assert second["bounds"] == {"x": 0, "y": 0, "width": 8, "height": 8}
    # Nothing was authored, and nothing is invented.
    assert first["hitboxes"] == [] and first["hurtboxes"] == [] and first["markers"] == []


def test_a_sheet_carries_the_authored_block_frame_by_frame() -> None:
    authored = (
        AuthoredFrame(
            hitboxes=(Box(1, 2, 3, 4),),
            hurtboxes=(Box(0, 0, 8, 8),),
            markers=("footstep",),
        ),
        AuthoredFrame(),
    )
    entry, _ = index.build_sheet(
        published([swatch(), swatch()], authored=authored), kinds.BUILT_INS["character"]
    )
    first, second = entry.as_dict()["per_frame"]
    assert first["hitboxes"] == [{"x": 1, "y": 2, "width": 3, "height": 4}]
    assert first["hurtboxes"] == [{"x": 0, "y": 0, "width": 8, "height": 8}]
    assert first["markers"] == ["footstep"]
    assert second["hitboxes"] == [] and second["markers"] == []


def test_an_authored_block_of_the_wrong_length_refuses_the_sheet() -> None:
    with pytest.raises(SscError) as refused:
        index.build_sheet(
            published([swatch()] * 3, authored=(AuthoredFrame(),)),
            kinds.BUILT_INS["character"],
        )
    assert refused.value.code == "frames-block-mismatch"


def test_an_authored_block_on_a_kind_that_does_not_animate_is_skipped(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(space, "icon", "potion", single=swatch(), sidecar_text="frames:\n- markers: [a]\n")
    groups, skipped = index.gather(space)
    assert groups == []
    assert len(skipped) == 1
    assert "does not animate" in skipped[0].why


def test_a_frame_larger_than_its_kinds_cell_is_refused() -> None:
    # Widening the cell instead would hand an engine a cell size the project never declared,
    # which cuts every other sprite of that kind in the wrong place.
    with pytest.raises(SscError) as refused:
        index.build_sheet(published([swatch(width=200, height=200)]), kinds.BUILT_INS["character"])
    assert refused.value.code == "frame-larger-than-cell"


def test_a_sheet_as_a_dict_nests_playback() -> None:
    entry, _ = index.build_sheet(
        published([swatch(), swatch()], fps=10, mode="ping-pong"), kinds.BUILT_INS["character"]
    )
    emitted = entry.as_dict()
    assert emitted["playback"] == {"fps": 10, "mode": "ping-pong", "sections": []}
    assert emitted["cell"] == {"width": 64, "height": 64}
    assert set(emitted) == {
        "kind",
        "key",
        "image",
        "cell",
        "columns",
        "rows",
        "frames",
        "anchor",
        "aligned",
        "playback",
        "per_frame",
    }


# R3.1, R3.2, R3.3 — atlases, tilesets and the panels among them.


def group(kind: str, assets: list[index.Published], **overrides: object) -> index.Group:
    profile = kinds.BUILT_INS[kind]
    if overrides:
        profile = replace(profile, **overrides)  # type: ignore[arg-type]
    return index.Group(
        kind=kind, profile=profile, artefact=index.artefact_of(profile), assets=assets
    )


def test_an_entry_is_named_after_its_asset_and_numbered_only_when_it_has_to_be() -> None:
    assert index.entry_ids(published([swatch()], kind="icon", key="potion")) == ["potion"]
    assert index.entry_ids(published([swatch(), swatch()], kind="icon", key="potion")) == [
        "potion_0000",
        "potion_0001",
    ]


def test_an_atlas_carries_a_rect_and_an_anchor_per_asset() -> None:
    icons = group(
        "icon",
        [
            published([swatch(16, 16)], kind="icon", key="potion"),
            published([swatch(32, 8)], kind="icon", key="sword"),
        ],
    )
    entry, pixels = index.build_atlas(icons, padding=2, extrude=1)

    assert entry.image == "atlases/icon.png"
    assert (entry.padding, entry.extrude) == (2, 1)
    assert pixels.shape == (entry.height, entry.width, 4)
    by_id = {item.id: item for item in entry.items}
    assert set(by_id) == {"potion", "sword"}
    assert (by_id["potion"].rect.width, by_id["potion"].rect.height) == (16, 16)
    assert (by_id["sword"].rect.width, by_id["sword"].rect.height) == (32, 8)
    # No entry overlaps another, which is the one thing a rect per entry has to promise.
    assert by_id["potion"].rect.as_dict() != by_id["sword"].rect.as_dict()


def test_only_a_kind_that_declares_nineslice_carries_borders() -> None:
    panels = group("ui", [published([swatch(32, 32)], kind="ui", key="panel")])
    entry, _ = index.build_atlas(panels)
    borders = entry.items[0].as_dict()["borders"]
    assert set(borders) == {"left", "right", "top", "bottom"}
    assert all(value >= 1 for value in borders.values())

    icons = group("icon", [published([swatch(16, 16)], kind="icon", key="potion")])
    plain, _ = index.build_atlas(icons)
    assert "borders" not in plain.items[0].as_dict()


def test_a_tileset_carries_the_tile_size_the_grid_and_every_id() -> None:
    cell = kinds.BUILT_INS["tile"].cell
    tiles = group(
        "tile",
        [
            published([swatch(*cell)], kind="tile", key="grass"),
            published([swatch(*cell)], kind="tile", key="stone"),
            published([swatch(*cell)], kind="tile", key="water"),
        ],
    )
    entry, pixels = index.build_tileset(tiles)

    assert entry.tile == cell
    assert (entry.columns, entry.rows) == (2, 2)
    assert pixels.shape == (2 * cell[1], 2 * cell[0], 4)
    assert [(tile.id, tile.column, tile.row) for tile in entry.tiles] == [
        ("grass", 0, 0),
        ("stone", 1, 0),
        ("water", 0, 1),
    ]


def test_a_tile_that_is_not_the_cell_is_refused() -> None:
    cell = kinds.BUILT_INS["tile"].cell
    tiles = group(
        "tile",
        [
            published([swatch(*cell)], kind="tile", key="grass"),
            published([swatch(cell[0] - 4, cell[1])], kind="tile", key="stone"),
        ],
    )
    with pytest.raises(SscError) as refused:
        index.build_tileset(tiles)
    assert refused.value.code == "tile-not-the-cell"
    assert "stone" in refused.value.message


def test_a_frame_set_arrives_in_filename_order(tmp_path: Path) -> None:
    space = workspace(tmp_path)
    asset(space, "character", "hero", frames=[swatch(value=1), swatch(value=2), swatch(value=3)])
    groups, _ = index.gather(space)
    frames = groups[0].assets[0].frames
    assert [int(frame[0, 0, 0]) for frame in frames] == [1, 2, 3]
