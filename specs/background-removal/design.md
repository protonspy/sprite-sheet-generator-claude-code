# Background removal — design

## What changes

Serves R1.3, R2.1, R2.3, R3.1, R3.2.

One new pure module, `core/bgremove.py`, and one command added to the existing
`cli/commands/convert.py` — which already holds the other three `--in`/`--out` commands and
already carries the frame-set reading, the output refusal and the size ceilings this one
needs. A second module for a fourth command of the same shape would be a file boundary
drawn where no design boundary is.

The pipeline per frame, in order, each step optional except the first two:

```
key mask  →  flood or global  →  despeckle  →  edge trim  →  edge pass  →  binary alpha
```

The order is the design. `despeckle` before `edge-trim` because trimming first turns a
speck into a smaller speck rather than removing it; `edge-pass` last because it reads the
final silhouette to decide which pixels border the transparent region.

## Flood, and why it is the default

Matching every pixel of the key colour is the failure this leaf exists to avoid: a green gem
inside a character is not the background, and `global` eats it. `flood` labels the
key-coloured region, keeps only the labels touching the border, and leaves anything enclosed
by the subject alone.

This came from reading a competitor's tool documentation rather than from first principles —
their chroma key has exactly this Global/Flood split, and ours would have shipped with only
the global behaviour. `docs/wiki/prior-art.md` carries that.

`global` stays because it is right when the subject genuinely has no enclosed key-coloured
region and the background is not connected — several disconnected patches of backdrop behind
a spread pose, for instance, where a flood from the border reaches only some of them.

## Binary alpha, and what `--edge-pass` therefore is

R3.1 forces alpha to 0 or 255, so `--edge-pass` cannot be about alpha. What it removes is
**colour spill**: the pixels that were partly key-coloured keep a green or magenta cast in
their RGB after the alpha decision, and that fringe is what reads as a halo to a human even
when `doctor` sees clean alpha.

So the edge pass clamps the key's dominant channel on border pixels down to the strongest of
the other two — the standard despill, and the reason it is a flag rather than the default is
that it changes colours the caller may have wanted.

`doctor`'s `halo` check names `ssc tool bgremove --edge-pass` as its fix and did so before
this leaf existed. That string is a promise this spec is obliged to keep, and it is why the
flag could not be called anything else.

## Alternatives considered

**Distance in RGB rather than in a chroma-separated space.** Real chroma keying separates
luma from chroma so a shadowed green and a lit green are one colour. Plain RGB distance is
worse at that, and it is what this ships: the input is a model's flat backdrop or a
generated board, not filmed footage, and the tolerance is a caller's dial rather than an
inference. If a real backdrop turns out to need it, the change is inside `key_mask` and
touches nothing else — which is the reason to keep that function alone in the first place.

## Risks

**`--tol` interacts with everything downstream.** Too low leaves a speckled background that
`despeckle` then has to clean; too high eats the subject and `edge-trim` makes it worse.
Nothing here can detect that, which is what `tool doctor` is for — `halo`, `silhouette` and
`palette` all read the result — and eventually what `tool sweep` is for.
