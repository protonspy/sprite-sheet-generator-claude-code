# Model registry — tasks

**What already covers these paths:** `tests/test_model_registry_fallback.py` covers the
shipped `models.json` — that it is well-formed, that the six endpoints are there, and the
four facts about sizes and `seed` this leaf reasons from. `tests/cli/test_kinds.py` covers
profile resolution, which R3.2 extends; `tests/cli/test_workspace.py` covers reading
`ssc.yaml`, which R3.1 reads from. All were run green before this work started.

## 1 · The registry

- [x] 1.1 (Unit) Read the shipped registry into models with their media, endpoint and schema — R1.1, R1.3
- [x] 1.2 (Unit) Try the provider first, fall back to the shipped copy, and report which was used — R1.4, R1.5
- [x] 1.3 (Unit) `ssc model list [--media]` and `ssc model show <id>`, refusing a name nobody has — R1.1, R1.2, R1.3, R1.6

## 2 · The check that runs before the money

- [x] 2.1 (TDD) Refuse an option the schema does not declare, and a value outside what it allows — R2.1, R2.2
- [x] 2.2 (TDD) Translate the core options into a model's own spelling, and refuse one the model has no concept of — R2.3, R2.4

## 3 · Which model runs

- [x] 3.1 (Unit) Take the model per media from `ssc.yaml`, let a kind override it, and refuse one nobody knows — R3.1, R3.2, R3.3

## Notes

**Both TDD tasks are the same argument, and it is this leaf's whole reason for existing.** An
option the model does not have is not an error at the provider: the call succeeds, the
parameter is dropped, the job is billed, and the image is plausible enough that nobody
notices it ignored you. The failure this code prevents is *invisible by construction*, and a
test written afterwards tends to assert what the validator happens to do rather than what it
is for. Written first, they say the thing that matters — an unknown option stops the call,
and a core option the model lacks stops it too rather than going missing.

The second earns the annotation on its own. Dropping `--seed` silently is the behaviour a
reasonable implementation arrives at by accident — `mapping.get(name)` returns `None`, `None`
is falsy, the option quietly does not go — and the cost is a caller who believes their
generations are reproducible and cannot discover otherwise except by running twice and
comparing.

**The red was observed on both, and on 2.1 twice.** Both failed on `ImportError` first. Then
2.1 failed again against a working validator, for a reason worth keeping: the refusal puts
the offending value in the message and the *allowed* values in `fix`, and the test had
asserted both in the message. The split is right — `fix` is the field a harness acts on — so
the test moved rather than the code.
