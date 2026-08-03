# Gen fal — design

## What changes

Serves R1.1, R1.2, R1.4, R1.5, R2.1, R2.5, R4.1, R4.3.

Four modules, and no new machinery underneath them. Everything expensive in this leaf was
built by an earlier one, and the design is mostly a statement of what it is *not* allowed to
rebuild:

| New | What it is |
|---|---|
| `cli/fal.py` | the provider adapter — auth, submit, poll, collect, and getting a local file to the model |
| `cli/gen.py` | the one pipeline all four verbs run: choose the model, build the call, cache, submit, collect, write |
| `cli/commands/gen.py` | `ssc gen image · video · expand · bgremove · collect` |
| `cli/config.py` | `ssc.yaml` read once, for `models:` as well as `kinds:` |
| `data/templates.json` | the prompt templates a kind profile names |

**`jobs.submit` is the only way this leaf reaches the network.** That function exists with no
caller: it saves the record, makes the call, and saves the returned `request_id` — and the
order is the whole point of `specs/job-store/`. Submitting first and recording after passes
every test about what a job file holds and loses exactly the thing that matters: the id of a
request that was already billed, in the window where the process died. `gen` passes a closure
that calls `fal_client.submit(...).request_id` and touches nothing else.

**One pipeline, four verbs.** The verbs differ in which model they choose, which core options
they set and whether they carry an image; every one of them then runs the same seven steps —
resolve the asset and its kind, choose the model, build the call, check it against the
schema, look in the cache, submit through `jobs.submit`, collect and file. Writing four
commands that each own their own version of those steps is how the character case hardens
into the signature, which the plan names as this leaf's failure mode.

**The prompt template comes from the kind, not from the command.** `Profile.template` was
declared by `specs/asset-kinds/` for this leaf and has had no reader until now. `gen image`
on a `tile`-kind asset gets the tile template and a square canvas; on a `banner`-kind asset it
gets a different one — with one command, because the alternative is a command per kind and a
kind system that only extends as far as the CLI does. A profile naming a template nobody ships
is a refusal that names the templates there are, not a silent fall back to `generic`: a kind
whose whole purpose is to say how its art is generated should not quietly generate it like
everything else. `gen video` has one template and never passes a board.

## Boundaries and contracts

Serves R1.3, R1.7, R1.8, R2.2, R2.3, R2.4, R2.6, R4.2.

**The cache key travels on the job, because collection is a second process.** A result is
stored under `Call.key()`, which covers the resolved call, the model, *and* the digests of
the images sent. `--no-wait` splits submitting from collecting across two runs, and the
second one has only the job record — which elides those digests to stay readable, so it
cannot rebuild the key. Recomputing it there would be computing it from less than the
submitter had, and getting it wrong silently means the next identical call pays again. So
the submitting call writes the key it computed into the job (`job-store` R1.6, nullable
there because the store does not know what a cache is), and `gen collect` stores what it
collects under it. The invariant to hold: **collecting leaves the workspace in the state
waiting would have left it in** — anything true of one path and not the other is a bug in
whichever path was not tested.

**A result URL is fetched only from a public `https` address, and every redirect is that
question asked again.** The URL comes out of the model's own response, so it is untrusted in
the ordinary case rather than the paranoid one: the bytes it returns are written into the
asset as a `source` and cached under the *legitimate* call's key, which makes a poisoned
fetch both filed and replayable. Checking the scheme is not the check — `https://169.254.169.254/`
passes it — so the host is resolved and refused if it is loopback, private, link-local,
reserved, multicast, unspecified, or in RFC 6598 shared address space. Redirects are followed
by hand, capped, and re-checked at every hop, because `follow_redirects=True` validates the
URL it was handed and nothing after it.

**The provider surface is exactly `job-store`'s `Provider`.** `fal_client` exposes
`status(application, request_id)`, `result(...)` and `cancel(...)` at module level, taking
the pair as plain arguments and holding nothing between calls — which is
`adr:0006-job-store-rides-the-fal-client-handle-surface` restated as three functions.
`cli/fal.py` registers an adapter in `jobs.PROVIDERS` under `"fal"`, so `ssc job status|wait|
cancel|resume` start working on real jobs without a line changing in `commands/job.py`. The
adapter's only real work is translating the client's `Queued`/`InProgress`/`Completed` into
this project's job states.

**A local image travels inline by default, and that is a privacy decision.** Fal models take
`image_url`, so every anchor and frame is either uploaded to Fal's CDN — a third-party host
with a lifetime nobody here controls — or inlined in the request body as a data URL.
`fal_client.encode_file` is the default and `--upload` is the opt-in, which is the same
instinct as never spending money without being asked. Inlining has a real ceiling, so a file
past it is refused with `--upload` as the fix rather than submitted and rejected by the
provider after the request was built.

