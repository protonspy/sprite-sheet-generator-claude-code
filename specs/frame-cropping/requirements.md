---
autonomy: auto
ci: wait
lang: en
---

# Frame cropping — requirements

## Purpose

Framing is the one local operation `ssc` has no command for. `tool trim` cuts to the
content, `tool expand` pads a canvas and `gen expand` invents what is beyond it, but
nothing cuts a frame down to a rectangle somebody chose: a 16:9 strip out of a square
render, ten pixels off every side of a set that was generated with too much air, the
exact box a layout needs. `ssc tool crop` is that command, and it takes numbers — an
explicit box, an aspect ratio with a gravity, or an inset. It is for the caller framing a
result they already have, and for the harness doing the same on their behalf, without
paying a model to reframe what is already on disk.

## R1 · The box

- **R1.1** When `ssc tool crop` runs, the `ssc` CLI shall write each frame as the pixels inside one rectangle, resampling nothing.
- **R1.2** The `ssc` CLI shall require exactly one of `--box`, `--aspect` and `--inset`, and shall refuse a call that gives none of them or more than one.
- **R1.3** Where `--box x,y,WxH` is given, the `ssc` CLI shall cut that rectangle, in the source's own pixels.
- **R1.4** Where `--aspect W:H` is given, the `ssc` CLI shall cut the largest rectangle of that ratio that fits the frame, positioned by `--gravity`.
- **R1.5** Where `--inset` is given, the `ssc` CLI shall cut the frame down by that many pixels on every side, or by four given numbers read as top, right, bottom and left.
- **R1.6** If the rectangle is not wholly inside a frame, then the `ssc` CLI shall refuse the call and name the frame it does not fit.
- **R1.7** If the rectangle would have no width or no height, then the `ssc` CLI shall refuse the call.

## R2 · One box, or one for each frame

- **R2.1** The `ssc` CLI shall compute one rectangle for the set and apply it to every frame.
- **R2.2** Where `--per-frame` is given, the `ssc` CLI shall compute the rectangle against each frame's own canvas.
- **R2.3** If `--per-frame` is given together with `--box`, then the `ssc` CLI shall refuse the call.
- **R2.4** The `ssc` CLI shall report the rectangle it cut and the size it produced.

## R3 · What the crop carries with it

- **R3.1** The `ssc` CLI shall require exactly one of `--asset <kind>/<key>` and `--out <path>`.
- **R3.2** Where `--asset` is given, the `ssc` CLI shall record the frames as the `crop` stage, with the rectangle among that stage's parameters.
- **R3.3** Where `--asset` is given, the `ssc` CLI shall move the asset's authored boxes by the same crop, and shall drop a box that falls wholly outside it.
- **R3.4** Where `--anchor x,y` is given, the `ssc` CLI shall report where that anchor lands after the crop.
- **R3.5** If `--per-frame` is given together with `--asset` or with `--anchor`, then the `ssc` CLI shall refuse the call, because an asset's authored boxes and its anchor are one record for the whole frame set and cannot follow a different crop per frame.

## Out of scope

**Padding.** A rectangle larger than the frame is refused, not filled with transparency.
Growing a canvas is `tool expand`, and a command that both cuts and pads makes a typo in
a number the difference between losing content and gaining margin.

**Cutting to the content.** That is `tool trim`, which uses the union of every opaque
pixel across the set precisely so the frames stay registered. `crop` takes numbers, and
duplicating trim's content detection here would be the second copy that drifts.

**Choosing the numbers.** Picking a box by eye is a person with an image viewer, or a
`sweep`. This command is told.
