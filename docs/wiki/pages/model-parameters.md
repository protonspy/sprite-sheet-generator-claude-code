# What the models actually accept

Eight endpoints carry the generation path: GPT Image 2, Nano Banana 2 and Grok Imagine Image
for images — each with an `/edit` twin — plus Grok Imagine Video for motion and BiRefNet for
hosted background removal. What each one accepts is not a detail: it decides what `ssc gen
image` can ask for, and it is the reason [[reference-boards]] computes a layout instead of
trusting a `--size` somebody typed.

## The schemas are published, not transcribed

Fal serves an OpenAPI document per endpoint, unauthenticated:

```
https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=<endpoint id>
```

It carries the input schema with every field, its type, its default and its enum. So the
registry reads the provider at runtime and keeps a copy in the package only as an offline
fallback — a hand-transcribed table would be wrong the week after Fal changes a model, and
wrong quietly.

| Model | Endpoint id | Default for |
|---|---|---|
| GPT Image 2 | `openai/gpt-image-2`, `openai/gpt-image-2/edit` | image |
| Nano Banana 2 | `fal-ai/nano-banana-2`, `fal-ai/nano-banana-2/edit` | |
| Grok Imagine Image | `xai/grok-imagine-image/v2.0/text-to-image`, `…/edit` | |
| GPT Image 1.5 | `fal-ai/gpt-image-1.5`, `fal-ai/gpt-image-1.5/edit` | |
| Grok Imagine Video | `xai/grok-imagine-video/image-to-video` | video |
| BiRefNet | `fal-ai/birefnet/v2` | |

The default is in the package, in `core.json`, and is not written into a workspace's
`ssc.yaml` — one fact in two places drifts, and the copy in every workspace ever created is
the one that goes stale. `models.image` in `ssc.yaml` and a kind's `image_model` both override
it, and `ssc model list` says which is in force.

Passing a reference image is a **different endpoint**, not a parameter: `/edit` on every image
model. A command that only knew the base endpoint could not pass the anchor image at all.
`openai/gpt-image-2/edit` also takes `mask_url`, which is inpainting — no flag of its own, but
`ssc model show` reports it and `--opt mask_url=…` reaches it.

## One model takes a size in pixels; the rest do not

This is the finding that shaped `--size`, and it is worse than "models offer a set of sizes":

| Model | How you ask | What you may ask for |
|---|---|---|
| GPT Image 2 | `image_size` | explicit `{width, height}`, or seven presets |
| GPT Image 1.5 | `image_size` | exactly `1024x1024`, `1536x1024`, `1024x1536` |
| Nano Banana 2 | `aspect_ratio` + `resolution` | any ratio, at `0.5K` · `1K` · `2K` · `4K` |
| Grok Imagine Image | `aspect_ratio` + `resolution` | 13 ratios, at `1k` · `2k` |
| Grok Imagine Video | `aspect_ratio` + `resolution` | any ratio, at `480p` · `720p` |

So a pose board of six cells in a row — 6:1 — is not merely unusual on GPT Image 1.5, it is
**unrepresentable**: the widest shape it offers is 3:2. On GPT Image 2 the same board is
refused too, but by a number rather than an enumeration: 3:1 is the widest it takes. The
honest answers are to lay the board out 3×2 or to generate the cells one at a time, and an
agent can only choose between those with the numbers in front of it. That is the argument for
`tool board` computing the layout and `gen image` reconciling it against the schema, rather
than a prompt asking politely for a wide image.

Note the spelling: Nano Banana 2 says `1K` and Grok Imagine Image says `1k` for the same idea.
Nothing here normalises that — the tier comes from the model's own enum.

**GPT Image 2's real pixel limits are in prose, not in the schema.** Both sides a multiple of
16, longest edge 3840, ratio at most 3:1, total pixels between 655,360 and 8,294,400 — stated
in the field's description, while the machine-readable part says only `maximum: 14142` per
side. They are transcribed into `core.json`, and
`adr:0013-pixel-bounds-are-transcribed-from-the-description` records why that departure was
worth making.

## The normalised core, and the three added to it

Five concepts were meant to be stable across models — prompt, input image, seconds, size,
seed. Measured against these eight endpoints:

- **`prompt`** holds everywhere except BiRefNet, which takes an image and gives one back.
- **input image** holds, but as `image_urls` (a list) on every `/edit` endpoint and
  `image_url` (one) on the video model and BiRefNet.
- **`seed`** exists on Nano Banana 2 and **on nothing else.** A normalised `--seed` cannot be
  assumed to reach the model; reproducibility is a per-model property.
- **seconds** is `duration` on Grok Imagine Video, a number defaulting to 6 with no enumerated
  set — so the "1 second loops better" setting is expressible, and there is nothing in the
  schema to stop a caller asking for a length that loops badly. See [[generating-animations]].

Three more earned a name, for a reason that is not symmetry: an agent cannot use an option it
has to already know exists, and these are the three it needs at the right moment.

| Concept | Flag | Spelled | Where it exists |
|---|---|---|---|
| count | `--count` | `num_images` | every image model, 1 to 4 |
| quality | `--quality` | `quality` | GPT Image 2 and 1.5 (`auto`…`high`), Grok Imagine Image (`low`, `medium`) |
| format | `--format` | `output_format` | every image model, and BiRefNet |

**`--count` multiplies what a call costs.** Four images is four times the money; every one is
written into the asset as its own `source` under `<stage>-1 … <stage>-N`, and the whole set is
cached behind the one call key. Before this existed the extra images were billed and thrown
away.

A kind may default `count`, `quality` and `format` under `kinds.<name>.options` — never the
prompt, the input image or the size, each of which is per call by construction. A default the
chosen model does not have is skipped and named in the result, where a *named* option the model
does not have is a refusal: asking for something and not getting it has to be visible, while a
policy that has to work at two models does not.

## Two things worth knowing before designing around them

**GPT Image 1.5 and GPT Image 2 can return alpha directly.** `background` takes `transparent`,
which means the chroma-key path is not the only way to get a cut-out from those models. It does
not replace `bgremove` — nothing says the alpha is clean at the edges, and
[[game-ready-defects]] is specific about halo — but it is a measurement worth making before
paying for a second call.

**BiRefNet is six models behind one endpoint.** `model` selects between General Use (Light /
Light 2K / Heavy / Dynamic), Matting and Portrait, and `operating_resolution` goes to
2304×2304. Quality here is a parameter, not a fixed property of the endpoint, so "remove the
background with BiRefNet" is under-specified as an instruction.
