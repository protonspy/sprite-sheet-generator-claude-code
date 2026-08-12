---
autonomy: auto
ci: wait
---

# Gen fal — requirements

## Purpose

`gen` is the half of `ssc` that bills. This feature is the four paid commands over Fal AI —
`gen image`, `gen video`, `gen expand`, `gen bgremove` — and the discipline around them: a
job on disk before the money moves, a prompt built from the target asset's kind rather than
from four different commands, a size reconciled against what the model actually offers, and
a collected result filed into the asset as a `source` with the call that produced it
recorded beside it. It is for an agent that must be able to submit, die, and come back for a
result it has already paid for.

`docs/wiki/model-parameters.md` is what these four models accept; `specs/model-registry/` is
the check that runs before submission, and `specs/job-store/` is the record.

## R1 · Paying for something

- **R1.1** The `ssc` CLI shall record a job for a generation call before that call is submitted.
- **R1.2** The `ssc` CLI shall report the job's id, the model that ran and every file it wrote.
- **R1.3** If no Fal credential is available, then the `ssc` CLI shall refuse the call before submitting anything and name what is missing.
- **R1.4** Where the caller asks not to wait, the `ssc` CLI shall report the job it submitted and collect nothing.
- **R1.5** The `ssc` CLI shall file an already-paid result into an asset given that job's id, without submitting anything.
- **R1.6** If the result of an identical call is already cached, then the `ssc` CLI shall write that result and submit nothing.
- **R1.7** The `ssc` CLI shall store a result it collects under the key the call that produced it was submitted with.
- **R1.8** If a result's address is not a public `https` one, then the `ssc` CLI shall fetch nothing from it and shall say what it refused.

## R2 · What is sent

- **R2.1** The `ssc` CLI shall build the prompt it sends from the template the target asset's kind names.
- **R2.2** The `ssc` CLI shall send a local image to the model inline, as a data URL.
- **R2.3** Where the caller asks for it, the `ssc` CLI shall upload a local image to the provider's storage and send that URL instead.
- **R2.4** If an image is too large to send inline and no upload was asked for, then the `ssc` CLI shall refuse and name the option that uploads it.
- **R2.5** The `ssc` CLI shall check every option against the chosen model's schema before submitting.
- **R2.6** Where an image is passed to an image model, the `ssc` CLI shall submit to that model's editing endpoint, and shall refuse when that model has none.
- **R2.7** (ADDED) Where the caller names a prompt template, the `ssc` CLI shall use it instead of the one the asset's kind names.
- **R2.8** (ADDED) The `ssc` CLI shall fill a template's named slots from values the caller supplies, and shall refuse a call whose template names a slot no value was given for.

> **R2.7 and R2.8, added when the character templates arrived.** R2.1 assumed one kind, one
> template, and that holds for every kind that produces one asset. A `character` does not: it
> is generated as a South anchor against a pixel-grid board, corrected to a neutral pose,
> turned into the other directions, then animated — four sets of words about one asset.
> Making each of those a kind would be a kind per *stage*, which is not what a kind is, so
> the override is per call.
>
> R2.8 is what keeps that from becoming a worse prompt. The slots are a closed vocabulary, so
> a typo is refused rather than substituted into nothing, and a template whose slot was never
> filled is refused **before** submission — the failure it prevents is the literal text
> `{name}` reaching the model inside a prompt that is then billed, in an image plausible
> enough that nobody looks. A value the chosen template does not use is not an error: one set
> of values driving several templates is the ordinary way to work.

## R3 · The size a layout needs, against the sizes a model has

- **R3.1** The `ssc` CLI shall express a requested size in the shape the chosen model asks the question in, and shall report the size it chose and how far that is from the size requested.
- **R3.2** If nothing the model offers is within tolerance of the requested size, then the `ssc` CLI shall refuse the call and report what the model does offer.

## R4 · What is written

- **R4.1** The `ssc` CLI shall record every collected file as a `source`, carrying the job, the model and the call that produced it.
- **R4.2** The `ssc` CLI shall store every file of a collected result under a key covering the resolved call, the model id and the images that were sent.
- **R4.3** While `--dry-run` is given, the `ssc` CLI shall report the fully resolved call and shall submit and write nothing.

## Out of scope

**Money, as a number.** No cost is estimated, no total is kept, and nothing is refused for
being expensive — `specs/budget-guard/` owns all three, including the refusal that names a
free command when one produces the same result. What this leaf owes it is a job record with
a `cost_usd` field and the resolved call inside it.

**A second provider.** Fal is the only one, and `job-store`'s `Provider` protocol is the seam
a second would arrive through. Shaping that seam against one provider is guesswork.

**Watching a job.** `ssc job wait|status|resume` already exist; this leaf reuses them rather
than growing a second way to look at a job.
