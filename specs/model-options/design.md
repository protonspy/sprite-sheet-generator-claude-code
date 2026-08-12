---
autonomy: auto
ci: wait
lang: en
---

# Model options — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R1.5, R1.6, R1.7, R1.8, R3.1, R3.2, R3.5, R4.1, R4.3.

Four endpoints join `data/models.json`, their input schemas copied from the OpenAPI document
Fal serves for each — `openai/gpt-image-2`, `openai/gpt-image-2/edit`,
`xai/grok-imagine-image/v2.0/text-to-image`, `xai/grok-imagine-image/v2.0/edit`. Each gets a
mapping in `data/core.json`. Nothing about how a schema is read changes: the registry still
fetches the live document and falls back to the shipped copy.

Registering the two `/edit` endpoints is what makes editing an existing image work on both new
models. `endpoint_for` already resolves a call carrying `--ref` or `--from-stage` to
`<endpoint>/edit` and refuses with `no-edit-endpoint` where there is none, so no routing
changes. `openai/gpt-image-2/edit` also carries `mask_url`, which is inpainting — reachable as
`--opt mask_url=…` and reported by `ssc model show`, and not given a flag of its own here.

`core.json` grows three things beyond the per-model mappings:

- **`concepts`** gains `count`, `quality` and `format`, and `models.CONCEPTS` gains the same
  three. `load` already refuses when the two disagree, so they cannot drift apart.
- **`defaults`** — `{"image": "openai/gpt-image-2", "video": "xai/grok-imagine-video/image-to-video"}`,
  consulted by `Registry.chosen` last, after `ssc.yaml` and after the kind. Today a fresh
  workspace holds only `schema:` in `ssc.yaml`, so every paid command refuses
  `no-model-configured` until somebody edits it; this is what makes a new workspace generate.
- **a third size shape, `pixels`**, on the two GPT Image 2 endpoints.

`kinds.Profile` gains `options: tuple[tuple[str, Any], ...]`, read from `kinds.<name>.options`
in `ssc.yaml` — a tuple of pairs rather than a dict because `Profile` is frozen, which is the
same reason `checks` is a tuple. `FIELDS` derives from the dataclass, so `ssc kind show`
reports it and its provenance without further work.

`gen.build` gains one step between the ask and `registry.resolve`: the kind's defaults fill in
the core options the caller did not name. `write_result` becomes a loop over every file the
result carries.

The three flags land where the schemas support them, not uniformly: `--count`, `--quality` and
`--format` on `gen image` and `gen expand`; `--format` alone on `gen bgremove`; none on
`gen video`, because no video model in the registry has any of the three.

## Boundaries and contracts

### The pixel bounds are transcribed from prose, and that is a departure

Serves R2.1.

`model-registry` is built on schemas being read rather than transcribed. GPT Image 2 breaks the
assumption underneath it: the real constraints are stated **only in the description string** —
both sides a multiple of 16, longest edge 3840, ratio at most 3:1, total pixels between 655,360
and 8,294,400 — while the machine-readable part of the schema says `maximum: 14142` per side
and nothing more. `3841x512` satisfies the schema and is rejected by the model.

So the bounds are recorded in `core.json`, the file that is hand-authored by design and already
carries the size shape:

```json
"size": {
  "kind": "pixels",
  "field": "image_size",
  "multiple": 16,
  "max_edge": 3840,
  "max_ratio": 3.0,
  "min_pixels": 655360,
  "max_pixels": 8294400
}
```

Said plainly rather than hidden: those five numbers go stale silently if Fal changes them,
exactly as `model-registry` warns a transcribed table does. What makes it the lesser evil is
where the failure lands — a stale bound here produces a refusal or a rounded size, where the
alternative is a call that bills and comes back rejected. `adr:0013` records it.

### `Option` learns that a field may take an object

Serves R2.2.