**Passing an image means a different endpoint, not a different parameter.** Both image models
put reference images behind `/edit` (`docs/wiki/model-parameters.md`), so `gen expand` and any
`gen image --ref` resolve `<endpoint>/edit` in the registry and refuse when the registry has
no such model — rather than sending `image_urls` to a base endpoint that would drop it.

**The job records the call, not the payload.** A data URL is megabytes of base64; written
into `jobs/<id>.json` it would duplicate a file that is already on disk and make `ssc job
list` unreadable. So an image argument is recorded as its digest and its byte count, and
everything else is recorded verbatim. The record stays the answer to "what did I pay for",
which is what it is for. `jobs.save` scrubs credentials on the way in; this is the same
instinct applied to bulk.

**The cache key is `cache.cache_key` with the model id as salt** — the extension point
`workspace-foundation` left for exactly this. `params` is the resolved call with image
arguments reduced to their digests, `inputs` is the digests of the images sent, and the salt
is `{"model": endpoint}`, because the same prompt against two models is two different results
and a cache that conflates them is worse than no cache. A hit writes the file and submits
nothing — the one case in this leaf where a `gen` command costs nothing, and it is reported
as `cached` like every other command's reuse.

## Data

Serves R4.1.

**An input read from a stage goes through the same binding as a write.** `--from-stage`
addresses a file the asset's own record names, so `listing.resolve` hands back a held
directory and `gen.image_in` reads through it — the counterpart of `gen.image_at`, which
takes a path because `--in` names a file that is nobody's asset and has no checked directory
to bind to. The binding is held across the record *and* the file it names: what a model is
paid to transform has to be what was read through the directory the address was checked
against, and a binding dropped in between would have covered the half that costs nothing.

A collected file is written into the asset through `listing.bound`, as
`specs/workspace-foundation/` requires of every asset write, and recorded as **`source`** —
the class `ssc clean` must
refuse to touch. That is the whole reason the class exists: a generated image cost money and
the model is not deterministic, so it is the one thing in the workspace that cannot be
reproduced. Its provenance carries the command, the job id, the model, and the resolved call.

## Alternatives considered

**`subscribe()` instead of `submit()` + poll.** The client offers one call that submits and
blocks until the result arrives. It is shorter, and it cannot be used here: the id never
reaches disk, so a death between paying and receiving loses a paid result — the exact failure
`adr:0005-a-job-always-exists` exists to prevent. Recorded there and not re-argued.

**`--no-wait` collecting later from the job alone.** A job record does not say where its
result should be filed, and adding a destination to it would put a workspace path into a
record whose whole design is a provider-shaped pair of identifiers. So `ssc gen collect
<job-id> --asset <kind>/<key>` takes the destination from the caller. It costs one argument
and keeps `job-store`'s schema the provider's, which is what lets a second provider fit.

## Risks

**Nothing here is exercised against the real provider.** Every test injects a fake client:
the suite must pass with no `FAL_KEY` and no network, and a test that pays money is a test
nobody runs twice. What that leaves untested is the shape of Fal's actual response — where
the URL sits in a completed result, and which exception a rejected call raises. Both are read
from the client and the published schemas rather than guessed, and both are isolated in
`cli/fal.py` so the first real call has one file to correct.

**A `Completed` status is not a successful one.** The client reports completion and surfaces
the failure when the result is fetched, so the adapter cannot treat `Completed` as `done` and
stop looking. Collection is what decides between `done` and `failed`, and a job that fails
keeps its record — it was still paid for, or at least still attempted.

**The address guard resolves the host, and the connection resolves it again.** Between those
two a DNS record can change, and the fetch would go somewhere the guard did not approve.
Closing it means pinning the connection to the address that was checked — a custom `httpx`
transport, for a CLI that talks to one CDN. The window is narrow (it needs authority over
DNS for a host fal itself named) and the trade is deliberate; what is not acceptable is
leaving it unsaid, so `_reachable`'s docstring states exactly what is and is not covered.
If `ssc` ever runs as a shared service rather than a local CLI, this is the line to revisit.

**The tolerance in the size reconciliation is a judgement, not a measurement.** Refusing a
6:1 board on GPT Image 1.5 is obviously right and accepting 1024×1024 for a 1.05:1 request is
obviously right; the line between them is chosen, and it is a constant with a comment rather
than a discovered constant. What keeps it honest is that the chosen size and the distance from
the requested one are both reported, so a caller can see a stretch it did not want.
