# Pixel snapping

Snapping turns fake pixels into real ones: it finds the grid the image is pretending to
have and collapses the blurred sub-pixel noise onto it. See [[game-ready-defects]] for
why the model produces fake pixels in the first place.

## The algorithm

1. Reduce the image to a fixed number of colours.
2. Analyse edges along both axes and collapse blurred sub-pixel runs into single grid
   pixels.
3. The result is a genuinely small image where one pixel means one pixel.
4. Scale it back up with **nearest neighbour** to the working size.

Step 4 is the one people skip. Nearest neighbour preserves the hard edges; every other
resampler reintroduces exactly the blur the first three steps removed.

## Nearest neighbour is an invariant, not a step

Once an image has been snapped, *no* resize anywhere in the pipeline may use anything
else — not the scale back up, not the reduction to the final cell size, not a preview.
One careless bilinear resize undoes the whole thing, and the damage is invisible at a
glance and obvious at 4× zoom.

This is a constraint on the tool's own code as much as on the workflow.

## It happens twice

Once on the anchor, so that the reference the model works from is already clean. Again on
each frame recovered from a generated sheet — because the model's output is blurry
regardless of how clean its input was.

The practical consequence: snapping is not a one-shot finishing step. It runs on every
frame of every animation, so it has to be cheap and it has to cache.

## Where the resolution decision lives

The pixel size is the project's visual era, roughly:

| Pixel size | Reads as |
|---|---|
| 16 | early-80s home computer |
| 32 | mid-80s adventure game |
| 48–64 | 16-bit console |
| 96+ | modern high-resolution pixel art |

It is a project-wide decision, not a per-asset one: mixing pixel sizes across assets is
the same failure as [[game-ready-defects]]' palette drift, in geometry instead of colour.

## Prototype first, snap later

Snapping is not required to start building a game. Fake pixels are fine for testing
whether the character feels right to control. The fidelity problem is real but it is not
urgent, and treating it as a blocker stops people from getting anything moving on screen.
