"""R3.5 · R3.6 — nothing overwrites, and the one file that is rewritten is rewritten whole."""

from __future__ import annotations

from pathlib import Path

import pytest

from ssc.cli.atomic import replace, write_new
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
