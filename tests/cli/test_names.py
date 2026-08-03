"""A kind, a key and a recorded path are all ways to leave the workspace.

From the security review of this leaf, which found both: `--kind ../../../..` wrote a
`meta.json` four directories above the root, and a hand-edited `meta.json` made
`ssc clean` delete a directory outside the workspace entirely.
"""

from __future__ import annotations

import pytest

from ssc.cli.errors import UsageError
from ssc.cli.names import check_name, check_relative_path


@pytest.mark.parametrize("value", ["hero", "anchor_s", "tile-grass", "a", "v2.1", "A1"])
def test_an_ordinary_name_is_accepted(value: str) -> None:
    assert check_name(value, "key") == value


@pytest.mark.parametrize(
    "value",
    [
        "..",
        ".",
        ".hidden",
        "a/b",
        "a\\b",
        "/abs",
        "C:/Windows",
        "",
        " hero",
        "hero ",
        "a" * 65,
        "héro",
    ],
)
def test_anything_that_is_not_a_single_plain_segment_is_refused(value: str) -> None:
    with pytest.raises(UsageError) as raised:
        check_name(value, "kind")
    assert raised.value.code == "invalid-name"
    assert raised.value.exit_code == 2


@pytest.mark.parametrize("value", ["con", "NUL", "com1", "lpt9", "CON.png"])
def test_windows_device_names_are_refused_everywhere(value: str) -> None:
    """A workspace gets copied between platforms, so this cannot be a Windows-only rule."""
    with pytest.raises(UsageError):
        check_name(value, "key")


@pytest.mark.parametrize("value", ["001_anchor.png", "frames/003_walk.png", "meta.json"])
def test_a_path_inside_the_asset_is_accepted(value: str) -> None:
    assert check_relative_path(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "../secret",
        "../../../../victim",
        "a/../../b",
        "/etc/passwd",
        "C:/Windows/System32",
        "frames\\003.png",
        "",
        ".",
        "..",
        "frames//003.png",
        "frames/./003.png",
    ],
)
def test_a_path_that_leaves_the_asset_is_refused(value: str) -> None:
    with pytest.raises(UsageError) as raised:
        check_relative_path(value)
    assert raised.value.code in {"invalid-path", "invalid-name"}
