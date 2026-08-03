"""Argument parsers shared by more than one command.

Here rather than in whichever command needed it first: `doctor` reads nine-patch guides and
so does `ninepatch`, and having the read-only measuring command import from the module that
loads a WASM runtime — for a twelve-line string parser — makes `doctor` fail for reasons it
has nothing to do with.
"""

from __future__ import annotations

import re

from ssc.cli.errors import UsageError

#: ASCII digits only, and a sign. `str.isdigit()` is true for superscripts and for a dozen
#: other Unicode digit blocks that `int()` then refuses, which turns a caller's typo into an
#: `internal-error` instead of the refusal this parser exists to give them.
INTEGER = re.compile(r"^-?[0-9]+$")

#: No guide is a billion pixels. The bound is not about the image — `bounds` refuses against
#: the real one — but about arithmetic: a value of a few hundred digits overflows the float
#: division inside `snap` before any check about the image can run.
MAX_GUIDE = 10**9


def parse_guides(value: str | None) -> tuple[int, int, int, int] | None:
    """`left,right,top,bottom`, each a distance inwards from that edge."""
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != 4 or not all(INTEGER.match(part) for part in parts):
        raise UsageError(
            "invalid-guides",
            f"{value!r} is not four whole numbers",
            fix="write it as left,right,top,bottom — distances inwards from each edge",
        )
    guides = tuple(int(part) for part in parts)
    if any(abs(guide) > MAX_GUIDE for guide in guides):
        raise UsageError(
            "invalid-guides",
            f"{value!r} holds a guide past {MAX_GUIDE}",
            fix="a guide is a distance in pixels, not a coordinate space",
        )
    left, right, top, bottom = guides
    return left, right, top, bottom
