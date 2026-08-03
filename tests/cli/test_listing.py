"""Reading the workspace back — specs/asset-listing R1, R2.6, R3.2, R3.3, R3.6, R3.7, R4."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import save_meta

from ssc.cli import listing, meta, workspace
from ssc.cli.errors import SscError, UsageError


def make_asset(root: Path, kind: str, key: str) -> Path:
    directory = root / "assets" / kind / key
    directory.mkdir(parents=True)
    save_meta(directory, meta.AssetMeta(key=key, kind=kind))
    return directory


def add(directory: Path, path: str, stage: str, *, parents: list[str] | None = None) -> None:
    record = meta.load(directory)
    meta.record(
        record,
        path=path,
        stage=stage,
        file_class="derived",
        data=b"",
        produced_by=meta.Provenance(command="tool snap"),
        derived_from=parents or [],
    )
    save_meta(directory, record)


# R1.1, R1.2 — the medium comes from the extension, and "neither" is an answer.


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("001_anchor.png", "image"),
        ("002_anchor.SNAP.PNG", "image"),
        ("003_walk.webp", "image"),
        ("004_preview.gif", "image"),
        ("001_clip.mp4", "video"),
        ("002_clip.webm", "video"),
        ("frames", None),
        ("003_boxes.json", None),
    ],
)
def test_media_comes_from_the_extension(path: str, expected: str | None) -> None:
    assert listing.media_of(path) == expected


# R2.6 — kind, then key, then position in the chain.


def test_entries_are_ordered_by_kind_then_key_then_chain(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    space = workspace.Workspace(root=tmp_path)

    tile = make_asset(tmp_path, "tile", "grass")
    add(tile, "001_grass.png", "raw")
    hero = make_asset(tmp_path, "character", "hero")
    add(hero, "002_hero.snap.png", "snap")
    add(hero, "001_hero.png", "raw")
    villain = make_asset(tmp_path, "character", "villain")
    add(villain, "001_villain.png", "raw")

    found = [(entry.kind, entry.key, entry.record.path) for entry in listing.entries(space)]
    assert found == [
        ("character", "hero", "001_hero.png"),
        ("character", "hero", "002_hero.snap.png"),
        ("character", "villain", "001_villain.png"),
        ("tile", "grass", "001_grass.png"),
    ]


def test_a_file_without_a_prefix_sorts_after_the_chain(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    space = workspace.Workspace(root=tmp_path)
    hero = make_asset(tmp_path, "character", "hero")
    add(hero, "frames", "frames")
    add(hero, "001_hero.png", "raw")

    assert [entry.record.path for entry in listing.entries(space)] == ["001_hero.png", "frames"]


def test_a_workspace_with_no_assets_lists_nothing(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    assert listing.entries(workspace.Workspace(root=tmp_path)) == []


# R3.2, R3.3 — an asset is addressed by kind and key, or by key alone when that is enough.


def test_an_asset_resolves_from_kind_and_key(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    space = workspace.Workspace(root=tmp_path)
    make_asset(tmp_path, "character", "hero")
    make_asset(tmp_path, "tile", "hero")

    directory, record = listing.resolve(space, "tile/hero")
    assert (record.kind, record.key) == ("tile", "hero")
    assert directory == tmp_path / "assets" / "tile" / "hero"


def test_a_bare_key_resolves_when_only_one_kind_has_it(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    space = workspace.Workspace(root=tmp_path)
    make_asset(tmp_path, "character", "hero")

    _, record = listing.resolve(space, "hero")
    assert (record.kind, record.key) == ("character", "hero")


def test_a_bare_key_in_two_kinds_is_refused_naming_both(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    space = workspace.Workspace(root=tmp_path)
    make_asset(tmp_path, "character", "hero")
    make_asset(tmp_path, "tile", "hero")

    with pytest.raises(UsageError) as refused:
        listing.resolve(space, "hero")
    assert refused.value.code == "ambiguous-key"
    assert "character" in refused.value.message
    assert "tile" in refused.value.message
    assert refused.value.exit_code == 2


def test_an_unknown_asset_is_refused_with_the_command_that_creates_one(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    space = workspace.Workspace(root=tmp_path)

    for address in ("hero", "character/hero"):
        with pytest.raises(UsageError) as refused:
            listing.resolve(space, address)
        assert refused.value.code == "no-asset"
        assert refused.value.fix is not None
        assert refused.value.fix.startswith("ssc asset new hero")


def test_an_address_of_three_segments_is_not_an_asset(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    with pytest.raises(UsageError) as refused:
        listing.resolve(workspace.Workspace(root=tmp_path), "a/b/c")
    assert refused.value.code == "invalid-address"


# R3.6, R3.7 — the lineage, roots first, and the cycle a hand-edited record can carry.


def stage_in(path: str) -> str:
    """`002_hero.snap.png` is stage `snap`; `001_hero.png` is stage `hero`."""
    parts = path.split(".")
    return parts[-2] if len(parts) > 2 else parts[0].split("_", 1)[-1]


def build_meta(*files: tuple[str, list[str]]) -> meta.AssetMeta:
    return meta.AssetMeta(
        key="hero",
        kind="character",
        files=[
            meta.FileRecord(
                path=path,
                stage=stage_in(path),
                **{"class": "derived"},
                sha256="0" * 64,
                produced_by=meta.Provenance(command="tool snap"),
                derived_from=parents,
            )
            for path, parents in files
        ],
    )


def test_lineage_walks_the_chain_back_to_its_root() -> None:
    record = build_meta(
        ("001_hero.png", []),
        ("002_hero.snap.png", ["001_hero.png"]),
        ("003_hero.nobg.png", ["002_hero.snap.png"]),
    )
    walked = listing.lineage(record, record.stage("nobg"))
    assert [entry.path for entry in walked] == ["001_hero.png", "002_hero.snap.png"]


def test_lineage_of_a_root_file_is_empty() -> None:
    record = build_meta(("001_hero.png", []))
    assert listing.lineage(record, record.stage("hero")) == []


def test_lineage_reports_each_ancestor_once_when_two_paths_share_one() -> None:
    record = build_meta(
        ("001_hero.png", []),
        ("002_hero.snap.png", ["001_hero.png"]),
        ("003_hero.nobg.png", ["001_hero.png"]),
        ("004_hero.sheet.png", ["002_hero.snap.png", "003_hero.nobg.png"]),
    )
    walked = listing.lineage(record, record.stage("sheet"))
    assert [entry.path for entry in walked] == [
        "001_hero.png",
        "002_hero.snap.png",
        "003_hero.nobg.png",
    ]


def test_an_ancestor_naming_no_record_is_skipped_rather_than_refused() -> None:
    record = build_meta(("001_hero.png", ["000_gone.png"]))
    assert listing.lineage(record, record.stage("hero")) == []


def test_a_lineage_cycle_is_refused_naming_the_file_it_closes_on() -> None:
    record = build_meta(
        ("001_hero.png", ["002_hero.snap.png"]),
        ("002_hero.snap.png", ["001_hero.png"]),
    )
    with pytest.raises(SscError) as refused:
        listing.lineage(record, record.stage("snap"))
    assert refused.value.code == "lineage-cycle"
    assert refused.value.exit_code == 1
    assert "002_hero.snap.png" in refused.value.message


def test_a_file_deriving_from_itself_is_a_cycle() -> None:
    record = build_meta(("001_hero.png", ["001_hero.png"]))
    with pytest.raises(SscError) as refused:
        listing.lineage(record, record.stage("hero"))
    assert refused.value.code == "lineage-cycle"


# R4.1, R4.2 — a validated string is not a validated target, because a link moves.


def test_an_asset_directory_reached_through_a_link_is_refused(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    workspace.create(tmp_path)
    elsewhere = tmp_path / "outside" / "hero"
    elsewhere.mkdir(parents=True)
    save_meta(elsewhere, meta.AssetMeta(key="hero", kind="character"))
    (tmp_path / "assets" / "character").mkdir(parents=True)
    link_dir(tmp_path / "assets" / "character" / "hero", elsewhere)

    with pytest.raises(SscError) as refused:
        listing.entries(workspace.Workspace(root=tmp_path))
    assert refused.value.code == "asset-escapes-workspace"
    assert refused.value.exit_code == 1


def test_resolving_by_kind_and_key_refuses_a_linked_asset_directory(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """The branch that never touches `asset_dirs`, and so needs the check of its own."""
    workspace.create(tmp_path)
    elsewhere = tmp_path / "outside" / "hero"
    elsewhere.mkdir(parents=True)
    save_meta(elsewhere, meta.AssetMeta(key="hero", kind="character"))
    (tmp_path / "assets" / "character").mkdir(parents=True)
    link_dir(tmp_path / "assets" / "character" / "hero", elsewhere)

    with pytest.raises(SscError) as refused:
        listing.resolve(workspace.Workspace(root=tmp_path), "character/hero")
    assert refused.value.code == "asset-escapes-workspace"


def test_a_file_reached_through_a_linked_subdirectory_is_refused(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """`frames/` is a legitimate recorded segment, which is what makes it worth linking."""
    workspace.create(tmp_path)
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    (elsewhere / "paid-for.png").write_bytes(b"not reproducible")
    directory = make_asset(tmp_path, "character", "hero")
    link_dir(directory / "frames", elsewhere)
    add(directory, "frames/paid-for.png", "frames")

    entry = listing.entries(workspace.Workspace(root=tmp_path))[0]
    with pytest.raises(SscError) as refused:
        _ = entry.file
    assert refused.value.code == "path-escapes-asset"
    assert (elsewhere / "paid-for.png").read_bytes() == b"not reproducible"


@pytest.mark.skipif(sys.platform == "win32", reason="creating a symlink needs a privilege")
def test_a_recorded_file_that_is_a_symlink_out_is_refused_before_it_is_opened(
    tmp_path: Path,
) -> None:
    workspace.create(tmp_path)
    victim = tmp_path / "paid-for.png"
    victim.write_bytes(b"not reproducible")
    directory = make_asset(tmp_path, "character", "hero")
    (directory / "001_hero.png").symlink_to(victim)
    add(directory, "001_hero.png", "anchor")

    entry = listing.entries(workspace.Workspace(root=tmp_path))[0]
    with pytest.raises(SscError) as refused:
        _ = entry.file
    assert refused.value.code == "path-escapes-asset"
    assert victim.read_bytes() == b"not reproducible"


# workspace-foundation R2.5 — enforced on the asset a caller addressed, which is where
# refusing changes an outcome, and not on the scan, which would take the workspace down.


@pytest.mark.parametrize("address", ["character/hero", "hero"])
def test_addressing_an_asset_that_holds_a_stray_subdirectory_is_refused(
    address: str, tmp_path: Path
) -> None:
    """Both branches of `resolve`: naming the kind, and letting a bare key find it."""
    workspace.create(tmp_path)
    directory = make_asset(tmp_path, "character", "hero")
    (directory / "notes").mkdir()

    with pytest.raises(SscError) as refused:
        listing.resolve(workspace.Workspace(root=tmp_path), address)
    assert refused.value.code == "unexpected-subdirectory"
    assert "notes" in refused.value.message


def test_one_malformed_asset_does_not_take_the_listing_down_with_it(tmp_path: Path) -> None:
    """The blast radius the code review found: `entries` scans every asset, so refusing
    there means one stray directory anywhere stops `list`, `clean`, and every unrelated
    asset. The read paths in this module skip what they cannot use; this one does too."""
    workspace.create(tmp_path)
    make_asset(tmp_path, "character", "hero")
    (make_asset(tmp_path, "tile", "grass") / "notes").mkdir()

    listed = [directory.name for directory in listing.asset_dirs(workspace.Workspace(tmp_path))]

    assert listed == ["hero", "grass"]
    # And the healthy one is still reachable by name while the other is not.
    assert listing.resolve(workspace.Workspace(tmp_path), "character/hero")[1].key == "hero"


def test_frames_is_the_one_subdirectory_that_belongs(tmp_path: Path) -> None:
    """The other half of R2.5: `frames/` is the set, and checking the layout must not
    refuse the one asset shape the whole pipeline produces."""
    workspace.create(tmp_path)
    directory = make_asset(tmp_path, "character", "hero")
    (directory / "frames").mkdir()

    assert listing.addressed(workspace.Workspace(root=tmp_path), directory) == directory


def test_an_asset_directory_that_stays_inside_is_allowed(tmp_path: Path) -> None:
    """The other half of R4.1: the check must not refuse an ordinary workspace, including
    one whose `assets/` is itself somewhere else — that is the root both sides resolve
    against, not an escape from it."""
    workspace.create(tmp_path)
    make_asset(tmp_path, "character", "hero")
    assert [directory.name for directory in listing.asset_dirs(workspace.Workspace(tmp_path))] == [
        "hero"
    ]


# workspace-foundation R3.7 — `bound` is `under_assets` for a caller about to write: the
# same refusal, and something to write through that the refusal actually covers.


def test_bound_hands_back_a_directory_to_write_through(tmp_path: Path) -> None:
    workspace.create(tmp_path)
    directory = make_asset(tmp_path, "character", "hero")

    with listing.bound(workspace.Workspace(root=tmp_path), directory) as held:
        held.write_new("001_hero.png", b"pixels")

    assert (directory / "001_hero.png").read_bytes() == b"pixels"


def test_bound_refuses_a_linked_asset_directory(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """The writing route's version of the same refusal, and the one that matters most:
    this is the branch where a followed link means a file written outside the workspace
    rather than one read from outside it."""
    workspace.create(tmp_path)
    elsewhere = tmp_path / "outside" / "hero"
    elsewhere.mkdir(parents=True)
    (tmp_path / "assets" / "character").mkdir(parents=True)
    link_dir(tmp_path / "assets" / "character" / "hero", elsewhere)

    with pytest.raises(SscError) as refused:
        listing.bound(workspace.Workspace(root=tmp_path), tmp_path / "assets/character/hero")
    assert refused.value.code == "asset-escapes-workspace"
    assert list(elsewhere.iterdir()) == []


def test_bound_does_not_refuse_a_stray_subdirectory(tmp_path: Path) -> None:
    """Deliberately not `addressed`: `clean` writes a record back for every asset, so the
    layout check here would let one stray directory abort a sweep over the others."""
    workspace.create(tmp_path)
    directory = make_asset(tmp_path, "character", "hero")
    (directory / "notes").mkdir()

    with listing.bound(workspace.Workspace(root=tmp_path), directory) as held:
        held.write_new("001_hero.png", b"pixels")

    assert (directory / "001_hero.png").exists()
