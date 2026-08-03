---
status: accepted
---

# 0005 · A job always exists

## Context

Everything under `gen` is paid and asynchronous: the provider queues the request, the
result arrives later, and the money is spent at submission rather than at collection. The
consequence that matters is not latency. It is that **the process which paid can die
before it collects** — a crash, a timeout, a closed laptop, a session that ran out of
context — and the result is sitting on the provider's side, already billed, addressable
only by an id that lived in that process's memory.

The obvious shape is to make the paid call synchronous and let long-running ones be a
special case: block, and if it takes too long, write something down. That is the shape
that loses money, because the special case is where the money is.

`fal-client` makes the alternative viable rather than aspirational. It exposes
`submit(application, arguments) -> handle` carrying a `request_id`, and then
`get_handle(application, request_id)` reconstructing that handle from the pair alone,
with no process-local state — see
`adr:0006-job-store-rides-the-fal-client-handle-surface`.

## Decision

Every provider call produces a **job**: a file under `jobs/`, one per job, written
atomically (temp file plus rename) before the call is considered made, carrying the
provider, the application id, the `provider.request_id`, the resolved arguments, the model
id and the cost. There is no synchronous path that skips it and no "small enough" call
exempt from it.

`ssc job wait|status|list|cancel|resume` is the surface over that directory, and `resume`
is the reason the rest exists: a fresh process reads the id off disk and collects a result
it never submitted.

Uniformity is the point. A store that only some calls write is a store no recovery path
can trust, and "was this the kind of call that recorded itself?" is not a question anyone
should have to answer after a crash.

## Consequences

- Every `gen` does filesystem writes before and after the network call. That cost is
  invisible next to a model round trip.
- `jobs/` is state that accumulates and needs a retention story. It is git-ignored: it is
  local operational state, not a deliverable.
- The atomic-write discipline is load-bearing, not ceremony. A half-written job file after
  a crash is exactly the case the store exists to survive, so temp-plus-rename is a
  requirement of `specs/job-store/`, and the record must be on disk **before** the
  submission returns rather than after.
- Gates and `ssc run` inherit this for free: resuming from disk after a session dies is
  the same mechanism, and that is why `gates-and-resume` can assume it.
- A provider without a retrievable request id would not fit. If one appears, it gets a job
  whose collection path is "cannot resume", stated rather than silently absent.
