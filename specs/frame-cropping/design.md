# Frame cropping — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R1.7, R2.1, R2.2, R2.3, R2.4, R3.1, R3.2,
R3.3, R3.4.

Two new modules and one line of registration.

`src/ssc/core/crop.py` is pure geometry and returns rectangles, never images — the same
split `core/recover.py`'s docstring makes for the same reason: an aspect fit can then be
tested against a canvas size with no image in play. It holds `aspect_rect(canvas, ratio,
gravity)` (R1.4) and `inset_rect(canvas, insets)` (R1.5), both returning the `Rect` that
`core/recover.py` already defines, and both raising `ValueError` where the result would
be empty (R1.7).

Nothing in the new module cuts pixels. `core.recover.crop(image, rect)` already does
that, and already refuses a rectangle that is not wholly inside the image with the
message R1.6 asks for — a numpy slice past the edge truncates silently, which is the
defect that function was written against.

`src/ssc/cli/commands/crop.py` is the command, shaped like `tool trim` in
`commands/recover.py`: `--in` a file or a directory through `read_frames`, exactly one of
`--asset` and `--out` through the existing `destination` guard (R3.1), and the write
through `transform_into_asset` or `write_frames`. `app.py` attaches it to the `tool`
group.

**A crop is a trim to a stated box**, so the recorded stage moves what a trim moves:
`trim_anchor` gives the anchor's new position (R3.4) and `trim_box` moves each authored
box and returns `None` for one that falls outside (R3.3), both from `core/assemble.py`
and both already tested. Writing a second pair of movers for the same arithmetic is how
the two would come to disagree.

## Boundaries and contracts

The recorded stage is `crop`, and its parameters carry the rectangle as
`{"box": {"x", "y", "width", "height"}}` — the shape `Rect.as_dict` already emits and
`tool trim` already records. No `schema` constant moves: a stage name and its parameters
are open, and `meta.json`'s shape is untouched.

## Alternatives considered

**A `--per-frame` that crops each frame to its own content**, which is what "a box
computed per frame" first suggests. Rejected: content detection belongs to `tool trim`,
and a second implementation of it under another command is the copy that drifts. Here
`--per-frame` varies only with the canvas — for a set whose frames share one canvas the
two modes produce the same rectangle, and the flag earns its place on a directory of
loose frames at differing sizes, where the default refuses under R1.6 because the shared
box does not fit the smallest frame. That refusal is the desirable half: a set at mixed
sizes is not registered, and cropping each frame to its own canvas is a deliberate act.

**Folding this into `tool expand` as a negative `--by`.** Rejected as stated in the
requirements' Out of scope: one command that both cuts and pads makes a sign error the
difference between losing content and gaining margin.

## Risks

**Gravity is nine values and off-by-one errors in it are invisible.** A crop placed one
pixel off looks like a crop, and the damage only shows when the set is packed and the
sprite jitters against its anchor. That is why the aspect fit is the one task built
test-first: the properties — the fitted rectangle is inside the canvas, its ratio is the
closest the canvas allows, and opposite gravities place it against opposite edges — are
what a test can hold and an eye cannot.
