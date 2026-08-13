---
autonomy: auto
ci: wait
lang: en
---

# Model options — requirements

## Purpose

Two image models this project should generate with are absent from the registry: GPT Image 2,
which is the one to reach for by default, and Grok Imagine Image, which is the one to reach
for beside Nano Banana 2. Adding them exposes three gaps. GPT Image 2 takes a size in
explicit pixels, which no model the registry has met could do. All three carry parameters —
how many images a call returns, what quality tier it runs at, what format it hands back —
that reach a model today only through `--opt key=value`, which an agent has to already know
exists. And `num_images` above 1 is worse than undiscoverable: the schema accepts it, the
provider bills for every image, and this project files the first and drops the rest.

## R1 · The models this project generates with

- **R1.1** The registry shall carry `openai/gpt-image-2` as an image model whose role is text-to-image.
- **R1.2** The registry shall carry `openai/gpt-image-2/edit` as an image model whose role is image-to-image and whose input image field is `image_urls`.
- **R1.3** The registry shall carry `xai/grok-imagine-image/v2.0/text-to-image` as an image model whose role is text-to-image.
- **R1.4** The registry shall carry `xai/grok-imagine-image/v2.0/edit` as an image model whose role is image-to-image and whose input image field is `image_urls`.
- **R1.5** The registry shall record `openai/gpt-image-2` as the default model for image and `xai/grok-imagine-video/image-to-video` as the default model for video.
- **R1.6** While neither the workspace configuration nor the asset's kind names a model for a media, the command shall use the registry's default for that media.
- **R1.7** The `ssc model list` command shall report which model is the default for each media.
- **R1.8** The registry shall record both GPT Image 2 endpoints and both Grok Imagine Image endpoints as having no seed.

## R2 · A size in pixels

- **R2.1** The registry shall carry a pixel size shape recording the field it is sent in, the multiple both sides must be, the longest edge, the widest aspect ratio, and the smallest and largest total pixel count the model accepts.
- **R2.2** Where a model's size shape is pixels, the command shall send the size as an explicit width and height.
- **R2.3** The command shall bring a requested size within the model's recorded bounds by scaling it to the pixel and edge limits and rounding each side to the required multiple, keeping the requested aspect ratio as closely as those bounds allow.
- **R2.4** The command shall report both the size that was requested and the size that was sent.
- **R2.5** If a requested size is proportionally wider or taller than the model's widest recorded ratio, then the command shall refuse, naming that ratio.

## R3 · Options with names

- **R3.1** The registry shall carry `count`, `quality` and `format` as core options, each mapped to the field a model spells it with or recorded as absent for that model.
- **R3.2** The generation commands shall accept `--count`, `--quality` and `--format`.
- **R3.3** If a caller names an option the chosen model does not have, then the command shall refuse, naming the model and the option.
- **R3.4** If a caller asks for a count outside what the model offers, then the command shall refuse, naming the range the model accepts.
- **R3.5** When an option is neither named on the command line nor defaulted by the kind, the command shall leave it out of the call, so the model's own default applies.
- **R3.6** The `ssc model show` command shall report, for each core option, the field that model spells it with and the values it accepts.

## R4 · Defaults on a kind

- **R4.1** Where a kind sets default options, the command shall apply them to a call that does not name them.
- **R4.2** If a kind's default names an option the chosen model does not have, then the command shall leave that option out and report it as skipped.
- **R4.3** When an option is named on the command line, the command shall use it in place of the kind's default for that option.
- **R4.4** The `ssc kind show` command shall report the kind's default options.

## R5 · Every image a call produced

- **R5.1** When a finished call carries more than one file, the command shall write every one into the asset as a `source`.
- **R5.2** While a call carries more than one file, the command shall name the stages `<stage>-1` through `<stage>-N`, in the order the provider returned them.
- **R5.3** The command shall cache every file a call produced, so a repeated call writes the same set without paying again.
- **R5.4** The command shall report every file it wrote, each with its stage.

## Out of scope

- **Pricing before the call.** Fal serves a price per endpoint at
  `GET https://api.fal.ai/v1/models/pricing`, which is what would let `budget-guard` refuse
  or ask before spending rather than recording `unpriced` afterwards. It needs its own spec:
  an authenticated call, a cache with a staleness rule, and a unit — `image`, `second`,
  `megapixel` — that differs per model. `--count 4` making a call cost four times as much is
  the reason it is worth doing next.
- **Refreshing `data/models.json`.** `scripts/fetch_model_schemas.py` is named by
  `project.md`, by `specs/model-registry/design.md` and by the wiki, and is not in the
  repository. The four endpoints here are added by hand; restoring that script is separate
  work.
- **Retiring GPT Image 1.5.** It stays in the registry. A model being no longer the one to
  reach for is not the same decision as removing it.
- **A per-image prompt.** One call with `--count 4` sends one prompt. Four prompts are four
  calls.
