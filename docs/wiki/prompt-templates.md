# Prompt templates

`gen image` and `gen video` never send a caller's words straight to a model. The words go
into a **template** — a fixed frame carrying everything that must be true of the output
regardless of what is being drawn — and the template is chosen by the asset's kind, or named
directly when one kind has more than one job.

The templates themselves are `src/ssc/data/templates.json`. This page is why they say what
they say.

## One kind is not one template

A `tile` is generated once. A `character` is generated four different ways over its life:
the South anchor against a checkerboard, a correction pass when that anchor came back
holding something, the other directions from the approved anchor, then the animation. Each
of those is a different set of instructions about the same asset.

Making each a kind would be a kind per *stage*, and a kind describes an asset — its cell,
its anchor mode, whether it animates. So the template can be named per call instead, and the
character templates are `anchor`, `neutral-pose`, `direction`, `walk`.

## Named slots, and why the vocabulary is closed

A template may carry slots — `{name}`, `{archetype}`, `{costume}`, `{prop}`,
`{silhouette}`, `{setting}`, `{direction}`, `{remove}` — filled with `--var name=Kael`.
There are eight and there will not be an arbitrary number: an open set becomes a second
prompt language nobody documents, and the things worth being structured about are the ones
that recur across the character templates. Everything else is prose, and prose goes in
`--prompt`.

Two rules follow, and they are deliberately asymmetric:

- **A slot the template names and nobody filled is a refusal, before submission.** The
  alternative is the literal text `{name}` travelling to the model inside a prompt that is
  then billed, in an image plausible enough that nobody looks.
- **A value the template does not use is fine.** One set of values driving several templates
  — the same character as an anchor, then a direction, then box art — is the ordinary way to
  work, and refusing the spares would punish it for nothing.

The check runs against the *template*, before the caller's text is substituted, and
`{prompt}` goes in last. Somebody writing `a knight {holding a torch}` is describing a
knight; a check against the finished string would refuse them for punctuation.

## What every sprite template asks for, and the one that does not

Every template that produces a sprite asks for a flat `#00b140` chroma-green field, because
generating on a background `tool bgremove` cannot key is how a paid image becomes unusable.
Magenta is the other preset and is the better key for a character carrying a lot of green,
but it has to be asked for on both sides — the prompt and `bgremove --chroma magenta`.

`box-art` is the exception, and it is the point of that template rather than an oversight.
Box art is the roster and character-select illustration: it keeps its own setting, because
it is never cut out. See [[anchor-and-directions]] for the rule that it must not then be fed
back as a sprite reference — that is the caller's to honour, and nothing enforces it.

## The base animation template, and the walk

`video` carries what is true of any in-place animation: hold the orientation the input
already has, keep the camera and framing fixed, loop back to the first frame, and — the
failure worth naming — **do not let the flat background become a floor, a room, a horizon,
a perspective grid or a shadow plane.** A model asked to animate a sprite will invent a
scene for it to stand in unless told not to.

`walk` is that base plus the motion of a walk cycle: alternating leg steps, subtle vertical
bobbing, minimal arm swing, both feet staying visible. The two overlap heavily on purpose.
Folding them into one would tell an idle animation to alternate its legs, and
[[generating-animations]] is why video generation exists here at all — image generation
cannot produce a walk cycle, and video is the base every other animation will be built on.
