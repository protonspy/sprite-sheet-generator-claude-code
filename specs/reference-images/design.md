# Reference images — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R1.5, R2.1, R2.2, R2.3, R2.4, R3.1, R3.2, R3.3, R4.1.

`Ask.image` and `Call.image` become sequences, and everything downstream of them follows:
`build` puts one placeholder per reference where the model's field is an array,
`Call.inputs` carries every digest so the cache key separates two calls that differ only in
their second image (R1.4), `recorded[image_field]` carries one elided record each (R1.5),
and `gen.run` makes one provider reference per image before submitting.

A reference is no longer a bare `Image`. `gen.Reference` pairs the image with the role the
caller gave it, and `--ref path:identity` is parsed on the command surface — one argument
rather than two parallel repeatable options, because `--ref a.png --ref b.png --role
identity --role palette` is two lists a caller can get out of step.

The role wording lives in `src/ssc/data/templates.json` under a new `roles` key, beside the
templates, because it is the same kind of thing: prose sent to a model, tuned by whoever
reads the results. `prompt_for` appends one sentence naming the images in order where any
of them carries a role.

**The anchor template gives up its blanket sentence.** It says *any image supplied alongside
this prompt is a pixel-grid reference: take block discipline from it and never take its
content*, which was true when a call carried one image and is wrong the moment it carries
two — the anchor a direction is drawn from is exactly the image whose content must be
taken. That lesson is not lost: it moves to the `board` role, so it travels with the image
it is about rather than with the template.

`--board` on `gen image` generates the board the resolved style names — `pixel-art` names
`checker` — through the same `core/board.py` that `tool board checker` uses, at the size the
call asks for, and sends it last (R3.3). Generated rather than required as a path because
the alternative is every caller running `tool board checker` first and passing a file whose
square size nobody chose deliberately; [[reference-boards]] is explicit that the square size
is a parameter that should track the project rather than a frozen asset.

`gen video` gains none of this: no repeatable reference, no `--board`. A video model given a
grid paints the grid onto the character, and the wiki's argument for two commands rather
than one with a flag is that a mistake which cannot be expressed cannot be made under time
pressure (R4.1).

## Boundaries and contracts

The provider surface is unchanged: `fal.reference` still takes one image's bytes, and the
call now makes N of those where it made one. `Call.arguments` already put a list in the
image field where the model's schema declares an array — this fills that list with more
than one element for the first time, which is why R1.3 refuses rather than truncating: a
model whose field is a plain string can hold exactly one URL, and quietly dropping the
second is a paid call missing half of what it was asked to work from.

`specs/gen-fal/R2.2` is folded to the plural in the same branch. Nothing else there
changes: its editing-endpoint rule still routes an image call to `/edit`, and its cache-key
requirement already said *the images that were sent*.

## Alternatives considered

**Auto-attaching the style's board whenever the style names one.** Rejected. `pixel-art` is
the default style for every kind, so this would put a board on every image call in every
existing workspace, and — through R1.3 — turn a working single-image model into a refusal.
A board is right for an anchor and wrong for a direction being drawn from one, which is a
per-call judgement, so it is a per-call flag.

**A role per model field.** Some providers are beginning to name their reference slots.
Nothing in this registry does, and mapping a role onto a field that does not exist would be
a table that lies. The role reaches the model as words, which is the one surface every model
has — the same argument `specs/generation-style/` made for the style itself.

## Ceilings

Repetition is the new thing here, so every bound this path had for one image has to hold
for N. `references_for` refuses past `gen.MAX_REFERENCES` **before the first read**, because
by the time the pipeline sees the list they are all resident; `build` checks the finished
list too, since `--board` adds an image the caller did not name. `image_at` refuses a file
past `frames.MAX_FILE_BYTES` from its header rather than after reading it, and `image_in`
passes the same ceiling into the bound `Directory.read` the way every other reader of one
does. The generated board is held to `MAX_BOARD_SIDE` — `tool board checker`'s own bound,
imported rather than restated, because `build` runs before the dry-run report, before the
cache and before the budget, and an unbounded side there is an allocation large enough to
end the process without a call being made.

## Risks

**Two references to a model that reads them positionally.** Nothing in a schema says which
image is which, so the ordering rule (R1.2) and the sentence naming them (R2.1) are the only
things keeping an anchor from being read as a board. Both are asserted; neither can be
verified without paying, which is why the order is defined as *the order given* rather than
as something `ssc` decides on the caller's behalf.
