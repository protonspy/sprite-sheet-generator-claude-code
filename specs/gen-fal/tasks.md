# Gen fal — tasks

**What already covers these paths:** `tests/cli/test_jobs.py` and
`tests/cli/test_job_commands.py` cover the store this leaf writes through — including
`submit`'s record-then-call order and the `PROVIDERS` lookup a fal adapter registers into;
`tests/cli/test_models.py`, `tests/cli/test_model_commands.py` and
`tests/test_model_registry_fallback.py` cover the schema check and the core-option mapping
every call goes through; `tests/cli/test_kinds.py` covers the profile that names the template
and the model. 990 tests, run green before this work started.

## 1 · The provider

- [x] 1.1 (Unit) A fal adapter over the client's `status`/`result`/`cancel`, registered as `"fal"`, translating its statuses into job states — R1.1
- [x] 1.2 (Unit) Refuse before submitting when there is no credential, and get a local image to the model inline or by upload, with the ceiling that separates them — R1.3, R2.2, R2.3, R2.4

## 2 · Building a call worth paying for

- [x] 2.1 (TDD) Reconcile a requested size against an enum of literal sizes or an aspect-ratio-plus-tier, and refuse when nothing is close enough — R3.1, R3.2
- [x] 2.2 (Unit) Build the resolved call: the kind's template, the core options, the raw options, the editing endpoint when an image is passed, checked against the schema — R2.1, R2.5, R2.6
- [x] 2.3 (Unit) `--dry-run` reports that resolved call and submits nothing — R4.3
- [x] 2.4 (Unit) Take a named template over the kind's, and ship the character templates the pipeline's own stages need — R2.7
- [x] 2.5 (Unit) Fill a template's named slots from `--var`, refusing an unknown slot and refusing a slot left empty before submitting — R2.8

## 3 · Submitting, collecting, filing

- [x] 3.1 (Unit) `ssc gen image` end to end against a fake client: record, submit, collect, write the file into the asset as a `source` and report the job — R1.1, R1.2, R4.1
- [x] 3.2 (Unit) `gen video`, `gen expand` and `gen bgremove` on the same pipeline, each choosing its own model — R1.1, R1.2
- [x] 3.3 (Unit) `--no-wait`, and `ssc gen collect <job-id> --asset` filing an already-paid result — R1.4, R1.5
- [x] 3.4 (Unit) Key the collected result by the resolved call, the model and the images sent, and reuse it instead of submitting — R1.6, R4.2
- [x] 3.5 (Unit) Carry the submitted key on the job so `gen collect` stores what it collects where waiting would have — R1.7
- [x] 3.6 (Unit) Refuse a result address that is not public `https`, on the first hop and on every redirect after it — R1.8

## Notes

**2.1 is the TDD task, and it is the one to look at before this merges.** Size reconciliation
is a small algorithm whose wrongness is invisible: pick the wrong member of GPT Image 1.5's
three-value enum and the model returns a plausible image with the sprites squashed, the job is
billed, and nothing in the output says the aspect was changed. It is also asymmetric — being
too permissive costs money and produces art nobody can use, being too strict costs a refusal
the caller can act on — so the test says what "close enough" means before the code gets a vote.

**Everything else is Unit because the shape is not in doubt.** The pipeline is plumbing over
three modules that already exist and already have tests; the risk in it is forgetting to go
through `jobs.submit` or `listing.bound`, which is a review question rather than a
test-ordering one.

**No test in this leaf reaches the network or reads a credential.** The client is injected
everywhere, and the suite has to pass with no `FAL_KEY` set — the same discipline
`model-registry` applied to the schema fetch, for the stronger reason that this half bills.

**The red on 2.1 was observed** as a `ModuleNotFoundError` for `ssc.cli.gen` — the test named
a function that did not exist yet, which is the honest first red for a module being created.
The tests then drove two decisions the implementation would not have arrived at on its own:
the enum is matched by *shape* and not by pixel count, so a 1200x800 board takes 1536x1024
rather than the square that is closer in area; and a request larger than every resolution
tier is reported rather than refused, because scale survives a nearest-neighbour resize and
aspect does not.

**One thing outside this leaf moved, and it is named in the PR.** `ssc.yaml`'s reader is now
`cli/config.py`, because `models:` is the second setting to be read from it and a second
reader would mean a second ceiling, a second loader and a second answer to what a malformed
config does. `kinds.declared` keeps the part that is about kinds and calls it for the read.

**Resolving an address needed nothing: `listing.resolve` was already there.** This leaf was
written against an earlier `main` and carried its own move of `asset_dir_for` out of
`commands/recover.py`. By the time it landed, `workspace-foundation` R3.7 had put that
invariant in `listing` under the name `resolve`, held rather than merely checked — so the
move was dropped and the four call sites use what exists.

**3.5 and 3.6 are the review's, and both are the same shape: a guarantee that held on the
path somebody tested and not on the path beside it.**

`gen collect` filed its result and cached nothing. Waiting cached; collecting did not — so
`--no-wait`, `gen collect`, then re-issuing the same command missed the cache and billed a
second time for bytes already in the asset. R1.6 was tested only on the waiting path, which
is why it read as covered. The key cannot be rebuilt at collection time, because it covers
the digests of the images sent and the job record elides those to stay readable; so the job
carries the key its submission computed, which is `job-store` R1.6 and the one place the
whole input is known. The regression test was run against the unfixed code first and does
fail there — a test for a bug nobody has watched fail is a test of nothing.

`fetch` checked that the URL was `https` and then followed redirects with the check behind
it, so an `https` result URL redirecting to `http://localhost` or to a cloud metadata
address was followed and the body written into the asset as a `source` — and cached under
the *original* call's key, so it replays. Two things were wrong rather than one: the hops
were unchecked, and `https` was never the question in the first place, since
`https://169.254.169.254/` satisfies it with no redirect at all. So the guard resolves the
host and refuses loopback, private, link-local, reserved, multicast and unspecified
addresses, and every hop goes through it. What it does not close is stated in the code
rather than glossed: the name is resolved here and again by the connection, and pinning the
socket to the checked address is a custom transport this CLI does not earn.

**What R3.7 cost this leaf, and it is the part worth reading.** `meta.load` and the asset
directory now travel as a held `Directory` rather than a path, and the recovered code read
its `--from-stage` input with `listing.inside(directory, ...)` — a path join against an
object that is no longer a path. It failed loudly, which is the good case. The fix is
`gen.image_in`, the bytes counterpart of `gen.image_at` and the same split
`frames.decode_image` makes against `frames.load_image`: a loose `--in` file is nobody's
asset and a path is the whole answer, while a staged file is read through the binding its
address was checked against. The binding is now held across the record *and* the file it
names, because dropping it in between would have bound the half that costs nothing.
