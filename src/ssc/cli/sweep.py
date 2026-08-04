"""The parameter grammar behind `ssc tool sweep`.

Values stay **strings** all the way through this module. What a value means — an int, a
float, a choice out of a fixed set, a bound it has to sit inside — is the registry's
knowledge (`cli/steps.py`), and a grammar that also parsed types would be a second place
that decides what `--tol` is. So this settles how many points there are and in what order,
and nothing about what they contain.
"""

from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass

from ssc.cli.errors import UsageError
from ssc.cli.names import check_name

#: A contact sheet is something a person looks at, and past a certain count nobody is
#: comparing anything — they are scrolling. The ceiling is on the *product*, so two
#: parameters of eight values each is already at it.
MAX_VARIANTS = 64

#: Bounds each side of a `first..last:step` range before the count is worked out. The count
#: itself is what R1.4 refuses on, but `1..1e9:0.000001` has to be refused *without* first
#: building the list that would prove it too long.
MAX_RANGE_POINTS = MAX_VARIANTS

#: How much representation error a range count absorbs before it counts as another point.
#: Absolute rather than relative because the values a parameter takes here are bounded by
#: the registry — a tolerance, a colour budget, a pixel count — and none of them is near
#: the magnitude where an absolute epsilon stops meaning anything.
RANGE_TOLERANCE = 1e-9

#: Anything a path segment may not hold. `parse_hex` accepts a leading `#` and strips it,
#: so a legitimate `--vary outline=#aabbcc` reaches here with a character no name allows.
UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

#: `check_name`'s own ceiling. A four-parameter sweep composes a longer label than this,
#: and being refused for it is not something a caller can act on.
MAX_SEGMENT = 64

NUMBER = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")

RANGE = re.compile(r"^(?P<first>-?[0-9.]+)\.\.(?P<last>-?[0-9.]+):(?P<step>-?[0-9.]+)$")


@dataclass(frozen=True)
class Vary:
    """One parameter and the values it takes, in the order they were written."""

    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Point:
    """One combination — the parameters of a single variant."""

    index: int
    values: dict[str, str]

    @property
    def label(self) -> str:
        """`tol-60_mode-flood` — what a person reads on the contact sheet.

        Display text, deliberately unconstrained. It shows the values as they were written,
        including a `#aabbcc` that `parse_hex` accepts and a run of parameters far longer
        than any filename should be.
        """
        return "_".join(f"{name}-{value}" for name, value in self.values.items())

    @property
    def segment(self) -> str:
        """`00_tol-60` — the same point as a directory name, confined.

        Split from `label` after both halves of doing one job with one string went wrong.
        Confining the display string rejected two *legitimate* sweeps: `--vary
        chroma=#aabbcc`, which `parse_hex` accepts and strips, and any run of four or so
        parameters, because a name is capped at 64 characters and a label concatenates all
        of them. A sweep doing nothing wrong was refused with "is not a name".

        So this sanitizes rather than merely checks. That is safe here and would not be
        elsewhere: the index prefix already carries uniqueness, so folding two distinct
        labels onto one cleaned string cannot collide, and truncating loses only
        description. `check_name` stays as the assertion that the result is confined —
        the property that matters is that a value cannot escape the review directory, and
        it is enforced rather than inherited from how strict the registry's parsers happen
        to be today.
        """
        stem = f"{self.index:02d}_{UNSAFE.sub('-', self.label)}"[:MAX_SEGMENT]
        # A cut can land mid-value and leave a trailing dot, which `check_name` refuses for
        # its own good reasons (Windows strips it, so two names become one directory).
        return check_name(stem.rstrip(".-_") or f"{self.index:02d}", "a variant name")


def parse_vary(declaration: str) -> Vary:
    """`name=values` into a name and its values (R1.3).

    Two spellings, and both are here rather than in two flags because they answer one
    question. An explicit list is what you write when the candidates are named — `flood`
    and `global`, or three palettes somebody chose. `first..last:step` is what you write
    when the parameter is a dial and the interesting part is the interval.
    """
    name, separator, raw = declaration.partition("=")
    name = name.strip()
    if not separator or not name:
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} is not a parameter and its values",
            fix="write it as --vary name=a,b,c or --vary name=first..last:step",
        )

    raw = raw.strip()
    if not raw:
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} names {name!r} with no values",
            fix="write it as --vary name=a,b,c or --vary name=first..last:step",
        )

    span = RANGE.match(raw)
    if span is not None:
        values = _span(span.group("first"), span.group("last"), span.group("step"), declaration)
    elif ".." in raw:
        # Routed on the `..` rather than on whether the whole thing parsed. Falling back to
        # the list parser meant `tol=a..b:c` became the single literal value `"a..b:c"` and
        # swept one nonsense point instead of refusing — a typo in a range silently becoming
        # a one-point sweep is the worst of the three outcomes.
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} looks like a range but is not first..last:step",
            fix="write it as first..last:step, for example 40..80:20",
        )
    else:
        values = _listed(raw, declaration)
    return Vary(name=name, values=values)


