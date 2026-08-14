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

## Attaching one

`ssc gen image --board` attaches the board the resolved style names — `pixel-art` names the
checkerboard, and no other shipped style names one — generating it at the size the call asks
for. It is a flag rather than something the style does on its own: `pixel-art` is the
default look for every kind, so attaching a board whenever the style names one would put a
grid on every image call ever made, and a board is right for an anchor and wrong for a
direction being drawn *from* that anchor.

Any file can be a board instead: `--ref <path>:board` says what the image is for without
generating anything. The role is what carries the lesson — *take block discipline from it
and never take its content* — which used to be a sentence in the `anchor` template. It moved
because that sentence said **any** image supplied alongside the prompt is a board, and a
call can now carry two.

## Boards are generated, not downloaded

Both are trivially computable, and both are distributed by their popularisers as
downloads behind a mailing list. Generating them avoids vendoring somebody else's file
under a licence this project does not have, and — more importantly — keeps the square
size and cell size as parameters that track the project instead of constants frozen into
an asset.

See [[anchor-and-directions]] for how the checkerboard is used, and
[[generating-animations]] for the pose board.
