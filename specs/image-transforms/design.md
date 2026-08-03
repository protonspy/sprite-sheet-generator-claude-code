# Image transforms — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R2.3.

`core/assemble.py` already has `flip`, which is `frame[:, ::-1]` — a reversed index, not a
resample. Everything here is that same move: `np.flipud` for the other axis, `np.rot90` for
a quarter turn. No filter, no interpolation, no new dependency, and the output is exactly
the input's pixels in a different order.

That is the whole architectural content, and it is why R1.3 is a refusal rather than a
feature nobody got to. Any angle that is not a multiple of 90° maps source pixels onto
positions between destination pixels, and something has to decide what lands there — which
is a resampler, which `specs/workspace-foundation/` forbids outright and
`tests/test_no_other_resampler.py` fails the suite over.

`tool mirror` grows an `--axis`, defaulting to the vertical axis so every existing call
keeps meaning what it meant. `tool rotate` is a new command rather than `mirror --turns`,
following the split `tool board` already uses: two operations taking different parameters
are two commands, because a flag that changes which other flags are legal is a worse
interface than a second name.

## Boundaries and contracts

Serves R2.1, R2.2, R2.4.

**The anchor is the part that is easy to get wrong.** Mirroring about the vertical axis
moves a pixel at `x` to `width - 1 - x`, and the `- 1` is the whole bug: get it wrong and
every sprite sits one pixel off, which reads as a character that jitters when it turns.
A quarter turn swaps the axes and reverses one of them, and which one depends on the
direction of the turn. Small, exact, and invisible when wrong — which is why its task is
the TDD one.

**An odd quarter turn swaps width and height.** A 64×48 frame becomes 48×64. For a square
cell nothing shows; for a non-square one the frames stop fitting the cell their kind
declares and `pack` would place them wrongly. R2.4 makes that a report rather than a
surprise: the command says what the new dimensions are and which cell they stopped
matching, and leaves the decision there, because changing a kind's cell is a project
decision and not a side effect of turning a picture.

**Per-frame boxes and markers belong to `specs/frame-metadata/`, and this spec does not
wait for them.** R2.2 is written now because the transform is where they would silently
rot: a hurt box is a rect in frame coordinates, and a mirrored frame with an unmirrored
hurt box is a character that takes damage on the wrong side. When that leaf lands it
inherits a requirement that already says what must happen, instead of a transform command
somebody has to remember to revisit.

## Alternatives considered

**Rotating by an arbitrary angle with nearest neighbour.** It picks the closest source
pixel rather than blending, so it looks like it slips past the one-resampler rule. It does not survive
contact with pixel art: rotating a grid by 30° gives ragged, unevenly stepped edges,
because a diagonal line of blocks is not a rotated line of blocks. The result is worse than
blur and harder to explain, and the honest answer to "I want this at 30°" is that the art
has to be drawn at 30°.
