# Normal maps — design

## What changes

Serves R1.1, R1.2, R1.4, R1.6, R2.1, R2.2.

A new pure module `core/normal.py` and a `ssc tool normal` command.

**Luminance, Sobel, normalise.** The height field is Rec. 601 luminance of the RGB. The
slopes are a 3x3 Sobel on each axis — a wider kernel than a plain difference because a
one-pixel difference on pixel art is all edge and no surface, and Sobel's smoothing across
the perpendicular axis is what makes a block read as a facet rather than as four cliffs.
The normal is `(-dx * strength, -dy * strength, 1)` normalised, encoded to `0..255` by the
usual `v * 0.5 + 0.5`.

**Transparency is a hole, not a colour.** A transparent pixel has RGB that is often black
and always meaningless, and letting it into the Sobel window puts a cliff around every
sprite's silhouette — the single most visible way to get this wrong. So the height field is
built with transparent pixels filled from the nearest opaque luminance rather than from
their own, the slopes are taken on that filled field, and the output is overwritten with a
flat normal wherever alpha is zero (R1.4).

**The fill is exactly one dilation, and one is provably enough.** Only a transparent pixel
*inside* an opaque pixel's 3x3 window can affect that pixel's slope, and every such pixel is
a direct neighbour of an opaque one. Anything further out cannot reach an opaque window and
is overwritten flat on the way out, so a constant is all it needs to be.

It is padded slicing rather than `np.roll`, and that is not a style choice: the edge of the
canvas is an edge, not a seam onto the opposite side. A sprite that touches two edges of its
frame — which any cropped or keyed one does — would otherwise have the far side's art
averaged into its own, silently. Bounding it at one pass is also what keeps the cost tied to
the pixel count rather than to the width of the transparent margin; the loop it replaced ran
once per pixel of margin over the whole array.

Every intermediate is `float32`. The values are 0..255 and the arithmetic is a weighted sum
and a Sobel, so single precision is more than enough, and the intermediates are several
image-sized arrays plus an eight- and a nine-deep stack — at `frames.MAX_PIXELS` that choice
is worth several gigabytes.

**The output's alpha is the input's alpha**, so the map's silhouette matches the sprite's
and an engine sampling outside it gets nothing rather than a flat blue rectangle.

## Boundaries and contracts

Serves R1.3, R1.5.

`core/normal.py` is pure — `ndarray` in, `ndarray` out, `ValueError` for a refusal — and the
command translates that to `UsageError` the way the others do. `--strength` is bounded on
both sides: at zero every normal is flat and the map is a solid colour, which is a silently
useless output rather than an error, so the floor is above zero.

Nearest neighbour does not arise here: the map is the size of its input and nothing resizes.

**`Profile.normal_map` is read by nobody yet, and this leaf deliberately does not change
that.** The field says whether a kind *should* have a map produced by default, which is a
statement about a pipeline that runs commands for you — `ssc run`, in
`specs/gates-and-resume/`. Wiring it here would mean inventing that pipeline's shape from
inside a leaf that has no view of it.

## Risks

**Painted shadows read as geometry.** Art that already contains its own lighting produces a
normal map describing that lighting rather than the surface, and the sprite then lights
wrongly in a way that looks like a bug in the engine. It is inherent to inferring height
from luminance and is recorded in the requirements' *Out of scope* so nobody spends a
release trying to filter it out.
