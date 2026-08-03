# Fixtures

These files have **measured** defects. `doctor` and every detector are validated against
these exact numbers, so a fixture is never regenerated or "fixed" — a new case gets a new
file.

## `fake-pixels-8x8-at-12x.png`

Fake pixel art: an 8×8 RGBA sprite upscaled to 96×96 with **bicubic** resampling, so every
block edge is a soft ramp rather than a step. This is the defect an image model produces
and the one `snap` exists to remove.

The source sprite, five flat colours over transparency:

```
· · K K K K · ·      K = (26, 20, 35)      outline
· K S S S S K ·      S = (222, 158, 120)   skin
· K S K S K S ·      C = (60, 120, 200)    tunic
· K S S S S S ·      B = (200, 60, 70)     belt
· C C B B C C ·      · = transparent
· C C C C C C ·
· · C · · C · ·
· · K · · K · ·
```

Measured against `vendor/pixel-snapper.wasm`: the auto-detected pixel size is 11.0 and the
output is 10×10, not the 8×8 it was drawn at — bicubic ramps widen the apparent grid, and
that gap is the point of the fixture. With `--pixel-size 12` the output is 9×9. Both
numbers were checked to be byte-identical to upstream's native CLI on the same input.
