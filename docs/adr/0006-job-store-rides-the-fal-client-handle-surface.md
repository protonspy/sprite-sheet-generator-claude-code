---
status: accepted
---

# 0006 · `job-store` rides `fal-client`'s handle surface, pinned to 1.x

## Context

`adr:0005-a-job-always-exists` assumes a specific provider capability: that a request id
written to disk is enough for a *different process* to ask about, collect, or cancel the
work. If `fal-client` only handed out a live handle bound to the submitting process, the
job store would be a log rather than a recovery mechanism, and `ssc job resume` could not
exist.

This was settled by reading the client, not the documentation — fal.ai's docs site refused
every read with HTTP 429 while the plan was being written, and the same route (read the
client, then verify by introspection) is the one to take when they are unreachable again.

Verified against the installed package rather than inferred:

| Version | `submit` | `get_handle` | `status` | `result` | `cancel` |
|---|---|---|---|---|---|
| 0.4.0 | yes | — | — | — | — |
| 0.5.0 | yes | yes | yes | yes | — |
| 0.7.0 | yes | yes | yes | yes | yes |
| 1.0.0 | yes | yes | yes | yes | yes |

All of them take `(application, request_id)` as plain arguments. On 1.0.0 the handle
returned by `get_handle` exposes `status`, `get`, `cancel` and `iter_events`, and
`SyncRequestHandle.from_request_id` reconstructs one directly.

## Decision

Build `specs/job-store/` on that surface: `submit` returns a `request_id`, the id and its
application are what the job file records, and every later operation goes through
`get_handle(application, request_id)`. No live handle is kept, and none is needed —
which is also what makes the store testable without a network, since the recorded pair is
the entire state.

Pin **`fal-client>=1.0,<2`**. The surface exists from 0.7.0, so the floor is not about
availability; it is about the promise. 1.0 is the first release that commits to a stable
major, and the upper bound is what stops a 2.x from silently changing the four calls this
design is built on. Retrieval is by polling `status`; `submit` also accepts a
`webhook_url`, which is a polling-free alternative worth weighing inside the leaf and not
a precondition for it.

Against `subscribe(application, arguments)`, which is the shortcut the client offers and
the one this design cannot take: it submits and blocks in the calling process until the
result arrives, so the id never reaches disk and a death between the two loses the paid
result — the exact failure `adr:0005-a-job-always-exists` exists to prevent.

## Consequences

- A `fal-client` major bump is a deliberate act with these four calls to re-verify. The
  table above is the checklist.
- `job-store` is not provider-agnostic by accident — it is shaped around a pair of
  identifiers, which is the smallest thing a second provider could plausibly also offer.
  A provider without one does not fit, and `adr:0005-a-job-always-exists` says what
  happens then.
- Polling means `ssc job wait` owns a backoff, and a job left waiting costs nothing but
  the process doing it.
- The client is pure Python and small, so the pin does not drag a native dependency into
  the free half of the tool.
