---
status: accepted
---

# 0004 · Generation ships in v1, under a verb that means "this bills"

## Context

`ssc` could have been a repair tool only — everything under `tool` is local, free,
deterministic and needs no account. That version is genuinely useful and it is what M1
delivers on its own.

It is also not the workflow. The material this tool exists to fix comes out of an image or
video model, and the loop that produces a usable asset is generate → measure → repair →
regenerate. A tool that owns the middle two steps and hands the other two back to the
operator is asking them to carry the parameters — which board, which size, which model,
which seed — across a boundary by hand, every iteration. That is where the reproducibility
this whole design is built around leaks out.

The reason to defer generation was risk, and the risks are real: it costs money, it needs
an API key, it couples the tool to a provider, and it introduces asynchrony and failure
modes that none of the deterministic commands have.

## Decision

Generation is in v1, as milestone M3, and the risks are handled rather than deferred.

The commitment that makes it safe is in the command surface: **`gen` means the provider
does it and charges for it; `tool` means local, free and synchronous.** The verb carries
the guarantee, so an agent reading `ssc --help` can tell which calls burn credit without
inspecting a single flag. This is why hosted background removal is `gen bgremove` even
though nothing about it is generative — cost is the discriminator, not creativity. A
`--provider` flag on one command would have destroyed the property.

Three further decisions fall out of that and are built alongside it: every provider call
produces a job (`adr:0005-a-job-always-exists`), a budget guard refuses before the call
rather than reporting after it, and every `gen` command first asks whether a deterministic
command produces the same result and refuses with that command as the fix when one does.

M1 and M2 remain fully usable with no API key. That is a requirement, not an aspiration:
if it stops being true, this decision was implemented wrong.

## Consequences

- The tool has a paid path, and every design after this one has to be honest about which
  side of the line it is on. New verbs (`gen upscale`, `gen relight`) get placed by cost.
- Provider coupling is real but bounded: Fal is the only provider in M3, and
  `model-registry` and `budget-guard` are shaped so a second one fits — including one that
  meters by subscription and never increments a per-call total.
- The test suite cannot cover the paid path end to end. What is testable is everything up
  to submission — resolution, validation, the refusal, the estimate — which is why
  `--dry-run` returns the fully resolved call rather than a summary of it.
- Users who want the free tool carry the `fal-client` dependency anyway. That is a small
  pure-Python package and was judged cheaper than a second distribution.
