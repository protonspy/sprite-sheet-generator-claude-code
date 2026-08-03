# Tile assets — design

## What changes

Serves R1.1, R1.2, R1.3, R1.5, R2.1, R2.2.

A new pure module `core/tile.py`, a `seam` check in `core/doctor/checks.py`, and a
`ssc tool tile` command.

**Closing the wrap is a copy, not a computation.** Two modes, and neither invents a pixel:

- **`edge`, the default.** The last column becomes a copy of the first, and the last row a
  copy of the first. Across the wrap the neighbouring pixels are then identical by
  construction, which is exactly what `seam` measures. It costs one column and one row of
  the art — visible at 32px if you look for it, and the smallest change that closes the
  boundary.
- **`mirror`.** The right half becomes the left half flipped, and the bottom half the top
  half flipped. Both wraps close because the tile is symmetric about both axes, and the cost
  is the symmetry, which reads as a pattern on a large floor.

A blend would be the third mode and is deliberately absent — see the requirements' *Out of
scope*. It is the reason this is `core/tile.py` and not a filter: everything here is a slice
assignment, so no palette entry appears that was not already in the image.

**`seam` measures against the image's own texture, not against an absolute.** A number like
"the columns differ by 40" says nothing on its own: a noisy tile differs by 40 everywhere,
and a flat one differs by 2 at a seam that is glaring. So the check computes the mean
absolute difference across each wrap boundary and divides it by the mean absolute difference
between *interior* neighbours on the same axis. A tile that already wraps scores about 1 —
the boundary is as ordinary as any other adjacency. The threshold is a multiple of that, and
that is what makes one default work for a noisy tile and a flat one alike.

## Boundaries and contracts

Serves R1.4, R2.3, R2.4, R3.1, R3.2.

`Check` gains `SEAM`. That enum's own docstring already says `seam` arrives with this leaf as
a delta rather than as a second detector, so this is the delta it anticipated. It is recorded
in `specs/sheet-doctor/`, which owns `doctor` — one modified requirement in its first group
and one added to its second, plus the task that cites it.

**`seam` runs only where it is asked for.** Unlike the seven, it is meaningless on anything
that is not a tile — every character frame in the project would report a "defect" for the
unremarkable fact that its left edge is not its right edge. `doctor --check seam` asks for it
explicitly, and a kind profile whose `checks` include `seam` asks for it too, which is what
the `tile` built-in already declares. Everywhere else it reports `skipped`, because a report
that omits a check is indistinguishable from one where the check found nothing.

The tileset index is `pack`'s output, not a new command. `atlas-packing` already derives one
id per entry from its filename and `tile`'s profile already declares `atlas_layout: grid`, so
a tileset is the cell grid *plus* the ids — one branch on the path that already exists, and
one refusal when the tiles are not all one size, which for a tileset is a defect rather than
something to pad around.

## Risks

**The ratio says nothing about uncorrelated noise, and that is correct rather than a bug.**
An image of per-pixel random values is maximally discontinuous everywhere, so no boundary in
it can be unusual, and the check reports a hard seam in one as clean. Writing the test first
is what surfaced it: the first fixture was uniform noise and the check refused to call it
broken. Every tile this pipeline produces has come through `snap` or `pixelart` and is blocky
by construction — the correlated case, where the denominator is small and the check is
sharp — so the limitation is real and out of the way. The fixture says so in prose, because
the next person to see it fail on noise should not "fix" the threshold.

**A tile that already wraps must come back unchanged in `edge` mode.** Copying column 0 over
column w-1 is idempotent only if they were already equal; if they were not, the operation is
a real edit and running it twice is the same as running it once. The test asserts both, since
a tool that quietly degrades an asset each time it is re-run is the failure this pipeline's
"nothing mutates its input" rule exists to make impossible.
