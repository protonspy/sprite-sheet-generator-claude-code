# Clip sampling — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R2.1, R2.2, R2.3, R2.4, R3.1, R3.2, R3.3, R3.4, R4.1, R4.2.

`src/ssc/core/clip.py` is new and holds the two things worth testing on their own: where a
cycle closes, and which frames to take across a range. Both are arithmetic over frames, so
neither reads a file — the same split `core/recover.py` makes, and the reason the cycle
finder can be tested against a handful of 8x8 arrays.

`src/ssc/cli/clip.py` reads the container. `cv2.VideoCapture` is what decodes it, from
`opencv-python-headless`, which is already a direct dependency for connected components and
morphology — so nothing is added to `docs/stack.md` and the `[cv]` extra is not involved.
The reader is separate from the geometry for the ordinary reason and one specific one: a
decoder is where the failures are, and keeping it away from the arithmetic means the
arithmetic has no failures to have.

`src/ssc/cli/commands/clip.py` is the command, shaped like `tool crop`: `--in`, exactly one
of `--asset` and `--out`, the same `destination` guard and the same `transform_into_asset`.

## The cycle

A walk cycle returns to its first frame. So the closing frame is the one, after a floor,
whose pixels are nearest the first — and the cycle is everything before it.

**The measure is a new one, and `core/curate.py`'s is deliberately not reused.** Curate
answers *has anything changed at all* and counts the share of pixels that differ, which is
right for dropping a frame that says nothing new and wrong here: every pixel of a frame one
shade darker differs, so a returning clip reads as never returning. This asks *how far from
the same picture is it*, which is a magnitude — the mean channel difference. Two measures
for two questions, rather than one measure answering the wrong one.

Two numbers make it a decision rather than a guess:

- **A floor** (R2.2). Frame 1 is always near frame 0, and without a floor every clip has a
  one-frame cycle. The floor is a fraction of the clip rather than a constant, because a
  cycle is a share of a clip somebody generated to hold one.
- **A ceiling on the distance** (R2.3). A clip that does not loop — a death animation, a
  model that drifted — has no frame near its first, and the nearest one is still far. Past
  the ceiling the answer is *none*, reported as such, and the whole clip is sampled.

Both are stated as constants with the argument written beside them, and neither is a flag:
a caller who wants the whole clip says so with `--whole`, which is the question they
actually have.

## Sampling

`positions(count, over)` gives the indices, evenly spaced, **excluding the end of the
range**. That exclusion is the domain fact worth stating: a cycle's closing frame is its
opening frame, and a sheet holding both plays the first pose twice — a visible stutter at
the loop point, which is exactly where an animation is looked at. Sampling a whole clip
excludes the end too, and there it is merely the arithmetic being the same.

## Data

The recorded stage carries what was sampled: the frames taken, the cycle found or `null`,
the clip's own frame count and rate. That is what makes a set reproducible from the record
— the same clip and the same numbers give the same frames, since nothing here is
non-deterministic.

## Alternatives considered

**Detecting the cycle from the frame rate and a stated period.** Rejected: it assumes the
model produced exactly the motion asked for, and `docs/wiki/generating-animations.md`
records that it does not — the sources disagree about clip length by a factor of three, and
a cycle inside a four-second clip is where the useful part is.

**Extracting every frame to disk and sampling afterwards.** Rejected on the bound: a
hundred frames of a 1024x1024 clip is most of a gigabyte on disk to throw away, and R1.4
already refuses a clip past what will be decoded.

## Risks

**The cycle finder is comparing pixels, and a clip with a moving background has no frame
near its first.** That is the case R2.3 reports rather than guesses at, and the template
`gen video` sends is written to prevent it — *the background stays the same flat neutral
field it already is* is one of the sentences that earns its place there. Where it happens
anyway the caller sees `cycle: null` and gets the whole clip, which is the honest answer.
