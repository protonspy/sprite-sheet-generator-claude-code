"""What may become a path.

A kind, a key and a recorded file path all end up concatenated onto the workspace root, so
each of them is a way to leave it. `Path("/w/assets") / "../.." / "x"` escapes, and
`Path("/w/assets") / "C:/Windows"` discards the left side entirely — neither needs anything
exotic, just a string nobody checked.

This matters more than it would in a tool driven only by a human at a terminal: `ssc` is
meant to be driven by an agent, and `meta.json` is a file that survives hand-editing and a
crash. Both are places a bad name arrives without anyone typing it.
"""

from __future__ import annotations

import re

from ssc.cli.errors import UsageError

#: A name is a name: a segment, not a path. Leading dot excluded, which also rules out
#: `.` and `..` without special-casing them.
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

#: Windows resolves these to devices whatever the extension, so `assets/con/hero` is not a
#: directory anybody gets to create. Rejected on every platform, because a workspace is
#: copied between them.
RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{n}" for n in range(1, 10)),
    *(f"lpt{n}" for n in range(1, 10)),
}


def check_name(value: str, what: str) -> str:
    """A single path segment: no separator, no `..`, no drive, no device name."""
    if not NAME.match(value):
        raise UsageError(
            "invalid-name",
            f"{what} {value!r} is not a name: use letters, digits, dot, dash or underscore, "
            "starting with a letter or a digit, up to 64 characters",
        )
    if value.split(".", 1)[0].lower() in RESERVED:
        raise UsageError(
            "invalid-name",
            f"{what} {value!r} is a reserved device name on Windows",
        )
    return value


def check_relative_path(value: str, what: str = "path") -> str:
    """A path recorded in `meta.json`: relative, forward slashes, every segment a name.

    `frames/003_walk.png` is legitimate and `../../etc` is not, and the difference has to
    be decided here rather than by whatever the filesystem does with it later.
    """
    if not value or value != value.strip():
        raise UsageError("invalid-path", f"{what} {value!r} is empty or padded with whitespace")
    if "\\" in value:
        raise UsageError(
            "invalid-path",
            f"{what} {value!r} uses a backslash; recorded paths are always forward-slashed",
        )
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise UsageError("invalid-path", f"{what} {value!r} is absolute; it must be relative")

    segments = value.split("/")
    for segment in segments:
        if segment in {"", ".", ".."}:
            raise UsageError(
                "invalid-path",
                f"{what} {value!r} walks outside the asset it belongs to",
            )
        check_name(segment, f"a segment of {what}")
    return value
