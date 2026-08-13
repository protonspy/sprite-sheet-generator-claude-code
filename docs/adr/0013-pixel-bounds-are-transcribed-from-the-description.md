---
status: accepted
---

# 0013 · Pixel bounds are transcribed from the description

## Context

`model-registry` rests on one rule: schemas are read from the provider, never transcribed
into this repository. A hand-written table of what a model accepts is wrong the week after
the provider changes it, and wrong quietly — the copy keeps answering, confidently, with
last release's truth. `data/models.json` exists only as an offline fallback, and
`data/core.json` holds the little that a schema cannot say: which field is this project's
`--seed`, and what shape a model asks the size question in.

GPT Image 2 broke the assumption under that rule. It is the first model in the registry that
takes a size in explicit pixels — `image_size: {width, height}` — and its real constraints
are stated **only in the field's description**:

> Concrete sizes must have both dimensions as multiples of 16, max edge 3840px, aspect ratio
> <= 3:1, total pixels between 655,360 and 8,294,400.

The machine-readable part of the same schema says `maximum: 14142` per side and nothing else.
So `3841x512` satisfies every constraint a program can read out of the document, and the
model rejects it. There is no third option where the numbers come from somewhere both
authoritative and parseable: prose is where the provider put them.

## Decision

Record the five numbers in `data/core.json`, beside the size shape they qualify:

```json
"size": {
  "kind": "pixels", "field": "image_size", "multiple": 16, "max_edge": 3840,
  "max_ratio": 3.0, "min_pixels": 655360, "max_pixels": 8294400
}
```

`core.json` and not `models.json`: that file is regenerated from the provider's document and
anything hand-written in it is destroyed by the next refresh. `core.json` is hand-authored by
design and already carries the shape.

`reconcile_size` reads them and fits the request — scaling, rounding to the multiple, and
refusing a ratio past the limit. A caller never types a preset.

## Consequences

**These five numbers go stale silently.** That is the cost, it is the thing
`model-registry` exists to avoid, and no test catches it: the suite pins that they are still
absent from the machine-readable schema, which is evidence the transcription is still needed
rather than evidence it is still correct.

What makes it the lesser evil is where each failure lands. A stale bound here produces a
refusal, or an image at a size slightly different from the one asked for — visible, local,
and free. Not transcribing means building a call from the loose bounds, submitting it, being
billed, and getting a rejection back from the model. One of those is a message; the other is
money.

**The escape is defined.** The moment Fal states these in the schema itself,
`test_gpt_image_2_takes_a_size_in_pixels` should start failing, and the right response is to
delete the numbers from `core.json` and read them from the document — not to update them.

**It does not generalise.** `pixels` is a size shape like `enum` and `ratio`, so a second
model that takes pixels costs one entry. But nothing here licenses transcribing anything
else: a value that is in the schema is read from the schema, and this record covers the one
case where it is not there to read.
