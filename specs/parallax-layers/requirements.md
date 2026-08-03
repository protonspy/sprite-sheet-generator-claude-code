---
autonomy: auto
ci: wait
---

# Parallax layers — requirements

## Purpose

A background is not one image. It is a stack of them — a far skyline, a middle treeline, a
near foreground — each scrolling at its own rate, which is what makes a flat painting read
as depth when the camera moves. The layers are separate files and stay separate files; what
this feature owns is the *stack*: their order, the rate each one scrolls at, and the checks
that stop an engine from being handed a set it cannot scroll. It is for whoever has three
paintings that belong together, and for an agent that has to hand an engine the numbers.

## R1 · The kind

- **R1.1** The `ssc` CLI shall ship a `background` kind, declaring that its assets are layered.
- **R1.2** Where a project declares a kind of its own, the `ssc` CLI shall let it say whether that kind is layered.

## R2 · The stack

- **R2.1** When `ssc tool layers` runs, the `ssc` CLI shall report the layers in order, each with its file and its scroll factor.
- **R2.2** Where scroll factors are given, the `ssc` CLI shall use them in the order the layers are in.
- **R2.3** Where no scroll factors are given, the `ssc` CLI shall derive one per layer from its position in the stack.
- **R2.4** If a scroll factor is outside zero to one, then the `ssc` CLI shall refuse the stack, because zero is infinitely far away and one moves with the camera.
- **R2.5** If the layers are not all one size, then the `ssc` CLI shall refuse the stack and report the sizes it found.
- **R2.6** If the count of scroll factors given does not match the count of layers, then the `ssc` CLI shall refuse the stack.

## Out of scope

**Separating a flat painting into depth planes.** That is a computer-vision problem, it is
wrong often and confidently, and being wrong produces a background that looks correct until
the camera moves. Layers are an input here, always. Somebody who has one painting and wants
three has an art problem, not a tooling one.

**Scrolling anything.** `ssc` reports the factor; the engine moves the pixels. A preview that
animates the stack belongs with the other previews in `specs/engine-index/`.
