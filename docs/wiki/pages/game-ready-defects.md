# Game-ready defects

Image and video models produce art that looks finished and is not usable. The defects
are systematic rather than accidental — they follow from how the models work — which is
why each one can be measured rather than judged.

This is the vocabulary the rest of the knowledge base assumes. Seven of these are the
checks `ssc tool doctor` ships with; `seam` and `nineslice` arrive later, with the kinds
that need them, as deltas against the doctor spec rather than as a second detector. One
defect on this page is deliberately not a doctor check at all — see the last section.

## Fake pixels

The model draws something that *looks* like pixel art: blocks of colour in a grid. Zoom
in and the blocks are made of smaller pixels with blurred boundaries. Nothing snaps to a
real grid, so the asset cannot be scaled, recoloured or animated without the blur
compounding.

Measured as `pixel_grid`. Repaired by [[pixel-snapping]].

## Frame bleeding

A model given a grid to fill does not respect the cell boundary. A sword tip or an elbow
from one frame crosses into its neighbour. Cutting the sheet on the grid lines then
carries a fragment of frame 4 into frame 3.

Measured as `bleed`. The repair is not a better prompt — it is to recover each frame by
its bounding box instead of slicing the grid. See [[frame-normalisation]].

## Frame drift

The character is not in the same place in every frame. Played back, it slides and
judders across the screen even though the animation is "walking in place". The cause is
that nothing locked the feet to a fixed point.

Measured as `drift`. Repaired by anchoring — see [[frame-normalisation]].

## Halo

Image models do not produce native transparency, so the workflow asks for a flat chroma
background and removes it afterwards. Done carelessly, a ring of semi-transparent
green-tinted pixels survives around the silhouette and glows against the game's
background.

Measured as `halo`: the count of pixels with alpha strictly between 0 and 255.

## Palette drift

Every asset is quantized independently, so each one lands on a slightly different set of
colours. Individually they look fine; together the game looks like a patchwork. This is
the defect that only appears once there are twenty assets, which is what makes it
expensive to discover late.

Measured as `palette`, against a palette locked for the project.

## Flicker

The animated cousin of palette drift. A region that did not move changes colour between
adjacent frames, because each frame quantized on its own. The eye reads it as noise
crawling over a still surface.

Measured as `flicker`. The fix is structural rather than corrective: compute one palette
across the whole set of frames, not one per frame.

## Silhouette loss

What survives being shrunk to a 48-pixel-wide sprite is the outline, not the detail — so
the shape carries the character and a shape that stops reading is the asset failing at
the size it will actually be played at. It goes wrong from both directions: a model that
answered a prompt with photorealistic rendering produces a blob with no readable outline,
and background removal that took too much punches holes in the body it was supposed to
leave alone.

Measured as `silhouette`, and **`specs/sheet-doctor/` settled what that means**: the
integrity of the alpha mask, reduced to the target cell — the count of background regions
the body encloses (`holes`) and the count of separate opaque regions (`fragments`).
Reducing first is what keeps "at the size it is played at" honest: a gap that does not
survive the reduction was never going to be seen.

Readability of the outline was the other reading and it was **not** adopted. Every
candidate number for it is a proxy for a person's judgement about whether a shape reads,
and a check reporting a number nobody defined is a judgement wearing a number's clothes.
The blob-with-no-outline case it was meant to catch is not left uncovered — such art has
no pixel grid, so `pixel_grid` reports it, and where it needs a person it gets one at the
review gate.

It pairs with `halo` from the opposite side: `halo` is background removal leaving too
much, this is it taking too much.

## Seam

*Arrives with the tile kind, not with the first doctor.*

A tile that does not tile. The right edge does not continue into the left edge, so a
repeating floor shows a visible grid of lines. Generation cannot be trusted to close it —
the commercial tools that offer "seamless generation" say so in their own documentation.

Measured as `seam`, by comparing the wrap-adjacent edges.

## Nine-slice breakage

*Arrives with the UI kind, not with the first doctor.*

A UI panel stretched by the engine distorts its corners, or its slice guides fall between
pixels so the border shimmers. The check renders the panel at 2× and requires the corners
to come back bit-identical.

Measured as `nineslice`.

## Broken cycles — the one that is not a doctor check

A walk that does not close: the last frame does not hand back to the first, so the loop
visibly hitches once per cycle. It belongs in this vocabulary because it is one of the
systematic defects, but it is not something `doctor` reports on a finished sheet — it is
a property of *where the frames were sampled from the clip*, so it is measured at that
moment, by the loop score `extract --cycle` returns. See [[generating-animations]].

The distinction is worth keeping straight: `doctor` measures an artefact that already
exists, the loop score decides a cut that has not been made yet.

## Why measurement is the point

Every defect above is a number and a named fix, never a judgement. That is what closes
the loop for an agent: it does not have to decide whether something "looks right", it
reads the measurement and runs the command that repairs it. A judgement an agent cannot
verify is a judgement it will get wrong under load.

Which is exactly why `silhouette` having no settled metric is a real gap and not a
detail. A check that reports a number nobody defined is a judgement wearing a number's
clothes, and it would be the one entry on this page an agent could not act on.
