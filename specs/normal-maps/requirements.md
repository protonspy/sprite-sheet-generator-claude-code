---
autonomy: auto
ci: wait
---

# Normal maps — requirements

## Purpose

A 2D engine can light a sprite if it is told which way each pixel's surface faces. That
information does not exist in the art, so it is inferred: brighter pixels read as raised,
darker as recessed, and the slope between them becomes a surface normal. The result is a
second image the engine samples alongside the first. This is for whoever wants a torch to
move across a wall the way it would in three dimensions, and it is deliberately an
inference — the art never carried a height field, and no amount of processing invents one
that is true.

## R1 · The map

- **R1.1** When `ssc tool normal` runs, the `ssc` CLI shall write an image the same size as its input, encoding one surface normal per pixel as a colour.
- **R1.2** The `ssc` CLI shall derive the height it reads slopes from out of the input's luminance.
- **R1.3** Where `--strength` is given, the `ssc` CLI shall scale the slope by it, and shall refuse a value outside its range.
- **R1.4** Where a pixel is transparent, the `ssc` CLI shall encode a flat normal there and shall not let it pull the slope of its opaque neighbours.
- **R1.5** Where `--in` names a set, the `ssc` CLI shall write one map per frame.
- **R1.6** The `ssc` CLI shall encode every normal as a unit vector.

## R2 · The convention

- **R2.1** The `ssc` CLI shall report which convention it encoded, because an engine that assumes the other one lights every surface backwards.
- **R2.2** Where `--flip-y` is given, the `ssc` CLI shall encode the other convention.

## Out of scope

**Inferring depth.** Luminance is not height, and a lit sprite whose art already contains
painted shadows will read those shadows as geometry. That is the known cost of the
inference, not a bug to be fixed by a better filter — the honest fix is an artist-authored
height map, which is an input this tool does not have.

**A specular or roughness map.** Same argument, less payoff.
