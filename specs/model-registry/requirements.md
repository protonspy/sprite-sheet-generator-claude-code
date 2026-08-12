---
autonomy: auto
ci: wait
---

# Model registry — requirements

## Purpose

An unknown option passed to a provider is a money leak, not an error: type `--opt
guidance_scale=7` at a model whose field is `cfg` and the call succeeds, the parameter is
dropped, the job is billed, and the image that comes back is plausible enough that nobody
notices it ignored you. This feature is what stands between a caller and that — the options
each model actually accepts, read from the provider rather than transcribed, and a check that
runs **before** anything is submitted. It is for an agent choosing parameters whose effect it
cannot see, and for whoever has to explain the bill.

`docs/wiki/model-parameters.md` records what these schemas actually say, including the four
incompatible ways the models ask about size — one of which is explicit pixels, whose real
bounds the schema states only in prose (`specs/model-options/` R2.1).

## R1 · Reading what a model accepts

- **R1.1** The `ssc` CLI shall list every model it knows, with its id, its media and the provider endpoint behind it.
- **R1.2** Where a media is named, the `ssc` CLI shall list only the models for that media.
- **R1.3** The `ssc` CLI shall report, for one model, every option that model accepts with its type, its default, and the values it allows where the schema names them.
- **R1.4** The `ssc` CLI shall read a model's schema from the provider, and shall fall back to the copy shipped with the package when it cannot.
- **R1.5** The `ssc` CLI shall report which of those two a reported schema came from.
- **R1.6** If a name matches no model, then the `ssc` CLI shall exit `2` and name the models it has.

## R2 · Checking a call before it is paid for

- **R2.1** If a call names an option the model's schema does not declare, then the `ssc` CLI shall refuse the call and name the options that model does accept.
- **R2.2** If an option's value is outside what the schema allows for it, then the `ssc` CLI shall refuse the call and report what the schema allows.
- **R2.3** The `ssc` CLI shall accept a small set of options under one name across models, and shall translate each into that model's own spelling as the registry records it.
- **R2.4** If one of those options names a concept the model does not have, then the `ssc` CLI shall refuse the call rather than dropping the option.

## R3 · Which model runs

- **R3.1** The `ssc` CLI shall take the model for each media from `ssc.yaml`.
- **R3.2** Where the kind of the asset being generated names a model for that media, the `ssc` CLI shall use that instead.
- **R3.3** If a configured model is not one it knows, then the `ssc` CLI shall exit `1` and name that model.

## Out of scope

**Submitting anything, and pricing.** No call is made here and no cost estimated — this leaf
decides whether a call is *well formed*. `specs/gen-fal/` submits, `specs/budget-guard/`
counts.

**Choosing a size.** Reconciling what a layout needs against what a model offers is
`gen-fal`'s, and it is genuinely hard: `docs/wiki/model-parameters.md` shows a 6:1 board is
not merely unusual on GPT Image 1.5 but unrepresentable. What this leaf owes that work is the
schema to reconcile against, in a shape it can read.
