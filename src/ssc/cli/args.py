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


def parse_hex(value: str) -> tuple[int, int, int]:
    """`rrggbb` into a colour.

    Here rather than in `commands/convert.py`, where it was, because it has three callers
    now: the two conversion commands, `cli/steps.py`'s registry — which parses the same
    values arriving from `--vary` — and `commands/doctor.py`, which still carries its own
    copy. Two implementations of "what is a hex colour" is exactly what this module exists
    to stop, and the third is noted rather than merged only because `doctor` is not this
    change's to touch.
    """
    text = value.strip().lstrip("#")
    if len(text) != 6 or any(character not in "0123456789abcdefABCDEF" for character in text):
        raise UsageError(
            "invalid-colour",
            f"{value!r} is not a 6-digit hex colour",
            fix="write it as rrggbb, for example 0d2b45",
        )
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def parse_anchor(value: str | None) -> tuple[int, int] | None:
    """`x,y` into the anchor point a transform is to carry, or `None` where no anchor was
    given. `x` is the column, `y` is the row — the order the index records the anchor in,
    not the `(row, column)` numpy carries a frame in.
    """
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != 2 or not all(INTEGER.match(part) for part in parts):
        raise UsageError(
            "invalid-anchor",
            f"{value!r} is not two whole numbers",
            fix="write it as x,y — column,then row, the order the index records",
        )
    return int(parts[0]), int(parts[1])


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
