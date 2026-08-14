# Box art, and the style a generation asks for

Two decisions sit in front of the first paid call of a character: what the character *is*,
and how it is *drawn*. They are separate, they are decided in that order, and until this
page's work landed `ssc` conflated them — every prompt template named pixel art, so the
only way to answer the second question was to not ask it.

## Box art answers the first question

Box art is the concept piece: the character at full fidelity, no cell, no chroma key
discipline, nothing that serves a sprite pipeline. It exists so a person can look at one
image and say *yes, that is the wizard* before any money is spent deriving four directions
and five animations from a silhouette nobody signed off on.

It is generated **only when there is no reference image**. A caller who already has art —
a commission, an earlier character in the same set, a sketch — has already answered the
question box art asks, and generating one anyway is a paid call that buys nothing.

The pixel art comes afterwards and comes from it, through `tool pixelart` (see
[[pixel-snapping]] for why that is not the same as recovering a grid). Box art is not a
draft of the sprite; it is the brief the sprite is drawn to.

A game can show it. Character-select screens want exactly this image, which is a second
reason it is worth its own stage rather than being a throwaway.

## Do not pass box art as a reference to the anchor

This is the trap, and it is counter-intuitive enough to be worth stating plainly: box art
makes a *worse* anchor image when it is passed as a reference.

The model honours it. That is the problem — the anchor comes back at the box art's
fidelity, richly shaded and finely detailed, when what a 16-bit sprite needs is the
opposite. The detail cannot survive the trip down to a 256-pixel cell, so it arrives as
noise that [[frame-normalisation]] then has to fight.

What the anchor takes instead is the checkerboard from [[reference-boards]], whose whole
job is to impose block discipline. Box art informs the *prompt* — the words describing the
character — and stays out of the payload.

**This is enforced now.** `ssc gen boxart` records what it produced, and `gen image`
refuses a `--from-stage` naming it, pointing at `tool pixelart` instead. The check reads
the provenance rather than the stage name, so renaming the stage does not get past it.
What it cannot see is a copy: bytes lifted out of the asset and passed with `--ref` carry
nothing that says where they came from. That is the honest limit of enforcing this at the
command surface, and the path it does close is the one an agent takes.

## Style answers the second question

A style is what the generation is asked to look like: a name this package ships, or free
text handed to the model unchanged. The shipped names are a starting set, not a closed
one, and the point of the axis is that `pixel-art` is now a choice rather than an
assumption baked into every template.

Two things make a style more than a string:

- **A style may carry an attachment.** `pixel-art` is words *plus* the checkerboard,
  because the words alone do not produce block discipline — that is the finding
  [[reference-boards]] records, and it is the reason a style is resolved rather than
  interpolated.
- **A style is a project decision before it is a call decision.** The kind profile carries
  the default, so two assets generated a week apart do not drift apart. This is the same
  argument [[prompt-templates]] makes for templates and the palette makes for colour: a
  parameter that is only ever an argument is a parameter nobody decided.

The harness picks it per call, and the default when nobody picks is `pixel-art` — which
keeps every existing workspace generating exactly what it generated before.

## Where the two meet

Box art is generated in whatever style reads as concept art, never in the asset's style,
even when the asset's style is `pixel-art`. That is not a special case bolted on; it falls
straight out of what the two decisions are for. The look of the deliverable is not the look
of the brief.
