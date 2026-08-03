# Parallax layers — design

## What changes

Serves R1.1, R1.2, R2.1, R2.2, R2.3.

A `background` built-in kind, a `layered` field on the kind profile, and a `ssc tool layers`
command. No new module under `core/`: there is no pixel operation here at all, which is the
honest shape of this leaf — every requirement is about the *set* and the numbers attached to
it, and the layers themselves are passed through untouched.

**Order is the file order, and the far layer is first.** `read_frames` already orders a
directory by filename, which is the ordering that survives being copied around; a stack named
`01-sky.png`, `02-hills.png`, `03-trees.png` reads in depth order without anyone declaring
one. Depth-first rather than near-first because that is the order they are drawn in, so the
index reads the same way the engine composites.

**A derived scroll factor is linear in the layer's position** — the far layer at `1/n`, the
near one at `1`, evenly spaced between. It is a starting point rather than a claim: real
parallax is a ratio of distances and nobody knows the distances, so the number a caller
tunes by eye is the real answer and this is what they tune *from*. R2.3 exists so that a
three-layer stack is usable before anyone has an opinion.

## Boundaries and contracts

Serves R1.2, R2.4, R2.5, R2.6.

`Profile` gains `layered: bool`, a delta against `specs/asset-kinds/` — that spec's whole
argument is that a kind is an extensible profile rather than an enum, so a new field there
is the mechanism working rather than a hole in it. `background` is the seventh built-in.

Three refusals, all of them about the *set* rather than about any image: a factor outside
zero to one, layers of differing size, and a count of factors that does not match the count
of layers. The second is the one that matters in practice — an engine scrolls every layer
across one viewport, so layers of different sizes are not a stack, and letting them through
produces a background that tears at whichever edge runs out first.

## Risks

**A scroll factor of zero is legal and means "never moves".** It is a sky, and it is a
legitimate thing to want, so the range is inclusive at both ends. That makes zero and "the
caller forgot to pass this" indistinguishable in the value itself — which is why an empty
`--scroll` derives the whole ladder rather than defaulting individual layers to zero.
