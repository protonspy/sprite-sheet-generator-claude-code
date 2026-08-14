# Generation style — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R2.1, R2.2, R2.3, R3.1, R3.2, R3.3.

A style is data, a slot, and a field on the profile.

`src/ssc/data/styles.json` is new and ships the five names. Each carries `words` — the
sentence a model is sent — and optionally `board`, the reference board that style needs.
Shipped as data for the reason `templates.json` is: the wording is prose that will be
tuned by whoever reads the results, and prose in a Python literal is prose nobody edits.

`src/ssc/cli/gen.py` gains the reader and the resolver beside `templates()` and
`prompt_for()`, which is where the prompt already lives. Resolution is one function: a name
the package ships resolves to its record, anything else is free text carried verbatim
(R1.3), and blank text is a refusal (R1.4).

`src/ssc/data/templates.json` gains `{style}` where each template currently states how the
art is drawn, and that wording moves into the `pixel-art` style. What stays in a template is
what is true of the output whatever it looks like: the cell, the chroma-green field, the
composition rules, "no text, no watermark". What leaves is "every sprite pixel lands as a
clean block", "16-bit console sprite work", "no anti-aliased edges" — sentences that are
answers to *how is this drawn*, which is now a question somebody else answers. `{style}` is
added to `gen.SLOT` and substituted in the same `re.sub` pass, so a style holding a brace
cannot rewrite a slot filled before it (R2.2).

`src/ssc/cli/kinds.py` gains `Profile.style`, defaulting to `pixel-art` (R3.1, R3.3). It is
an ordinary profile field, so `ssc.yaml` can declare it and `ssc kind show` reports where it
came from without either being taught about styles (R3.2).

`src/ssc/cli/commands/gen.py` gains `--style` on `gen image` only.

**`gen expand` inherits the kind's style, and that is meant.** It carries a prompt and no
`--template`, so it goes through the kind's own template — which now has a `{style}` slot.
Outpainting a hand-painted character in pixel-art words is exactly the seam this axis
exists to close, and the wording it inherits used to be hardwired pixel art, so nothing
changes for a project that declares no style. What it does not get is the flag: the look
of an asset is not a thing to pick again halfway through extending its canvas.

## Boundaries and contracts

The style reaches the model **inside the prompt** and nowhere else: no new field is added to
a call, so no model schema has to accept anything new and `registry.resolve` is untouched.
That also means the cache key separates two styles for free — the prompt is part of the key,
and the same words in two styles are two different prompts, which is what they must be.

`Call.report()` grows a `style` object: the name, whether it is shipped, and the board it
names where it names one (R1.5, R1.6). That is the seam `specs/reference-images/` picks up —
it does not have to re-resolve a style to find out which board to attach.

## Alternatives considered

**A style as a template.** Five names times eight templates is forty templates, and the
combination that nobody wrote is the one somebody wants. Rejected on that alone; the axes
are independent, and `{style}` inside a template is what says so.

**A style as a model option.** The look would then be a field per provider, and every model
whose schema has no such field could not be asked for one. Prose in a prompt is the only
surface every model has.

**Refusing a `--style` no one ships.** Rejected: free text is the escape hatch that keeps
the shipped set a starting point rather than a closed enum, which is the same argument
`adr:0008-a-kind-is-a-profile-not-an-enum` already made for kinds. The cost is a typo
becoming a style — mitigated by R1.5, which reports whether what was applied is a name the
package knows, so a caller who meant `pixel-art` and typed `pixelart` can see it.

## Risks

**A style is the first free text a `ssc.yaml` can put into a paid prompt.** Every other
prompt-shaping field a config may set is closed — `template` must name one this package
ships, `checks` and `options` are typed — and a workspace config arrives with a cloned
repository as often as it is written by whoever runs the command. Free text stays, because
a project whose look is "woodcut print" is exactly what R3.2 is for; what it gets is a
ceiling (`gen.MAX_STYLE`, R1.7), so the worst case is a phrase rather than a paragraph
prepended to every call the kind ever makes. `--style` is held to the same bound, from the
same function, for the reason `style_for` is one function at all.

**A template that keeps a stylistic sentence nobody noticed.** The wording is prose across
eleven templates, and the failure is silent: a `vector` generation still asking for hard
pixel edges comes back looking almost right. The task list handles it by asserting the
absence — a template must not name pixel art unless a style put it there — rather than by
asserting the presence of the new slot.