`image_size` is `anyOf: [$ref ImageSize, enum of seven presets]`. `_type_of` finds the enum
branch and reports `string`; `_allowed` returns the presets. A `{"width": …, "height": …}` is
therefore refused by `_check_value` as not one of the presets. `Option` gains `objects: bool`,
set when an `anyOf` branch is a `$ref` or declares `type: object`, and `_check_value` accepts a
mapping for such a field. The `$ref` is **not** resolved: what bounds the value is `core.json`,
not the shape inside the ref, and following it would mean carrying `components` into a function
that today takes only the input schema.

### Size, in three shapes

Serves R2.3, R2.4, R2.5.

`reconcile_size` gains a `pixels` branch beside `enum` and `ratio`:

1. Refuse when the requested ratio is outside `1/max_ratio … max_ratio`, with the
   `size-unrepresentable` code the `enum` branch already raises — it is the same fact about the
   model.
2. Scale the request to fit `max_edge` and `max_pixels`, and up to reach `min_pixels`.
3. Round each side to the nearest `multiple`, never below one multiple, then step the longer
   side down by one multiple if rounding pushed the total past `max_pixels`.
4. Report `requested`, `chosen` as `WxH`, and `aspect_error` — the same keys the other two
   branches report, so a caller reads one shape whatever the model asks.

`Size.fields` becomes `dict[str, Any]`: the value for a pixel-shaped field is
`{"width": w, "height": h}` rather than a string. `Call.arguments` and the recorded payload pass
it through unchanged.

### Every file a call produced

Serves R5.1, R5.2, R5.3, R5.4.

`fal.file_urls(result)` returns every URL — the known result keys in order, depth-first within
each — and `file_url` becomes its first element, so `bgremove` and the video path are
untouched. `write_result` fetches each, files each as a `source`, and names the stages
`<stage>-1 … <stage>-N` when there is more than one. It cannot keep `<stage>` for the first:
`meta.record` refuses a stage the asset already holds, deliberately, so `--from-stage` is never
ambiguous. N files need N distinct stages, and the suffix is therefore unconditional across a
set.

The cache is one key to one blob by construction — the key *is* the content's identity. A set
needs an indirection, so `Cache` gains `put_set`/`get_set`: a manifest listing each member's
own key, with the manifest at `sha256("set:" + key)` and each member at
`sha256("member:" + key + ":" + i)`. Both are hashed rather than suffixed, because `path_for`
shards on the first two characters and a suffixed key would file a manifest in the same shard
as a content address that starts the same way. A manifest naming a member that is missing reads
as a miss, so a half-populated cache directory costs a regeneration rather than a partial write,
and `get(key)` on a set answers nothing — the single-file path is untouched.

## Alternatives considered

**A kind default naming an option the model lacks: refuse, or skip?** Refusing is what
`registry.resolve` does for a core option a caller *named*, and the asymmetry is the point. A
named option is somebody asking for something, and silently not doing it is the failure
`model-registry` R2.4 exists to prevent. A kind default is a policy that has to survive being
read by two models — `quality` exists on GPT Image 2 and does not exist on Nano Banana 2, and a
kind setting it would otherwise be unusable with half the registry. So: named refuses,
defaulted skips and reports that it skipped (R4.2).

**A package default, or `ssc init` writing one into `ssc.yaml`?** Writing it puts one fact in
two places — the package and every workspace ever created — and the copy is what goes stale
when the default changes. `workspace.create` also says in as many words that `ssc.yaml` is
almost empty on purpose. The default lives in the package; `ssc.yaml` stays an override.

## Risks

**The live schema is now weaker than the shipped copy for video.** Fal's current
`xai/grok-imagine-video/image-to-video` document declares `aspect_ratio` with no enum, where
`data/models.json` still carries eight values. With a live fetch, `_allowed_of` finds nothing
and `ssc gen video --size` fails `size-unknown`. It is not caused by this change and is not
fixed by it — it belongs to `model-registry`, which owns what happens when a fetched schema is
thinner than the fallback. Recorded here because the size work in R2 is the natural place for
somebody to look for it.
