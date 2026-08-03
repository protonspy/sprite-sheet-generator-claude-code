"""R3.5 · R3.6 · R3.7 — nothing overwrites, the one file that is rewritten is rewritten
whole, and a write goes to the directory that was checked rather than to whatever the path
resolves to by the time it happens."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from ssc.cli.atomic import Directory, replace, write_new
from ssc.cli.errors import SscError


def test_write_new_creates_the_file_and_any_missing_parent(tmp_path: Path) -> None:
    target = tmp_path / "assets/character/hero/001_anchor.png"
    write_new(target, b"pixels")
    assert target.read_bytes() == b"pixels"


def test_write_new_refuses_an_existing_path(tmp_path: Path) -> None:
    target = tmp_path / "001_anchor.png"
    write_new(target, b"first")
    with pytest.raises(SscError) as raised:
        write_new(target, b"second")
    assert raised.value.code == "file-exists"
    assert raised.value.exit_code == 1
    assert target.read_bytes() == b"first"


def test_the_refusal_names_a_way_out(tmp_path: Path) -> None:
    target = tmp_path / "001_anchor.png"
    write_new(target, b"first")
    with pytest.raises(SscError) as raised:
        write_new(target, b"second")
    assert raised.value.fix is not None


def test_replace_overwrites_deliberately(tmp_path: Path) -> None:
    target = tmp_path / "meta.json"
    write_new(target, b"{}")
    replace(target, b'{"schema": 1}')
    assert target.read_bytes() == b'{"schema": 1}'


def test_replace_creates_the_file_when_there_is_none(tmp_path: Path) -> None:
    target = tmp_path / "nested/meta.json"
    replace(target, b"{}")
    assert target.read_bytes() == b"{}"


def test_replace_leaves_no_temporary_file_behind(tmp_path: Path) -> None:
    replace(tmp_path / "meta.json", b"{}")
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]


def test_a_failed_replace_leaves_the_previous_record_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reason for temp-plus-rename: an interruption must not produce half a file."""
    target = tmp_path / "meta.json"
    write_new(target, b'{"schema": 1}')

    def die(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("ssc.cli.atomic.os.replace", die)
    with pytest.raises(KeyboardInterrupt):
        replace(target, b'{"schema": 2}')

    assert target.read_bytes() == b'{"schema": 1}'
    assert [p.name for p in tmp_path.iterdir()] == ["meta.json"]


def test_bytes_survive_unchanged_on_every_platform(tmp_path: Path) -> None:
    """CRLF translation would corrupt a PNG, and only on Windows."""
    payload = b"\x89PNG\r\n\x1a\n\r\n"
    write_new(tmp_path / "a.png", payload)
    replace(tmp_path / "b.png", payload)
    assert (tmp_path / "a.png").read_bytes() == payload
    assert (tmp_path / "b.png").read_bytes() == payload


# R3.7 — a held directory. The property under test everywhere below is one thing: what
# was written landed in the directory that was opened, and never anywhere else.


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has no dir_fd to bind to")
def test_the_binding_is_real_where_the_platform_has_one(tmp_path: Path) -> None:
    """The guard against the failure this file already had once.

    `_DIR_FD` decides between a descriptor and an identity check, and the first version of
    it named a function `os.supports_dir_fd` never contains — so it was `False` everywhere
    and every platform silently took the weaker branch. Nothing failed on Windows, where
    the answer is `False` anyway, which is exactly why this assertion exists: the whole
    hardening degrades to a narrower window without a single test going red.
    """
    from ssc.cli.atomic import _DIR_FD

    assert _DIR_FD is True
    with Directory.open(tmp_path) as held:
        assert held._fd is not None


def test_a_held_directory_writes_and_refuses_the_same_way(tmp_path: Path) -> None:
    with Directory.open(tmp_path) as held:
        assert held.write_new("001_anchor.png", b"pixels") == tmp_path / "001_anchor.png"
        with pytest.raises(SscError) as raised:
            held.write_new("001_anchor.png", b"again")
    assert raised.value.code == "file-exists"
    assert (tmp_path / "001_anchor.png").read_bytes() == b"pixels"


def test_a_held_directory_replaces_whole_and_leaves_no_temporary(tmp_path: Path) -> None:
    with Directory.open(tmp_path) as held:
        held.write_new("meta.json", b"{}")
        held.replace("meta.json", b'{"schema": 1}')
    assert (tmp_path / "meta.json").read_bytes() == b'{"schema": 1}'
    assert [child.name for child in tmp_path.iterdir()] == ["meta.json"]


def test_a_held_subdirectory_is_created_once(tmp_path: Path) -> None:
    """`frames/` is the one subdirectory an asset may have, and a second `cut` into an
    asset that already has one is a refusal rather than a set written over another."""
    with Directory.open(tmp_path) as held:
        with held.child("frames") as frames:
            frames.write_new("001.png", b"pixels")
        with pytest.raises(SscError) as raised:
            held.child("frames")
    assert raised.value.code == "file-exists"
    assert (tmp_path / "frames" / "001.png").read_bytes() == b"pixels"


def test_a_name_that_walks_is_not_a_file_name(tmp_path: Path) -> None:
    """Everything below a held directory resolves against it, so a name that is a path is
    the one input that would make "relative to what was opened" mean nothing."""
    with Directory.open(tmp_path) as held:
        for name in ["../escaped.png", "nested/deep.png", "..", ""]:
            with pytest.raises(SscError) as raised:
                held.write_new(name, b"pixels")
            assert raised.value.code == "invalid-name"


def test_the_write_follows_the_directory_and_not_the_path(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """The whole point of holding one: the path is swapped for a link to somewhere else
    *after* the directory was opened and checked, and the write does not go there.

    The two platforms honour that differently and both are the requirement being met. A
    descriptor is a real binding, so on POSIX the write still lands in the directory that
    was opened — which is now reachable under another name. Windows has no descriptor for a
    directory, so the identity check refuses instead. Neither writes into `elsewhere`, and
    that is the assertion both share.
    """
    checked = tmp_path / "checked"
    checked.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    with Directory.open(checked) as held:
        checked.rename(tmp_path / "moved")
        link_dir(checked, elsewhere)

        if sys.platform == "win32":
            with pytest.raises(SscError) as raised:
                held.write_new("001_anchor.png", b"pixels")
            assert raised.value.code == "directory-changed"
        else:
            held.write_new("001_anchor.png", b"pixels")
            assert (tmp_path / "moved" / "001_anchor.png").read_bytes() == b"pixels"

    assert list(elsewhere.iterdir()) == []


def test_a_held_directory_deletes_a_file_and_a_frame_set(tmp_path: Path) -> None:
    """The two shapes `clean` removes: a recorded file, and `frames/`, which is one
    record naming a directory."""
    with Directory.open(tmp_path) as held:
        held.write_new("002_hero.snap.png", b"pixels")
        with held.child("frames") as frames:
            frames.write_new("001.png", b"pixels")

        held.delete("002_hero.snap.png")
        held.delete("frames")

    assert list(tmp_path.iterdir()) == []


def test_deleting_a_record_whose_file_already_went_is_not_an_error(tmp_path: Path) -> None:
    """`clean`'s own rule: the record is dropped either way, so a file somebody removed by
    hand must not stop the sweep before the record that names it is gone."""
    with Directory.open(tmp_path) as held:
        held.delete("001_never_existed.png")


def test_a_delete_does_not_cross_a_link_out_of_the_asset(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """`frames/` is a legitimate recorded segment, which is exactly what makes it worth
    replacing with a link: `shutil.rmtree` through one is the widest blast radius in the
    tool. A hand-edited `meta.json` is in this project's threat model, so this is reachable
    without any race at all.

    Deleting the *link itself* is refused too, on both platforms. `unlink` on it would be
    safe — it removes the link, never the target — but a recorded entry that is a link is
    a corrupt record, since nothing in `ssc` writes one, and reporting it beats tidying the
    evidence away. `clean` never gets this far anyway: `listing.inside` refuses the record
    first, which is what keeps that check load-bearing rather than redundant.
    """
    asset = tmp_path / "hero"
    asset.mkdir()
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    (elsewhere / "paid-for.png").write_bytes(b"not reproducible")
    link_dir(asset / "frames", elsewhere)

    with Directory.open(asset) as held:
        with pytest.raises(SscError) as refused:
            held.delete("frames/paid-for.png")
        with pytest.raises(SscError):
            held.delete("frames")

    assert refused.value.code == "path-escapes-asset"
    assert (elsewhere / "paid-for.png").read_bytes() == b"not reproducible"
    assert elsewhere.is_dir()


def test_a_delete_follows_the_directory_and_not_the_path(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """The swap, on the destructive operation. Same two platform outcomes as the write, and
    the same shared assertion: nothing in `elsewhere` was touched."""
    checked = tmp_path / "checked"
    checked.mkdir()
    (checked / "001_hero.png").write_bytes(b"pixels")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "001_hero.png").write_bytes(b"not reproducible")

    with Directory.open(checked) as held:
        checked.rename(tmp_path / "moved")
        link_dir(checked, elsewhere)

        if sys.platform == "win32":
            with pytest.raises(SscError) as refused:
                held.delete("001_hero.png")
            assert refused.value.code == "directory-changed"
        else:
            held.delete("001_hero.png")
            assert not (tmp_path / "moved" / "001_hero.png").exists()

    assert (elsewhere / "001_hero.png").read_bytes() == b"not reproducible"


def test_confirm_refuses_a_path_that_is_not_the_directory_being_held(tmp_path: Path) -> None:
    """`listing.bound` checks a path and then asks this whether the path it checked is the
    directory it opened. A no is the swap that happened in between."""
    one = tmp_path / "one"
    one.mkdir()
    other = tmp_path / "other"
    other.mkdir()

    with Directory.open(one) as held:
        held.confirm(one)
        with pytest.raises(SscError) as raised:
            held.confirm(other)
    assert raised.value.code == "directory-changed"
    assert raised.value.fix is not None


# R3.7, the read half — the record a command acts on comes out of the directory that was
# checked, not out of whatever that path names by the time the load happens.


def test_a_held_directory_reads_what_it_holds(tmp_path: Path) -> None:
    (tmp_path / "meta.json").write_bytes(b'{"schema": 1}')
    (tmp_path / "frames").mkdir()
    (tmp_path / "frames" / "001.png").write_bytes(b"pixels")

    with Directory.open(tmp_path) as held:
        assert held.read("meta.json") == b'{"schema": 1}'
        assert held.read("frames/001.png") == b"pixels"


def test_reading_a_file_that_is_not_there_reaches_the_caller_intact(tmp_path: Path) -> None:
    """`meta.load` is the caller, and a directory holding no `meta.json` is a directory that
    is not an asset — an ordinary mistake with a command that fixes it, not an escape. It
    can only stay one if `read` declines to translate it."""
    with Directory.open(tmp_path) as held, pytest.raises(FileNotFoundError):
        held.read("meta.json")


def test_a_read_can_be_bounded_and_refuses_what_is_over_the_bound(tmp_path: Path) -> None:
    """Binding a read costs the laziness `Image.open` on a path would have had, so the
    caller that needs a ceiling gets one. The limit is inclusive: a file exactly at it is
    the largest legitimate input, not the first refused one."""
    (tmp_path / "at-the-limit").write_bytes(b"x" * 16)
    (tmp_path / "over-it").write_bytes(b"x" * 17)

    with Directory.open(tmp_path) as held:
        assert held.read("at-the-limit", max_bytes=16) == b"x" * 16
        with pytest.raises(SscError) as raised:
            held.read("over-it", max_bytes=16)
    assert raised.value.code == "file-too-large"


def test_a_bounded_read_stops_at_the_bound_rather_than_reading_it_all(tmp_path: Path) -> None:
    """The point of the ceiling is the memory, so the refusal has to come from reading one
    byte past it rather than from measuring afterwards — a `stat` first would ask a second
    time about the file the first question was meant to settle."""
    (tmp_path / "big").write_bytes(b"x" * 4096)

    with Directory.open(tmp_path) as held, pytest.raises(SscError):
        held.read("big", max_bytes=8)


def test_a_recorded_name_that_is_a_directory_is_refused_the_same_way_on_both_platforms(
    tmp_path: Path,
) -> None:
    """POSIX gets EISDIR from `O_NOFOLLOW`, Windows gets a `PermissionError` from opening a
    directory. Left bare, the Windows branch reported the identical corrupt record as an
    `internal-error` traceback while POSIX named it — so the translation is on both."""
    (tmp_path / "001_hero.png").mkdir()

    with Directory.open(tmp_path) as held, pytest.raises(SscError) as raised:
        held.read("001_hero.png")
    assert raised.value.code == "path-escapes-asset"


def test_a_name_that_walks_is_not_readable_either(tmp_path: Path) -> None:
    (tmp_path.parent / "secret.json").write_bytes(b"not yours")
    with Directory.open(tmp_path) as held:
        for name in ["../secret.json", "..", ""]:
            with pytest.raises(SscError) as raised:
                held.read(name)
            assert raised.value.code == "invalid-name"


def test_a_read_does_not_cross_a_link_out_of_the_asset(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """The read counterpart of the delete gate, and reachable the same way: a hand-edited
    `meta.json` naming `frames/x.png` where `frames/` has been replaced with a link is how
    a file outside the asset gets read under the asset's name."""
    asset = tmp_path / "hero"
    asset.mkdir()
    elsewhere = tmp_path / "outside"
    elsewhere.mkdir()
    (elsewhere / "paid-for.png").write_bytes(b"not reproducible")
    link_dir(asset / "frames", elsewhere)

    with Directory.open(asset) as held, pytest.raises(SscError) as refused:
        held.read("frames/paid-for.png")
    assert refused.value.code == "path-escapes-asset"


def test_the_read_follows_the_directory_and_not_the_path(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """The swap, on the read. The two platforms honour it differently and both meet the
    requirement: POSIX keeps reading the directory it opened, Windows refuses. What neither
    does is return `elsewhere`'s record as though it were this asset's — which is the whole
    failure a bound read exists to prevent."""
    checked = tmp_path / "checked"
    checked.mkdir()
    (checked / "meta.json").write_bytes(b'{"which": "ours"}')
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "meta.json").write_bytes(b'{"which": "theirs"}')

    with Directory.open(checked) as held:
        checked.rename(tmp_path / "moved")
        link_dir(checked, elsewhere)

        if sys.platform == "win32":
            with pytest.raises(SscError) as raised:
                held.read("meta.json")
            assert raised.value.code == "directory-changed"
        else:
            assert held.read("meta.json") == b'{"which": "ours"}'


def test_subdirectories_names_the_directories_and_nothing_else(tmp_path: Path) -> None:
    """`meta.check_layout` is the caller: `frames/` and nothing else, so what it needs is
    the children that are directories, and a file must not read as one."""
    (tmp_path / "frames").mkdir()
    (tmp_path / "sprites").mkdir()
    (tmp_path / "meta.json").write_bytes(b"{}")
    (tmp_path / "001_hero.png").write_bytes(b"pixels")

    with Directory.open(tmp_path) as held:
        assert held.subdirectories() == ["frames", "sprites"]


def test_an_empty_directory_has_no_subdirectories(tmp_path: Path) -> None:
    with Directory.open(tmp_path) as held:
        assert held.subdirectories() == []


def test_the_listing_follows_the_directory_and_not_the_path(
    tmp_path: Path, link_dir: Callable[[Path, Path], None]
) -> None:
    """A layout check is worth what it was taken against. Checking one directory's children
    and then acting on another's is a check of something that is no longer the subject."""
    checked = tmp_path / "checked"
    checked.mkdir()
    (checked / "frames").mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "sprites").mkdir()

    with Directory.open(checked) as held:
        checked.rename(tmp_path / "moved")
        link_dir(checked, elsewhere)

        if sys.platform == "win32":
            with pytest.raises(SscError) as raised:
                held.subdirectories()
            assert raised.value.code == "directory-changed"
        else:
            assert held.subdirectories() == ["frames"]


# R3.9 — the Windows fallback rests on a number the volume has to supply, and says so when
# the volume does not.


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX binds to a descriptor, not to a number")
def test_a_descriptor_is_bindable_whatever_the_volume_reports(tmp_path: Path) -> None:
    """On POSIX `bindable` is `True` by construction, and must not start consulting
    `st_ino`: the descriptor is the binding, and the number is not part of it."""
    with Directory.open(tmp_path) as held:
        assert held.bindable is True


def test_a_volume_reporting_no_file_index_is_not_bindable(tmp_path: Path) -> None:
    """The measurement behind R3.9. NTFS reports a real 64-bit file index; FAT32, exFAT and
    some SMB mounts have none and Windows returns `0`, which makes every directory on the
    volume identical to every other and `_guard` a comparison that always passes.

    Constructed rather than mounted, because the failure is about what the code does with
    the number and a test that needed an exFAT volume would never run anywhere.
    """
    from ssc.cli.atomic import Directory as Held

    assert Held(tmp_path, None, (0, 0)).bindable is False
    assert Held(tmp_path, None, (12, 0)).bindable is False
    assert Held(tmp_path, None, (0, 34)).bindable is False
    assert Held(tmp_path, None, (12, 34)).bindable is True
