"""R5.1 · R5.2 · R5.3 — content addressing, and what must change the key.

Written before `ssc.cli.cache` existed. A key that ignores a parameter hands back a stale
image that looks plausible, and nobody notices — which is why this task is TDD and why
most of these tests are about what makes two calls *different* rather than the same.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ssc.cli.cache import Cache, cache_key
from ssc.cli.errors import SscError

A = "a" * 64
B = "b" * 64


def test_the_key_is_a_sha256() -> None:
    key = cache_key("tool snap", params={}, inputs=[A])
    assert len(key) == 64
    assert set(key) <= set("0123456789abcdef")


def test_the_same_call_gives_the_same_key() -> None:
    first = cache_key("tool snap", params={"k_colors": 16}, inputs=[A])
    second = cache_key("tool snap", params={"k_colors": 16}, inputs=[A])
    assert first == second


def test_different_input_content_gives_a_different_key() -> None:
    assert cache_key("tool snap", params={}, inputs=[A]) != cache_key(
        "tool snap", params={}, inputs=[B]
    )


def test_the_order_of_the_inputs_matters() -> None:
    """A frame set is an ordered thing; two orders are two different animations."""
    assert cache_key("tool pack", params={}, inputs=[A, B]) != cache_key(
        "tool pack", params={}, inputs=[B, A]
    )


def test_a_different_command_gives_a_different_key() -> None:
    assert cache_key("tool snap", params={}, inputs=[A]) != cache_key(
        "tool pixelart", params={}, inputs=[A]
    )


def test_a_changed_parameter_gives_a_different_key() -> None:
    assert cache_key("tool snap", params={"k_colors": 16}, inputs=[A]) != cache_key(
        "tool snap", params={"k_colors": 8}, inputs=[A]
    )


def test_the_order_parameters_were_written_in_does_not_matter() -> None:
    """Dict order is not semantics, and a key that thought it was would miss constantly."""
    assert cache_key("tool snap", params={"a": 1, "b": 2}, inputs=[A]) == cache_key(
        "tool snap", params={"b": 2, "a": 1}, inputs=[A]
    )


def test_salt_changes_the_key() -> None:
    """The reason `salt` exists: the same prompt against two models is two results, and a
    cache conflating them is worse than no cache. `cv-runtime` folds in the execution
    provider the same way."""
    assert cache_key("gen image", params={}, inputs=[A], salt={"model": "nano-banana-2"}) != (
        cache_key("gen image", params={}, inputs=[A], salt={"model": "gpt-image-1.5"})
    )


def test_no_salt_is_empty_salt() -> None:
    assert cache_key("tool snap", params={}, inputs=[A]) == cache_key(
        "tool snap", params={}, inputs=[A], salt={}
    )


def test_a_nested_parameter_still_hashes_deterministically() -> None:
    nested = {"palette": ["0d2b45", "ffecd6"], "opts": {"dither": True}}
    assert cache_key("tool pixelart", params=nested, inputs=[A]) == cache_key(
        "tool pixelart",
        params={"opts": {"dither": True}, "palette": ["0d2b45", "ffecd6"]},
        inputs=[A],
    )


def test_a_parameter_that_cannot_be_hashed_is_refused_loudly() -> None:
    """Coercing it with `str()` would produce a key that silently ignores the difference
    between two objects — the exact failure this whole task exists to prevent."""
    with pytest.raises(SscError) as raised:
        cache_key("tool snap", params={"path": Path("/tmp/x")}, inputs=[A])
    assert raised.value.code == "uncacheable-params"


def test_storing_and_reading_back(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    key = cache_key("tool snap", params={}, inputs=[A])
    assert cache.get(key) is None
    cache.put(key, b"snapped")
    assert cache.get(key) == b"snapped"


def test_entries_are_spread_so_one_directory_does_not_hold_everything(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    key = cache_key("tool snap", params={}, inputs=[A])
    cache.put(key, b"snapped")
    assert (tmp_path / key[:2] / key).is_file()


def test_writing_the_same_key_twice_is_not_an_error(tmp_path: Path) -> None:
    """Content addressing means the second write is the same bytes; refusing it would
    turn a harmless race between two runs into a failure."""
    cache = Cache(tmp_path)
    key = cache_key("tool snap", params={}, inputs=[A])
    cache.put(key, b"snapped")
    cache.put(key, b"snapped")
    assert cache.get(key) == b"snapped"


def test_the_cache_may_vanish_at_any_moment(tmp_path: Path) -> None:
    """R5.3. Deleting `cache/` is always safe, so a miss on a directory that is not there
    is a miss, not a crash."""
    cache = Cache(tmp_path / "gone")
    assert cache.get(cache_key("tool snap", params={}, inputs=[A])) is None


def test_use_computes_on_a_miss_and_reports_it(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    key = cache_key("tool snap", params={}, inputs=[A])
    calls = []

    def compute() -> bytes:
        calls.append(1)
        return b"snapped"

    data, hit = cache.use(key, compute)
    assert (data, hit, len(calls)) == (b"snapped", False, 1)


def test_use_reuses_on_a_hit_without_recomputing(tmp_path: Path) -> None:
    """R5.2 — the flag is what a command puts in its JSON, so "reused" is read rather
    than inferred from how fast it ran."""
    cache = Cache(tmp_path)
    key = cache_key("tool snap", params={}, inputs=[A])
    cache.put(key, b"snapped")

    def explode() -> bytes:
        raise AssertionError("a hit must not recompute")

    assert cache.use(key, explode) == (b"snapped", True)
