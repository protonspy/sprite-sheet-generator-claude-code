# The two reference boards

Two images get passed to an image model alongside the prompt. They do different jobs and
they are not interchangeable — passing the wrong one produces plausible garbage.

## The checkerboard

A black-and-white checkerboard, passed as a reference image together with the prompt.
Its role is to impose block discipline: it pushes the model toward flat cells of colour
instead of smooth gradients. Without it, asking for "pixel art" yields a painting that
merely resembles pixel art.

Sources disagree on the square size. One describes a board alternating every single
pixel; another describes a grid of black and white *squares*. Those are different images
and produce different results, and which one wins is a per-model empirical question —
which is why `ssc tool board` generates it at a chosen square size instead of shipping
one frozen PNG.

## The pose board

A canvas already divided into the animation's frame layout — 4×3 cells at 512×512, for
instance, making a 2048×1536 image — passed together with a prompt that names the
sequence frame by frame.

**Cells must be large.** 512×512 is a floor, not a target. The snapper needs detail to
work from, and it runs on each recovered frame individually; a frame that arrives at
128×128 has already lost what the snap would have preserved. 256×256 is the *final* size,
reached after snapping, not the size to generate at.

## Never in video

`gen video` passes neither board. A video model given a grid merges the grid into the
character's body — the lines end up painted on the armour. This is why image and video
generation are separate commands with separate templates rather than one command with a
flag: a mistake that is structurally impossible cannot be made under time pressure.

## Boards are generated, not downloaded

Both are trivially computable, and both are distributed by their popularisers as
downloads behind a mailing list. Generating them avoids vendoring somebody else's file
under a licence this project does not have, and — more importantly — keeps the square
size and cell size as parameters that track the project instead of constants frozen into
an asset.

See [[anchor-and-directions]] for how the checkerboard is used, and
[[generating-animations]] for the pose board.
