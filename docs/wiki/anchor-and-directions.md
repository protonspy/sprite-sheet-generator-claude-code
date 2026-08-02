# The anchor, and the four directions

The anchor is the single most important image in a character's life. Every later image —
the other three directions, every animation, every derived character — is generated from
it. An error here does not stay put; it propagates into forty frames.

## Face South first

The South-facing (front) view shows the features that identify the character, so it is
what a model can most reliably hold on to when asked for another angle. Generate it at
1024×1024 with a flat chroma background, aiming at a much smaller in-game cell — 256×256
is the common target.

The prompt asks for a strong readable silhouette and dark outline clusters, and against
photorealism. Silhouette is what survives being shrunk to a 48-pixel-wide sprite; detail
is not.

## Neutral pose is the rule that gets learned the hard way

**No fireball in the hand. No drawn weapon. Nothing the character should not be holding
in every animation derived from this image.**

An object present in the anchor becomes attached to the body in every walk cycle, every
idle, every hurt frame generated from it, and removing it afterwards is expensive
hand-work per frame. The attack animation is where the weapon or the spell gets asked
for — by then it is one animation's problem instead of the character's.

## Do not feed the concept art as a reference

Box art or a high-fidelity concept image, passed as a second reference, drags the
generation toward its own fidelity. If the target is a 16-bit look, the concept art
fights it. Keep the concept art for the character-select screen.

The reference that *does* belong there is the checkerboard — see [[reference-boards]].

## The other three directions

With the anchor settled, generate West and North from it: pass the anchor as the first
reference and the checkerboard as the second, and name only the direction in the prompt.

East is usually a horizontal flip of West, which saves a generation entirely. **The flip
is free and the generation is not**, which is why `ssc` treats "mirror" as a command the
expensive path must check for before spending.

It breaks on asymmetry. A book held under one arm, a sheath, a scar, a pauldron on one
shoulder — flipped, they move to the wrong side. The same asymmetry also confuses the
model when it generates the back view, putting the object in the wrong hand. Neither is
detectable by looking quickly, so it is worth checking deliberately.

## Every direction gets snapped

The generated image for each direction is still blurry at the edges, so each one is
snapped and scaled back up before it becomes that direction's working anchor. See
[[pixel-snapping]] for why this happens more than once.
