# UI assets — design

## What changes

Serves R1.1, R1.2, R1.3, R1.5, R2.1, R2.2, R3.1.

A new pure module `core/ninepatch.py`, a `nineslice` check in `core/doctor/checks.py`, and
two commands: `ssc tool ninepatch` and `ssc tool states`.

**A guide is a distance from an edge, snapped to the pixel size.** `left=8` means the left
column of regions is eight pixels wide. Snapping is the whole of R1.2: `snap` and `pixelart`
leave art whose real pixels are blocks of N screen pixels, and a guide at 9 with a pixel size
of 4 puts the boundary inside a block — the engine then stretches three quarters of one
pixel-art pixel, and the border shimmers at some widths and not others. The pixel size comes
from `doctor.detect_pixel_size`, which already exists and is already this project's answer to
"what grid is this art on".

**Derived guides are one pixel-art pixel on every side.** Not an inference about the drawing —
the requirements put reading the border off the art firmly out of scope — but the smallest
guide that can be right, and the one a caller adjusts from.

**`nineslice` measures what stretching will do.** An edge region is repeated along one axis,
so what matters is whether it is *constant* along that axis: a left edge that changes down its
height cannot be stretched vertically without the change being smeared. The check takes, for
each stretched region, the variation along its own stretch axis — the four edges on one axis
each, the centre on both — and reports the largest. A region uniform along the direction it
stretches scores zero, however busy it is in the direction it does not.

That is why R2.4 exists: without guides there are no regions, and guessing them to produce a
number would be measuring something nobody asked about. Like `seam`, it is asked for rather
than run by default.

## Boundaries and contracts

Serves R1.4, R2.3, R2.4, R3.2, R3.3.

`core/ninepatch.py` is pure and raises `ValueError`; the commands translate to `UsageError`.
`Check` gains `NINESLICE`, recorded as a delta in `specs/sheet-doctor/` the same way `seam`
was — that enum's docstring named both from the start.

**The four state names are a closed set, deliberately, and this is the one place in the
project where a closed set is right.** An engine looks up `hover`; a file named `hovver` that
packs silently produces a control whose hover state nothing ever queries, and the failure
appears as "the button doesn't light up", with no error anywhere to explain it. Refusing and
naming the four is the only outcome a caller can act on. This is not the `kind` situation — a
kind is an open-ended taxonomy a project extends, and these four are a fixed vocabulary an
engine already speaks.

## Risks

**A derived guide is almost always wrong for the art.** One pixel-art pixel per side is the
smallest defensible guide, not the right one for a panel with a four-pixel bevel. The report
carries the nine region sizes precisely so a caller can see that the corners came out 4x4 and
pass real guides; a defaults-are-fine reading of this command produces panels that stretch
their own border.
