# Frame normalisation

Between a generated sheet and a usable one there is a fixed sequence of repairs. Skipping
any of them produces an animation that is visibly wrong in a way people describe as
"cheap" without being able to name it.

## Recover frames by bounding box, not by grid

The figures in a generated sheet are not centred in their cells. Cutting on the grid lines
gives every frame a fragment of its neighbour — that is [[game-ready-defects]]' frame
bleeding, and no prompt prevents it.

Instead: find the chroma background, take each figure's bounding box, extract it as its
own image. A small dilation before labelling keeps a sword tip that is separated from the
body by a few pixels attached to its owner rather than becoming its own frame.

A sheet from an unknown source needs the grid detected rather than declared — projecting
the background mask onto each axis reveals the gutters, and their spacing is the layout.

## Curate before doing more work

Not every generated frame carries information. Blink frames in the middle of an attack,
two frames that differ by nothing — drop them. This is cheaper before snapping and
aligning than after, and a shorter animation is usually a better one.

The comparison is against the last frame *kept*, not the immediately preceding frame;
otherwise a slow drift accumulates below the threshold and nothing gets dropped.

## Snap each frame

See [[pixel-snapping]]. Each recovered frame is snapped individually and scaled to the
final cell size — 256×256 is typical.

## Anchor the feet

This is the fix for frame drift. Pick a fixed point — feet, bottom edge, centre, or eyes —
and translate every frame so that point lands on the same coordinate.

Two details matter more than they look:

- **Anchor on the bottom rows, not the whole silhouette's centroid.** Arms swinging move
  the global centroid, so anchoring to it reintroduces the drift it was meant to remove.
- **Translate by whole pixels only.** Sub-pixel translation blurs, which violates the
  nearest-neighbour invariant from [[pixel-snapping]].

Onion-skinning — the previous frame ghosted under the current one — is how a person checks
this quickly.

## Remove the background, then pack

Chroma removal comes after the pixels are crisp: it is cleaner to key a hard-edged image
than a blurred one. Flood from the border rather than matching the key colour globally,
or a green gem inside the character disappears with the background.

Then pack the aligned frames into a uniform grid and record where the anchor ended up.
**That anchor point has to reach the engine** — without it the engine centres the sprite
itself and the drift comes back at runtime, after all of this work.
