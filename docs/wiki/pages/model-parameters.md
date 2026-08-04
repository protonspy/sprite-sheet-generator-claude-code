# What the models actually accept

Four models carry the generation path: Nano Banana 2 and GPT Image 1.5 for images, Grok
Imagine Video for motion, BiRefNet for hosted background removal. What each one accepts is
not a detail — it decides what `ssc gen image` can ask for, and it is the reason
[[reference-boards]] computes a layout instead of trusting a `--size` somebody typed.

## The schemas are published, not transcribed

Fal serves an OpenAPI document per endpoint, unauthenticated:

```
https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint id>
```

It carries the input schema with every field, its type, its default and its enum. So the
registry reads the provider at runtime and keeps a copy in the package only as an offline
fallback — a hand-transcribed table would be wrong the week after Fal changes a model, and
wrong quietly. `scripts/fetch_model_schemas.py` refreshes the shipped copy from that URL
and `--check` reports drift.

| Model | Endpoint id |
|---|---|
| Nano Banana 2 | `fal-ai/nano-banana-2`, `fal-ai/nano-banana-2/edit` |
| GPT Image 1.5 | `fal-ai/gpt-image-1.5`, `fal-ai/gpt-image-1.5/edit` |
| Grok Imagine Video | `xai/grok-imagine-video/image-to-video` |
| BiRefNet | `fal-ai/birefnet/v2` |

Passing a reference image is a **different endpoint**, not a parameter: `/edit` on both
image models. A command that only knew the base endpoint could not pass the anchor image
at all.

## Nobody takes a size in pixels

This is the finding that matters most, and it is worse than "models offer a set of sizes".
The three image paths answer the size question in three incompatible shapes:

| Model | How you ask | What you may ask for |
|---|---|---|
| GPT Image 1.5 | `image_size` | exactly `1024x1024`, `1536x1024`, `1024x1536` |
| Nano Banana 2 | `aspect_ratio` + `resolution` | any ratio, at `0.5K` · `1K` · `2K` · `4K` |
| Grok Imagine Video | `aspect_ratio` + `resolution` | any ratio, at `480p` · `720p` |

So a pose board of six cells in a row — 6:1 — is not merely unusual on GPT Image 1.5, it
is **unrepresentable**: the widest shape it offers is 3:2. The honest answers are to lay
the board out 3×2 or to generate the cells one at a time, and an agent can only choose
between those with both numbers in front of it. That is the whole argument for `tool board`
computing the layout and `gen image` reconciling it against the schema, rather than a
prompt asking politely for a wide image.

## The normalised core is smaller than it looks

A handful of concepts were meant to be stable across models — prompt, input image,
seconds, size, seed. Measured against these four:

- **`prompt`** holds everywhere.
- **input image** holds, but as `image_urls` (a list) on both image models and `image_url`
  (one) on the video model, and only on the `/edit` endpoints.
- **`seed`** exists on Nano Banana 2 and **does not exist on GPT Image 1.5.** A normalised
  `--seed` cannot be assumed to reach the model; reproducibility is a per-model property.
- **seconds** is `duration` on Grok Imagine Video, a number defaulting to 6 with no
  enumerated set — so the "1 second loops better" setting is expressible, and there is
  nothing in the schema to stop a caller asking for a length that loops badly. See
  [[generating-animations]].

Which is why the mapping from a core flag to a model's spelling lives in the registry
beside the schema rather than in code, and why a concept that does not map is recorded as
absent instead of silently dropped.

## Two things worth knowing before designing around them

**GPT Image 1.5 can return alpha directly.** Its `background` field takes `transparent`,
which means the chroma-key path is not the only way to get a cut-out from that model. It
does not replace `bgremove` — nothing says the alpha is clean at the edges, and
[[game-ready-defects]] is specific about halo — but it is a measurement worth making
before paying for a second call.

**BiRefNet is six models behind one endpoint.** `model` selects between General Use
(Light / Light 2K / Heavy / Dynamic), Matting and Portrait, and `operating_resolution`
goes to 2304×2304. Quality here is a parameter, not a fixed property of the endpoint, so
"remove the background with BiRefNet" is under-specified as an instruction.
