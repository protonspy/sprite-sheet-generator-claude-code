# Game-ready defects

Image and video models produce art that looks finished and is not usable. The defects
are systematic rather than accidental — they follow from how the models work — which is
why each one can be measured rather than judged.

This is the vocabulary the rest of the knowledge base assumes, and the list `ssc tool
doctor` reports against.

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

## Seam

A tile that does not tile. The right edge does not continue into the left edge, so a
repeating floor shows a visible grid of lines. Generation cannot be trusted to close it —
the commercial tools that offer "seamless generation" say so in their own documentation.

Measured as `seam`, by comparing the wrap-adjacent edges.

## Nine-slice breakage

A UI panel stretched by the engine distorts its corners, or its slice guides fall between
pixels so the border shimmers. The check renders the panel at 2× and requires the corners
to come back bit-identical.

Measured as `nineslice`.

## Why measurement is the point

Each defect above carries the command that repairs it. That is what closes the loop for
an agent: it does not have to decide whether something "looks right", it reads a number
and runs the named fix. A judgement an agent cannot verify is a judgement it will get
wrong under load.
