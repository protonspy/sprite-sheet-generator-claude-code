# Sprite normalisation gate

The instability that survives everything else `ssc` does is **between** the animations of
one asset, not inside any one of them: the sprite grows two pixels when it starts walking,
its feet sink through the floor mid-animation, the cell the engine addresses is wrong for
one of the sets. `tool align` locks one anchor across the frames of a set; nothing makes
idle's baseline agree with walk's. This page is the gate that does — six steps, each an exact
command, each catching one failure mode, with `doctor` reporting between them so a number
rather than an eye says when to move on.

The three commands the gate adds are `tool bounds`, `tool normalise` and `tool preview`
(plan `sprite-normalisation-gate`); `tool doctor` carries the `scale` check that ties them
together. The vocabulary is [[game-ready-defects]] and [[frame-normalisation]]; the anchor is
[[anchor-and-directions]]' feet anchor, and the resampler is [[pixel-snapping]]'s
nearest-neighbour one.

## 1. Measure each frame — `tool bounds`

```
ssc tool bounds --in walk/
```

Reports, per frame, the alpha bounding box — `x`, `y`, `width`, `height`, `baseline`,
`centre` — and, per set, each as a median with a spread. **`baseline`** is the lowest occupied
row (the feet); **`centre`** is the body's centre in that row; **visible height** is the
alpha box's height, never the canvas. The spread is the within-set jitter.

**Catches:** a frame with no coverage (`bounds: null` — a blank a caller mistook for a
sprite at the origin), and within-set jitter larger than a pixel in baseline or centre, which
is the drift [[frame-normalisation]]'s anchor step is there to remove before it is measured
across sets.

## 2. Doctor the set — `tool doctor`

```
ssc tool doctor --in walk/ [--cell 64x64] [--cols 8 --rows 1] [--palette rrggbb,...]
```

The seven checks on one set: `pixel_grid`, `bleed`, `drift`, `halo`, `palette`, `flicker`,
`silhouette`, plus `consistency`. Each is a number and a fix, never a judgement — a skipped
check says why. Run this per set before measuring across sets, so a defect inside one
animation is not read as a cross-set problem.

**Catches:** everything [[game-ready-defects]] names that lives inside one set — a halo, a
bleeding cell, a drifting anchor, a flickering palette, a broken silhouette — each with the
command that repairs it.

## 3. Measure across sets — `tool doctor` with the `scale` check

```
ssc tool doctor --in idle/ --in walk/ --in attack/
```

The first `--in` is the set the seven checks run on; each further `--in` names another set of
the same asset. The `scale` check is the only one that reads them: it reduces each set to
its median visible height and reports `variation_px` — the range across sets — with
`ssc tool normalise` as its fix. One pixel of variation is noise (it sits at the
nearest-neighbour resampler's own ±1 rounding floor); two is the defect.

**Catches:** the sprite that grows between animations — the one failure that reaches a
running game and that no within-set check can see, because every set is clean on its own.

## 4. Normalise — `tool normalise`

```
ssc tool normalise --in idle/ --in walk/ --out normalised/ [--anchor feet] [--cols 8]
```

Resamples each set onto one target visible height (the median of the sets' medians), moves
every frame of every set onto one anchor pixel through `plan_alignment`, and lays each set
out as a sheet of equal cells through `pack`. Padding and layout are those two; this
command orchestrates them and the scale decision, and reimplements neither. A set already on
the target is left untouched — an identity resample would risk the very drift the gate
exists to remove, for no gain.

**Catches:** scale drift between sets, a baseline or centre that disagrees across
animations, and a cell size that differs per action so the engine's cell is wrong for one of
them — the three failures step 3 measured.

## 5. Re-doctor the normalised sheets — `scale` reports `0`

```
ssc tool doctor --in normalised/idle.png --in normalised/walk.png
```

The same `scale` check, now on the output of step 4. `variation_px` should be `0` (or `1`,
which the resampler cannot reliably remove). This is the number that says the gate closed —
not the eye, and not the fact that step 4 exited `0`.

**Catches:** a normalise that did not land — a set whose resample rounded the wrong way, or a
blank set that refused and was missed. If the variation is still above one, go back to step 4;
the gate is not closed.

## 6. Preview — `tool preview`

```
ssc tool preview --in normalised/walk.png --out walk.gif --fps 12 --mode ping-pong
ssc tool preview --in normalised/walk.png --out walk.png --contact   # a labelled sheet
```

Renders the normalised set as an animated GIF at the declared frame rate and playback order
(`loop`, `ping-pong`, `reverse`), or a contact sheet with each frame labelled by its index —
through the one renderer `ssc preview` uses for the index path, so nothing here is a second
renderer. For a sheet input, `--cell WxH` with `--cols` and `--rows` cuts it into frames
first.

**Catches:** what a number cannot — a stutter at the turn of a `ping-pong`, a foot that
slides, a flicker the eye sees and the threshold missed. This is the last step because
everything before it is what makes the preview worth watching.

## Why it is a gate, not a command

The six steps are run by a person, in order, and the person moves on when the number says so
— `bounds`' spread, `doctor`'s `scale` `variation_px`, then `scale` again at `0`. Folding
them into one command would either skip the between-steps measurements (the point of having
them) or print a report nobody reads. The gate is the smallest thing that makes a person
look at the right number at the right time, and `doctor` is what carries the numbers between
the leaves.