def _listed(raw: str, declaration: str) -> tuple[str, ...]:
    """A comma-separated list, with the empties refused rather than dropped.

    `--vary mode=flood,,global` is a typo, and silently sweeping two points where the
    caller wrote three is the kind of thing nobody notices until the contact sheet has one
    fewer cell than they expected.
    """
    parts = [part.strip() for part in raw.split(",")]
    if any(not part for part in parts):
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} has an empty value in its list",
            fix="write the values separated by single commas",
        )
    seen: list[str] = []
    for part in parts:
        # Duplicates are refused, not deduplicated: running the same point twice produces
        # two identical variants and a contact sheet that looks like a bug in the tool.
        if part in seen:
            raise UsageError(
                "invalid-vary",
                f"{declaration!r} lists {part!r} more than once",
                fix="each value is run once; remove the repeat",
            )
        seen.append(part)
    return tuple(seen)


def _span(first: str, last: str, step: str, declaration: str) -> tuple[str, ...]:
    """`first..last:step`, inclusive of `last` where the step lands on it exactly."""
    for part in (first, last, step):
        if not NUMBER.match(part):
            raise UsageError(
                "invalid-vary",
                f"{declaration!r} has {part!r} where a number belongs",
                fix="write it as first..last:step, for example 40..80:20",
            )

    whole = not any("." in part for part in (first, last, step))
    start, stop, by = float(first), float(last), float(step)

    if by == 0:
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} has a step of zero, which never reaches {last}",
            fix="use a step above zero, or write the values out as a list",
        )
    if (stop - start) / by < 0:
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} steps away from {last}, so it never arrives",
            fix=f"a range from {first} to {last} needs a step of the matching sign",
        )

    # Counted rather than accumulated. Adding the step repeatedly drifts on floats — a
    # `0..1:0.1` walk lands on 0.30000000000000004 — and the drift shows up in a directory
    # name, where it is both ugly and unstable between platforms.
    #
    # Floored with a tolerance, and both halves of that matter. `int()` alone truncated
    # `0..0.3:0.1` to three points and silently dropped `0.3`, because the division lands on
    # 2.9999999999999996 — a sweep quietly one variant short of what was asked for, which is
    # the one failure a comparison tool must not have. Plain `round()` fixes that case and
    # breaks another: `40..99:20` has a span of 2.95, which rounds up to a fourth point at
    # 100, past the last the caller stated. The tolerance absorbs representation error
    # without inventing a point the range does not contain.
    count = math.floor((stop - start) / by + RANGE_TOLERANCE) + 1
    if count > MAX_RANGE_POINTS:
        raise UsageError(
            "invalid-vary",
            f"{declaration!r} is {count} points, over the {MAX_RANGE_POINTS} a sweep allows",
            fix=f"widen the step, or narrow the range, to at most {MAX_RANGE_POINTS} points",
        )

    values = []
    for index in range(count):
        value = start + index * by
        # `round` before formatting, so 0.1 * 3 is 0.3 in the name as well as in the value
        # the registry will parse back.
        values.append(str(round(value)) if whole else f"{round(value, 6):g}")
    return tuple(values)


def expand(varied: list[Vary]) -> list[Point]:
    """Every combination, in declaration order, refused above the ceiling (R1.2, R1.4).

    The first parameter varies slowest, which is `itertools.product`'s order and is the one
    worth having: the variants group by the parameter written first, so a contact sheet
    laid out in rows reads as one block per value of it.

    The ceiling is checked from the *counts*, before the product is built. Building the
    product in order to measure it is how a ceiling meant to bound work ends up doing the
    work it was protecting against.
    """
    if not varied:
        raise UsageError(
            "no-vary",
            "a sweep needs at least one parameter to vary",
            fix="add --vary name=a,b,c",
        )

    seen: set[str] = set()
    for one in varied:
        if one.name in seen:
            raise UsageError(
                "invalid-vary",
                f"{one.name!r} is varied more than once",
                fix="give each parameter one --vary, carrying all of its values",
            )
        seen.add(one.name)

    total = 1
    for one in varied:
        total *= len(one.values)
    if total > MAX_VARIANTS:
        raise UsageError(
            "too-many-variants",
            f"that is {total} variants, over the {MAX_VARIANTS} a sweep allows",
            fix=f"narrow a range, or vary fewer parameters, to at most {MAX_VARIANTS}",
        )

    names = [one.name for one in varied]
    return [
        Point(index=index, values=dict(zip(names, combination, strict=True)))
        for index, combination in enumerate(itertools.product(*(one.values for one in varied)))
    ]
