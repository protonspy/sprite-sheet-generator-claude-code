---
autonomy: auto
ci: wait
---

# Sweep and review — requirements

## Purpose

`ssc tool sweep` runs one free command across a range of its own parameters, measures every
result with `doctor`, and leaves the whole comparison in one directory for a person to look
at. It is for the question no measurement answers on its own — *which tolerance, which
colour budget, which dither* — where the honest method is to produce the candidates and put
them side by side. It decides nothing: the decision is `specs/gates-and-resume/`'s.

## R1 · What a sweep runs

- **R1.1** The `ssc` CLI shall run one named command once per point in the declared parameter range, over the same input, writing each result as its own variant.
- **R1.2** Where more than one parameter is declared, the `ssc` CLI shall run every combination of their values.
- **R1.3** The `ssc` CLI shall accept a parameter range written as an explicit list of values, and as `first..last:step`.
- **R1.4** If the declared range would produce more variants than the ceiling, then the `ssc` CLI shall refuse before running anything, reporting the number it would have produced.
- **R1.5** If the named command is not one the sweep can run, then the `ssc` CLI shall refuse, naming the commands it can run.
- **R1.6** If a declared parameter is not one the named command accepts, then the `ssc` CLI shall refuse, naming the parameters that command accepts.
- **R1.7** If a declared value is outside what the named command accepts for that parameter, then the `ssc` CLI shall refuse before running anything, naming the value and the bound it broke.

## R2 · What a sweep measures

- **R2.1** The `ssc` CLI shall run `doctor` over each variant and record that variant's report with it.
- **R2.2** The `ssc` CLI shall report each variant's parameter values, output path, defect count and warning count.
- **R2.3** The `ssc` CLI shall report which variant had the fewest defects, as a measurement and not as a decision.
- **R2.4** If one variant's command fails, then the `ssc` CLI shall record that variant as failed with the reason and continue with the remaining variants.

## R3 · The contact sheet

- **R3.1** The `ssc` CLI shall write one contact sheet image showing every variant.
- **R3.2** The `ssc` CLI shall label each variant on the contact sheet with its index and its parameter values.
- **R3.3** The `ssc` CLI shall place every variant on the contact sheet at its own size, resampling nothing.
- **R3.4** Where a variant produced more than one frame, the `ssc` CLI shall show its first frame on the contact sheet.
- **R3.5** Where a variant failed, the `ssc` CLI shall leave its contact sheet cell empty and label it as failed.

## R4 · The review directory

- **R4.1** The `ssc` CLI shall write the variants, the contact sheet and the report into one review directory.
- **R4.2** Where a workspace and a key are given and no output directory is, the `ssc` CLI shall write into `review/<key>/`.
- **R4.3** If the review directory already holds a sweep, then the `ssc` CLI shall refuse unless replacement was asked for.
- **R4.4** The `ssc` CLI shall record the command, the input and the range it ran with in the report, so the comparison can be read without the invocation that produced it.
- **R4.5** While `--dry-run` is in effect, the `ssc` CLI shall write nothing and shall report the variants it would have produced.

## Out of scope

**Paid commands.** `sweep` is under `tool`, so it is free, and a ceiling on variants is
meaningless the moment a variant costs money. Sweeping a model's parameters is a different
feature with a different guard, and `specs/budget-guard/` is what it would go through.

**Choosing.** Nothing here picks a winner or writes one back into an asset. R2.3 reports an
arithmetic fact about defect counts; a person decides, through `ssc gate approve`.
