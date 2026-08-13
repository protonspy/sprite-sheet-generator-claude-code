---
autonomy: auto
ci: wait
---

# Model pricing — requirements

## Purpose

Choosing a model is choosing what a run costs, and `ssc` cannot say what anything costs
until the bill arrives: `budget.py` records the amount a provider returns *after* a call.
An agent picking between three image-to-video models has nothing to pick on. Fal publishes
a price for every endpoint, but not in the OpenAPI document `models.json` is regenerated
from — it is in the model listing, as a sentence of Markdown written per model. So this
leaf pulls that sentence into the catalogue and shows it, and adds the three video models
that are missing from it.

A price nobody reads changes nothing, and the agent driving a workspace reads the shipped
instruction file and the `sprite-*` skills, not this spec. So the same leaf puts the
choice into those texts: which model a step reaches for, and what to set when the work is
one icon rather than a forty-frame sheet.

It also writes `scripts/fetch_model_schemas.py`, which `CLAUDE.md` and `core.json` both
name as the thing that regenerates `models.json` and which is not in the repository.

## R1 · The catalogue

- **R1.1** The `ssc` CLI shall carry `xai/grok-imagine-video/v1.5/image-to-video`,
  `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` and
  `bytedance/seedance-2.5/image-to-video` in its model registry, each with the media
  `video`.
- **R1.2** The `ssc` CLI shall keep `openai/gpt-image-2` as the default for `image` and
  `xai/grok-imagine-video/image-to-video` as the default for `video`.
- **R1.3** The `ssc` CLI shall map every core concept for each added model onto that
  model's own field, or onto `null` where the model has no such concept.

## R2 · The price

- **R2.1** The `ssc` CLI shall carry, for each model in the registry, the price text the
  provider published for it and the date that text was fetched.
- **R2.2** When `ssc model show` runs, the `ssc` CLI shall report that price text and its
  fetch date.
- **R2.3** When `ssc model list` runs, the `ssc` CLI shall report for each model whether a
  price is known.
- **R2.4** The `ssc` CLI shall report the price as the provider's own text and shall not
  derive a number from it.
- **R2.5** Where a model has no published price, the `ssc` CLI shall report the price as
  `null` rather than omitting the field.
- **R2.6** If a caller reads the price expecting an amount, then the `ssc` CLI shall carry
  alongside it the statement that it is indicative and that `ssc budget` is what a run
  actually cost.

## R3 · The refresh

- **R3.1** The repository shall carry a script that regenerates `models.json` from the
  providers' published documents.
- **R3.2** When that script runs, the refresh script shall write each model's input schema
  from the endpoint's OpenAPI document and its price text from the provider's model
  listing.
- **R3.3** When that script runs, the refresh script shall stamp each price with the date
  it was fetched.
- **R3.4** If an endpoint's document cannot be fetched, then the script shall leave that
  model's existing entry untouched and report it.
- **R3.5** The script shall reach the provider without credentials.

## R4 · Choosing, in the shipped text

- **R4.1** The root instruction file shipped for each agent shall name the model the CLI
  reaches for by default for each media, and shall name `ssc model list` and `ssc model
  show` as how to see the rest and their prices.
- **R4.2** The root instruction file shall state which options move what a call costs, so a
  model and its options are chosen against the work rather than against a habit.
- **R4.3** The shipped `sprite-*` skills shall each name, for their generating steps, the
  model and the options that step reaches for.
- **R4.4** Where a step's cost scales with the work, the skill shall name what to set at
  the cheap end and at the expensive end, and which property of the work decides.
- **R4.5** If a shipped text names a model, then the named endpoint shall be one the
  registry carries.

## Out of scope

- **Computing what a call will cost.** The published price is one sentence per model in
  five different billing shapes — per image, per token, per second by resolution, with
  multipliers. Turning that into an estimate means a parser that is wrong silently, and a
  wrong price is only discovered on the invoice. `ssc budget` already records the real
  amount per call, which is the number that is true.
- **A price for anything but a model.** Storage, egress and the pixel-snapper are not
  priced here.
- **Refreshing on its own.** The catalogue is refreshed by running the script and
  committing the result, never by a command reaching the network mid-run.
