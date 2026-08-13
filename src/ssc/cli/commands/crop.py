"""`ssc tool crop` — cutting a frame down to a rectangle somebody chose.

A module of its own rather than a ninth command in `recover.py`: that module is the
detector — finding pieces nobody described — and this one is told exactly where to cut.
It borrows `recover.py`'s destination handling, because writing into an asset or writing
loose files is the same choice everywhere it appears.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any

import click

from ssc.cli.args import INTEGER, MAX_GUIDE, parse_anchor
from ssc.cli.commands.recover import destination, transform_into_asset
from ssc.cli.errors import UsageError
from ssc.cli.frames import Frame, read_frames, write_frames
from ssc.cli.main import ssc_command
from ssc.cli.output import Result
from ssc.core.assemble import trim_anchor, trim_box
from ssc.core.crop import GRAVITIES, aspect_rect, inset_rect
from ssc.core.recover import Rect, crop


def bounded(numbers: list[int], value: str, code: str, fix: str) -> None:
    """Refuse a number past `MAX_GUIDE` before it reaches the geometry.

    `args.parse_guides` bounds its numbers for the same reason and this borrows its
    ceiling: a coordinate of a few hundred digits is not a pixel, and letting it through
    turns a caller's typo into whatever the arithmetic does with it — an `internal-error`
    saying nothing, rather than the refusal naming the flag they can act on.
    """
    if any(abs(number) > MAX_GUIDE for number in numbers):
        raise UsageError(code, f"{value!r} holds a number past {MAX_GUIDE}", fix=fix)


def parse_box(value: str) -> Rect:
    """`x,y,WxH` into the rectangle to cut — the origin, then the size.

    One argument rather than four options: a box is one thing, and `--x 4 --y 8 --width 16`
    is three chances to give half of it.
    """
    parts = [part.strip() for part in value.split(",")]
    size = parts[2].lower().split("x") if len(parts) == 3 else []
    numbers = parts[:2] + size
    if len(parts) != 3 or len(size) != 2 or not all(INTEGER.match(part) for part in numbers):
        raise UsageError(
            "invalid-box",
            f"{value!r} is not a box like 4,8,16x16",
            fix="write it as x,y,WxH — the origin, then the size",
        )
    x, y, width, height = int(parts[0]), int(parts[1]), int(size[0]), int(size[1])
    bounded(
        [x, y, width, height], value, "invalid-box", "a box is in pixels, not a coordinate space"
    )
    if width < 1 or height < 1:
        raise UsageError(
            "invalid-box",
            f"{value!r} has no pixels in it",
            fix="give a box at least 1x1",
        )
    return Rect(x=x, y=y, width=width, height=height)


def parse_ratio(value: str) -> tuple[int, int]:
    """`W:H` into the ratio to fit. A colon, not an `x`, because `WxH` is a size everywhere
    else in this CLI and `16x9` meaning "the shape 16:9, at whatever size fits" would read
    as a sixteen-by-nine box."""
    parts = [part.strip() for part in value.split(":")]
    if len(parts) != 2 or not all(INTEGER.match(part) for part in parts):
        raise UsageError(
            "invalid-aspect",
            f"{value!r} is not a ratio like 16:9",
            fix="write it as W:H — width, then height",
        )
    ratio = [int(parts[0]), int(parts[1])]
    bounded(ratio, value, "invalid-aspect", "a ratio is two small numbers, like 16:9")
    return ratio[0], ratio[1]


def parse_insets(value: str) -> tuple[int, int, int, int]:
    """One number for all four sides, or four read clockwise from the top."""
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in (1, 4) or not all(INTEGER.match(part) for part in parts):
        raise UsageError(
            "invalid-inset",
            f"{value!r} is not one number or four",
            fix="give --inset 8, or --inset top,right,bottom,left",
        )
    numbers = [int(part) for part in parts]
    bounded(numbers, value, "invalid-inset", "an inset is a distance in pixels")
    if len(numbers) == 1:
        return (numbers[0],) * 4
    return numbers[0], numbers[1], numbers[2], numbers[3]


def rect_for(
    canvas: tuple[int, int],
    *,
    box: Rect | None,
    ratio: tuple[int, int] | None,
    insets: tuple[int, int, int, int] | None,
    gravity: str,
) -> Rect:
    """The rectangle to cut out of a canvas of this size.

    A stated box is already the answer and is returned unchanged — it is in the source's
    own pixels, so it does not depend on the canvas at all, which is the same reason
    `--per-frame` means nothing alongside it (R2.3).
    """
    if box is not None:
        return box
    try:
        if ratio is not None:
            return aspect_rect(canvas, ratio, gravity)
        assert insets is not None
        return inset_rect(canvas, insets)
    except ValueError as refused:
        # The geometry refuses in the caller's own terms — an empty rectangle, a negative
        # inset — so the message is passed through rather than restated worse.
        raise UsageError(
            "invalid-box", str(refused), fix="crop to something with pixels in it"
        ) from refused


def cut(frames: list[Frame], rects: list[Rect]) -> list[Frame]:
    """Every frame cut to its rectangle, or the call refused naming the frame that did not
    fit (R1.6).

    `recover.crop` is what refuses: a numpy slice past the edge truncates silently, and the
    frame's name is the part a caller needs to act on — a set of ninety says nothing without
    it.
    """
    cropped = []
    for frame, rect in zip(frames, rects, strict=True):
        try:
            cropped.append(Frame(frame.name, crop(frame.image, rect)))
        except ValueError as refused:
            raise UsageError(
                "box-outside-frame",
                f"{frame.name}: {refused}",
                fix="crop never invents a pixel; give a box inside the frame, or tool expand first",
            ) from refused
    return cropped


@ssc_command("crop", help="Cut frames to a box you state. Never pads — that is tool expand.")
@click.option(
    "--gravity",
    type=click.Choice(GRAVITIES),
    default="centre",
    help="Where a computed box sits. An axis it does not name is centred.",
)
@click.option(
    "--per-frame",
    "per_frame",
    is_flag=True,
    help="Compute the box against each frame's own canvas. Breaks registration; say so.",
)
@click.option("--inset", "inset_in", default=None, help="Cut N off every side, or T,R,B,L.")
@click.option("--aspect", "aspect_in", default=None, help="Cut the largest W:H that fits.")
@click.option(
    "--anchor", "anchor_in", default=None, help="Recorded anchor x,y moved with the frames."
)
@click.option("--box", "box_in", default=None, help="The rectangle to cut, as x,y,WxH.")
@click.option("--asset", default=None, help="Record into this <kind>/<key>.")
@click.option("--out", default=None, type=click.Path(path_type=Path), help="Or here.")
@click.option("--in", "source", required=True, type=click.Path(path_type=Path))
def crop_command(
    source: Path,
    out: Path | None,
    asset: str | None,
    box_in: str | None,
    anchor_in: str | None,
    aspect_in: str | None,
    inset_in: str | None,
    gravity: str,
    per_frame: bool,
    *,
    dry_run: bool,
) -> Result:
    destination(asset, out)
    if per_frame and box_in is not None:
        raise UsageError(
            "per-frame-with-box",
            "--box is one rectangle already, so there is nothing for --per-frame to vary",
            fix="drop --per-frame, or state the box with --aspect or --inset",
        )
    if per_frame and (asset is not None or anchor_in is not None):
        # An asset's authored boxes are one set for the frame set — `sidecar.transformed_
        # document` takes a single move — and its anchor is one point. A crop that differs
        # per frame has no single transform for either of them to follow (R3.5).
        raise UsageError(
            "per-frame-with-a-record",
            "authored boxes and an anchor are one record for the set, and cannot follow a "
            "different crop on every frame",
            fix="crop the set to one box, or write the frames with --out and record them later",
        )
    anchor = parse_anchor(anchor_in)
    stated = [given for given in (box_in, aspect_in, inset_in) if given is not None]
    if len(stated) != 1:
        raise UsageError(
            "no-box" if not stated else "two-boxes",
            "give exactly one of --box, --aspect and --inset"
            + (f", not {len(stated)}" if stated else ""),
            fix="--box 4,8,16x16 cuts a rectangle; --aspect 16:9 and --inset 8 compute one",
        )
    box = parse_box(box_in) if box_in is not None else None
    ratio = parse_ratio(aspect_in) if aspect_in is not None else None
    insets = parse_insets(inset_in) if inset_in is not None else None

    frames = read_frames(source)
    # One rectangle for the set by default (R2.1), computed against the first frame's
    # canvas: the frames of a set share one, and a frame that does not is what R1.6 refuses
    # over. `--per-frame` is the way to say that a directory of mixed sizes was meant.
    canvases = [(frame.image.shape[1], frame.image.shape[0]) for frame in frames]
    rects = [
        rect_for(canvas, box=box, ratio=ratio, insets=insets, gravity=gravity)
        for canvas in (canvases if per_frame else canvases[:1] * len(frames))
    ]
    rect = rects[0]
    cropped = cut(frames, rects)
    images = [frame.image for frame in cropped]

    sidecar_path: str | None = None
    if asset is not None:
        written, sidecar_path = transform_into_asset(
            asset,
            images,
            command="tool crop",
            stage="crop",
            params={"box": rect.as_dict()},
            source=source,
            total=len(frames),
            move=partial(trim_box, kept=(rect.x, rect.y, rect.width, rect.height)),
            dry_run=dry_run,
        )
    else:
        assert out is not None
        written = [str(path) for path in write_frames(source, out, cropped, dry_run=dry_run)]

    payload: dict[str, Any] = {
        "frames": len(cropped),
        "box": rect.as_dict(),
        "size": {"width": rect.width, "height": rect.height},
        "written": written,
    }
    if any(other != rect for other in rects):
        # Only where they actually differ, which is `--per-frame` over a set at more than
        # one canvas size. A `boxes` list repeating one rectangle ninety times would bury
        # the fact that the interesting case is the one where they are not all the same.
        payload["boxes"] = [
            {"frame": frame.name, "box": each.as_dict()}
            for frame, each in zip(frames, rects, strict=True)
        ]
    if asset is not None:
        payload["sidecar"] = sidecar_path
    if anchor is not None:
        # A crop is a trim to a stated box, so the anchor moves by the box's origin — the
        # same arithmetic, from the same function `tool trim` uses.
        moved = trim_anchor(anchor, box=(rect.x, rect.y, rect.width, rect.height))
        payload["anchor"] = {"x": moved[0], "y": moved[1]}
    varied = "boxes" in payload
    return Result(
        "tool crop",
        f"{len(cropped)} frame{'' if len(cropped) == 1 else 's'} cut to "
        + ("a box of their own" if varied else f"{rect.width}x{rect.height}"),
        payload,
        dry_run=dry_run,
    )
