---
autonomy: auto
ci: wait
---

# ssc — the 2D sprite pipeline

## Why

`ssc` is the set of primitives that takes any image to a game-ready asset with real
pixels, a transparent background, and metadata the engine can read — a character
spritesheet, but equally an icon atlas, a seamless tileset, a nine-slice UI panel, a
banner. Image and video models produce art that is not game-ready, and the defects are
systematic rather than accidental: fake pixel art, frame bleeding, drift, opaque
backgrounds, palette drift, flicker between frames, visible tiling seams, broken
cycles. Each command repairs one of those, is either deterministic or explicitly
expensive, and writes a new file — nothing ever mutates its input.

The plan closes when M6 ships: an agent starts from a base image, generates the poses
and the video, converts to real pixel art, assembles the sheet or the atlas, measures
the result with `doctor`, and publishes `dist/index.json` for the engine — stopping only
at the human gates, and resuming from disk after any session dies. Every milestone is
deliverable on its own: M1 already repairs a sheet you have today, with no API key.

## Decomposition

### M1 — the deterministic core · no API key

- `specs/workspace-foundation/` — `ssc init`, `ssc asset new <key> --kind <k>`,
  `ssc.yaml`, and the on-disk contract:
  `assets/<kind>/<key>/` with the numbered-prefix chain inside it, a `meta.json` per
  asset recording each file's provenance, its `stage` and its class (`source` ·
  `derived` · `output`), the content-addressed cache, `ssc clean` which may delete only
  `derived`, and the CLI contract every other command inherits — `--json` on all output,
  `--in`/`--out`, `--dry-run`, nearest-neighbour as the only resampler, exit codes
  `0 1 2 3`.
- `specs/asset-listing/` — `ssc image list [kind]` / `ssc video list [kind]`, filtered by
  kind, stage and class, and `ssc image show <key> --stage nobg` / `ssc video show <key>`
  resolving a stage to a file without the caller knowing its number and returning that
  file's lineage and its `doctor`. Two media nouns, because generation has exactly two;
  everything a command writes is one or the other.
- `specs/sheet-doctor/` — `ssc tool doctor`: seven checks (`pixel_grid`, `bleed`,
  `drift`, `halo`, `palette`, `flicker`, `silhouette`), each defect carrying the
  command that fixes it, and the fixtures with known, measured defects that prove the
  detector.
- `specs/pixel-art-conversion/` — `ssc tool snap` (fake pixel art → a real grid, via
  the spritefusion-pixel-snapper `.wasm`, then nearest-neighbour back up to the
  working size) and `ssc tool pixelart` (art of any origin → true pixel art: palette
  quantization, controllable dithering, outline emphasis, orphan-cluster cleanup).
  Both run outside a workspace with plain `--in`/`--out`, both accept a set of frames
  and compute **one** grid and **one** palette for all of them, and neither assumes
  a character — an environment, a tile or an icon is a legitimate input. Plus
  `ssc tool board`, which *generates* the two reference images the generation step
  needs: a black-and-white checkerboard at a given square size, and a pose board of
  `<cols>x<rows>` cells at a given cell size.
- `specs/background-removal/` — `ssc tool bgremove` by chroma: `--chroma` (green and
  magenta presets), `--tol`, `--mode global|flood`, `--edge-pass`, `--edge-trim`,
  `--despeckle`, real alpha with no semi-transparent halo. `flood` is the default and
  starts from the border, so a green gem inside the character survives.
- `specs/frame-recovery/` — getting N pieces out of one image, in three modes — fixed
  grid, chroma bounding box, connected-component islands with `--min-size` and
  `--max-aspect` — plus **grid auto-detection**, so a sheet of unknown origin can be cut
  without the caller already knowing its layout. `ssc tool cut` binds the pieces as the
  frames of one animation, `ssc tool slice` binds them as N distinct assets each with its
  own key, and `ssc tool curate` drops the redundant ones.
- `specs/sheet-assembly/` — putting the pieces back on a grid: `ssc tool expand`
  (deterministic canvas padding, to a size or by a margin, filling with chroma or alpha),
  `ssc tool mirror` (horizontal flip, the free way to get East from West),
  `ssc tool align` (lock the anchor on feet, bottom, centre or eyes, with onion-skin
  output), `ssc tool pack` (fixed cell, recorded anchor).

### M2 — every other kind of asset · still no API key

- `specs/asset-kinds/` — a kind is an **extensible profile**, not a closed enum: a name
  declaring cell size, anchor mode, whether it animates, its atlas layout, which
  `doctor` checks apply to it, and which generation template it uses. Built-ins ship
  with the package — `character`, `icon`, `tile`, `ui`, `banner`, `map` — and a project
  declares its own in `ssc.yaml` without touching code. `ssc kind list` is how a caller
  discovers them, since an extensible set cannot be hard-coded into a harness.
- `specs/atlas-packing/` — `ssc tool pack --atlas` for any non-animated kind: bin
  packing, a stable id per entry, `--padding` and `--extrude` so the GPU cannot sample a
  neighbour across an entry boundary, and an index entry carrying each entry's rect and
  anchor. This is what icons, banners and map pieces all share.
- `specs/tile-assets/` — `ssc tool tile --seamless` closing the wrap seam, the `seam`
  check in `doctor`, and a tileset index carrying tile size and tile ids.
- `specs/normal-maps/` — `ssc tool normal --strength`, deriving a normal map from a
  finished asset so a 2D engine can light it, and the index field that points at it.
  Works on any kind; a kind profile says whether one is produced by default.
- `specs/parallax-layers/` — the `background` kind: an asset that is N layers rather than
  one image, each layer a file, each carrying a scroll factor the index emits. Layers are
  explicit — separating a flat painting into depth planes is a CV problem and stays out.
- `specs/ui-assets/` — `ssc tool ninepatch` for panels and buttons: slice guides that
  land on the pixel grid, the `nineslice` check in `doctor`, and state sets
  (normal/hover/pressed/disabled) packed as one sheet. Named `ninepatch` and not
  `slice`, which `frame-recovery` already owns for a different operation.

### M3 — generation · costs money

- `specs/job-store/` — `jobs/`, one file per job, atomic writes (temp + rename),
  `ssc job wait|status|list|cancel|resume`, and the `provider.request_id` that
  recovers an already-paid result after a crash.
- `specs/model-registry/` — `ssc model list [--media image|video]` and
  `ssc model show <id>` reporting the options that model actually accepts, defaults per
  media in `ssc.yaml` overridable by a kind profile, and **validation against the
  model's schema before anything is submitted**. A small normalised core maps across
  models — prompt, input image, `--seconds`, `--size`, `--seed` — and everything else
  goes through raw as repeatable `--opt <key>=<value>`. `--dry-run` returns the **fully
  resolved call** — model, size, template, every option, estimated cost — so a caller can
  inspect the decision before paying for it. The model id is part of the cache key and is
  recorded in the job.
- `specs/gen-fal/` — `ssc gen image`, `ssc gen video`, `ssc gen expand` (generative
  outpaint) and `ssc gen bgremove` (BiRefNet as a hosted model) over Fal AI, on
  `fal-client` — `FAL_KEY` for auth, `submit` for the queue, `encode_file` or
  `upload_file` to get a local image to the model. `gen` means
  *the provider does it and charges for it*, not *it creates something* — that is what
  keeps the price readable in the verb. `gen image` picks its prompt template from the
  target asset's
  kind profile, so a tile, a banner and a character are generated by three different
  templates without three different commands; `gen video` has one template and never
  passes a board. The two boards are not interchangeable — the checkerboard imposes
  block discipline, the pose board declares the frame layout. **The layout determines the
  required size, and `gen image` reconciles it against what the model supports** — it
  picks the nearest allowed size and reports the discrepancy, or refuses when no allowed
  size is close enough, rather than submitting an aspect the model will quietly squash.
  Cache keyed by input hash.
- `specs/budget-guard/` — `budget.max_usd` and `budget.warn_at` in `ssc.yaml`, a
  running total in the workspace read back by `ssc budget`, a refusal before every `gen`,
  an estimate under `--dry-run` that excludes the jobs a free path would have covered,
  and retry only on transient network errors. Every `gen` command first asks whether a
  deterministic command produces the same result, and refuses with that command as the
  fix when one does.

### M4 — gates and harness · the human in the loop

- `specs/sweep-and-review/` — `ssc tool sweep` across a parameter range, a contact
  sheet of the variants with each one's `doctor`, and `review/<key>/` as the material
  awaiting a decision.
- `specs/gates-and-resume/` — `ssc gate list|open|approve|reject` as state in the
  workspace (exit code `3` while pending, never a question in the conversation), an
  approval becoming an inheritable default, and `ssc run` / `ssc status` to stop at
  the next gate and resume from disk.
- `specs/engine-index/` — `ssc index --format pixi|phaser|godot|generic`, one
  `dist/index.json` covering every kind: sheets with cell, grid, fps, loop and the
  anchor that stops the engine re-centering the sprite; atlases with a rect per entry;
  tilesets with tile size and ids; nine-slice borders for `ui`. Playback is `loop`,
  `ping-pong` or `reverse`, and one sheet may declare **named sections** — an attack's
  windup, hit and recovery are three ranges of one animation, not three sheets. Plus
  `ssc preview`, which renders an animated GIF or a contact sheet from what the index
  declares, and a 2×2 tiled preview for `tile` assets — the cheapest way to see that the
  numbers are right before an engine reads them.
- `specs/frame-metadata/` — per-frame boxes and markers: an alpha bounding box `ssc`
  derives for free, hit and hurt boxes authored in a sidecar, and named markers on a frame
  (footstep, spawn, cancel window). Validated against the frame count so a curated frame
  cannot silently shift them, and emitted into the index. `ssc` carries these values; it
  never invents damage or knockback.
- `specs/sprite-skills/` — the six harness skills: `sprite-cleanup`,
  `sprite-animation`, `sprite-style`, `sprite-character`, `sprite-resource`,
  `sprite-integrate`.

### M5 — style and derivation

- `specs/style-and-palette/` — `ssc tool style`, the project-locked `palette.json`,
  named presets (pico8, nes, gameboy, sweetie16), ordered or Floyd-Steinberg
  dithering as a project decision, and palette coherence across every asset.
- `specs/asset-derivation/` — `ssc asset new <key> --extends <parent>` and the
  `<asset>.yaml` behind it: it inherits the recipe (kind, pixel_size, palette, cell,
  frame counts, fps, the parent's anchors as a generation reference), never the pixels.

### M6 — computer vision · the `[cv]` extra

- `specs/cv-runtime/` — where model inference runs: `--device auto|cpu|cuda|directml|
  coreml`, the `[cv]` and `[cv-gpu]` extras that install the matching `onnxruntime`
  build, and the execution provider folded into the cache key. `auto` picks the best
  available; a device named explicitly fails loudly rather than falling back.
  **Hardware detection is independent of the installed runtime**: `ssc info` reports the
  GPUs present and the providers usable, and when a capable GPU exists but only the CPU
  extra is installed, every model-backed command returns that gap as a structured hint
  carrying the exact install command — once per run, suppressible, and a field in the
  JSON rather than a line of chatter.
- `specs/cv-background-removal/` — `ssc tool bgremove --model birefnet|rembg` under
  the `[cv]` extra, degrading cleanly with an actionable message when the extra is not
  installed.
- `specs/cv-motion-consistency/` — pose tracking through an animation cycle and a
  consistency embedding across frames.

## Tasks

- [ ] 0.1 (Unit) Build spritefusion-pixel-snapper for `wasm32-wasip1` — write the thin
      wrapper crate exposing a flat ABI over `process_image`, vendor
      `vendor/pixel-snapper.wasm` alongside the upstream `LICENSE`, and prove with a
      test that `wasmtime` loads the module and snaps a fixture
- [ ] 0.2 (Unit) Record the decisions already made in `docs/adr/` — Python + uv, the
      snapper vendored via WASI, generation inside v1, a job always exists — plus the
      outcome of 0.1 as its own record
- [x] 0.3 (Unit) Fill in `.claude/rules/project.md` (build, test, scoped test, lint,
      format) and `docs/stack.md` with the core dependencies, `fal-client` among them
- [ ] 0.6 (Unit) Record as an ADR that `job-store` is built on `fal-client`'s
      `submit` → `get_handle(application, request_id)` → `status`/`result`/`cancel`
      surface, and pin the client version that provides it
- [ ] 0.7 (Unit) Pull the endpoint ids and parameter schemas for the four models this
      workflow names — Nano Banana 2, GPT Image 1.5, Grok Imagine Video, BiRefNet — into
      the shipped registry fallback, and confirm whether Fal exposes them machine-readably
      or they have to be transcribed
- [ ] 0.4 (Unit) Settle in `docs/glossary.md` the vocabulary all twenty-seven specs inherit:
      key, kind, stage, source, derived, output, anchor, cell, sheet, frame, atlas, tile, seam, nine-slice, job, gate,
      snap, pixelart, flicker
- [x] 0.5 (Unit) Distil the design document and the three transcripts in `docs/raw/`
      into `docs/wiki/` pages reachable from `index.md`, then delete the raw files

## Notes

**Order.** `workspace-foundation` first — every other leaf writes `meta.json` and
speaks the same JSON contract. Then `sheet-doctor`, ahead of the tools it measures:
that is "measure, don't guess" applied to this repo, and the fixtures with measured
defects are what stops the detector from regressing silently. `pixel-art-conversion`
and `background-removal` are independent of each other after that and are the natural
candidates for parallel sessions — one worktree each. The last two are a chain, not a
fan-out: **`frame-recovery` has to follow `background-removal`**, because two of its
three modes work by finding the chroma, which is that leaf's parameter, and the two
sharing one notion of "what the background is" is the whole point; **`sheet-assembly`
then follows `frame-recovery`**, because it assembles what that produces.

**`tool slice` is how existing material gets in, and that is why it is M1.** `cut` and
`slice` are the same algorithm with different output bindings — `cut` writes the frames
of one animation, `slice` writes N distinct assets each with its own key and its own
lineage. Keeping them one leaf keeps the three detection modes (grid, chroma bounding
box, connected-component islands) in one place; splitting them by binding would have
produced the same detector twice. Without `slice`, M1's promise — "repairs a sheet you
already have" — only holds for someone whose asset is already cut apart, which is
nobody.

**`expand` is split by what it costs, not by what it does.** `tool expand` pads a
canvas: deterministic, free, and needed inside the pipeline itself, because a frame
whose content overflows its cell — or a character the model cropped at the edge — has
to gain margin before anything measures its bounding box. Today that padding is
implicit inside `align` and `pack`, which is worse than it sounds: an implicit
operation writes no `meta.json` entry, so it cannot be reproduced or debugged.
`gen expand` outpaints: a model invents the new area, it costs money, it returns a job.
One name for both would hide the price behind a flag, which is exactly what principle 2
forbids.

**Task 0.1 blocks `pixel-art-conversion`, and it is more than swapping a flag.**
Upstream is Rust and documents `wasm-pack build --target web`, which produces
`wasm32-unknown-unknown` plus wasm-bindgen JS glue; the public signature is
`process_image(inputBytes, kColors, pixelSizeOverride, paletteHex)`, whose types do
not cross the boundary without that glue. The path is a thin wrapper crate exporting a
flat ABI — or a WASI `main` reading stdin and writing stdout — compiled to
`wasm32-wasip1`. If it does not build, the fallback ladder is: a native per-platform
binary from `cargo build --release`, or porting the algorithm to numpy and paying that
cost. The decision is taken with the evidence in hand and becomes an ADR.
`ssc tool pixelart` does not depend on the `.wasm` and proceeds either way.

**`proper-pixel-art` was considered and not adopted.**
[It](https://github.com/KennethJAllen/proper-pixel-art) (MIT, Python, on PyPI) would
have removed Rust, `wasmtime` and the vendored binary from the critical path, and it
detects the grid itself (Canny → Hough → median spacing) and computes one mesh and
palette across a video's frames. It was passed over for the maturity and provenance of
the snapper, whose dithering preservation was the original argument for vendoring it —
a naive modal downsample destroys the pattern, and dithering is a wanted aesthetic.
What this costs is that grid detection and the shared cross-frame palette are our code
rather than a free side effect. That is a smaller loss than it looks: `doctor` owes a
`pixel_grid` detector regardless of which engine `snap` wraps, and the `flicker` check
needs the shared palette regardless.

**`flicker` is the seventh check, and it was not in the design document.** The defect:
a region that did not move changes colour between adjacent frames, because each frame
quantized on its own. `palette` measures new colours against the project limit and
does not see this. It is why `snap` and `pixelart` take a set of frames rather than one
file at a time — the fix is structural (one palette for all of them), not a
post-process.

**The reference boards are generated, never vendored.** Both sources treat the
black-and-white checkerboard as the trick that makes an image model produce
block-shaped pixels, and both distribute it as a download behind a mailing list. Two
reasons not to take it: it is somebody else's file under a licence we do not have, and
a fixed PNG freezes a parameter that should track the project. One source describes a
checkerboard alternating every single pixel, the other a grid of black and white
*squares* — those are different images, and which one works is an empirical question
per model. `ssc tool board` makes it answerable with `tool sweep` instead of settling
it by guess. It lives in M1 because it is local, deterministic and free, and because
it is useful on its own: it lets someone with no API key produce a board and paste it
into whatever image tool they already use.

**Nearest neighbour is an invariant, not an option.** Every resize anywhere in the
pipeline — snapping back up to the working size, scaling a recovered frame down to the
final cell, previewing — uses nearest neighbour. Any other resampler reintroduces the
sub-pixel blur that `snap` just removed, which means one careless `Image.resize()`
undoes the entire point of M1. It belongs in `workspace-foundation`'s contract so that
no later leaf has to remember it.

**`snap` runs twice, and that is by design.** Once on the anchor, so the reference the
model works from is already clean; again on each frame recovered from a generated
sheet, because the model's output is blurry regardless of how clean the input was.
Consequence for `pixel-art-conversion`: it is called far more often than a one-shot
tool would be, so it has to be cheap and cache well — not a batch job with a progress
bar.

**The layout is `assets/<kind>/<key>/`, and that is a reversal of the design
document.** The original grouped by stage — `images/`, `videos/`, `frames/`,
`sprites/`, with the key underneath. That answers "where are the videos" well and "what
exists of kind tile" badly, and the second is the question an operator and an agent
actually ask. Kind first also keeps an extensible kind system honest: a project-defined
kind gets a directory, not a special case. Inside the key the chain stays flat —
`001_anchor_s.png → 002_anchor_s.snap.png → 003_anchor_s.nobg.png` — so one `ls` still
reads the whole lineage, and `frames/` is the only subdirectory because it is the only
set. This is the hardest thing in the plan to change later, so it owes an ADR from
`workspace-foundation`.

**Files are classified by reproducibility, not by size — and the design document had
this backwards.** It said to version `sprites/` and ignore `videos/` because video is
heavy. But a generated video is the one thing in the workspace that *cannot* be
reproduced: it cost money and the model is not deterministic. Ignoring it throws away
the most expensive artefact and keeps the cheap ones. So every file carries a class.
`source` is what a model produced — non-reproducible, always versioned, and `ssc clean`
must refuse to touch it. `derived` is everything a deterministic command computed from a
source with recorded params — safe to delete and regenerate, which is what makes the
workspace reconstructible after wiping `cache/`. `output` is the deliverable. This is
what turns "keep the raw image" from a convention people follow into a guarantee the
tool enforces.

**A stage is addressable by name, not by number.** The numbered prefix orders the chain
for a human reading `ls`; it must not be how a caller finds a file. `002_anchor_s.snap.png`
carries `stage: snap` in `meta.json`, so `--stage nobg` resolves without anyone counting.
Otherwise inserting one step in the middle renumbers everything downstream and breaks
every script that hard-coded `003`.

**Listing is its own leaf because an agent cannot glob.** A harness driving this tool
needs to ask what exists before it can decide what to do, and the honest answer has to
come from a command with a JSON contract, not from the caller reconstructing paths.
`ssc image list tile` is a directory scan precisely because the layout above put kind
first — the CLI surface and the disk layout are one decision, not two. The nouns are
`image` and `video` because generation has exactly two modalities and everything the
tool writes is one of them: a frame is an image, a sheet is an image, an atlas is an
image. `gen` creates, `tool` transforms, `image`/`video` observe.

**A kind is a profile, not an enum — and that is why M2 exists at all.** The kinds an
asset library needs are open-ended: character, icon, tile, ui, banner, map, and then a
cursor, a portrait, a font, a VFX sheet. A closed enum makes every new one a code
change and a release; a profile — a name declaring cell, anchor mode, whether it
animates, atlas layout, applicable `doctor` checks, generation template — makes it a
line of `ssc.yaml`. That is a hard-to-reverse choice about the shape of the whole tool,
so `asset-kinds` owes an ADR, not a paragraph in its design. `workspace-foundation`
only records the `kind` field; the profile system that gives it meaning is M2's.

**M2 is placed second because it is the cheapest path to a real deliverable.** Icons,
tiles, banners and UI do not animate, so they need no video, no cycle, no drift
correction and no API key — `pixelart` plus `bgremove` plus `pack` already does most of
it. Two genuinely new algorithms carry the milestone: closing a wrap seam, and slicing
a nine-patch on the pixel grid.

**M2 is the first exercise of the anchored-spec rule.** `tile-assets` adds the `seam`
check and `ui-assets` adds `nineslice`, both as **deltas against `sheet-doctor`** rather
than new documents; `atlas-packing` extends `pack`, which is `sheet-assembly`'s. Three
leaves editing two earlier specs in their own branches, in their own PRs. If that turns
out to be painful in practice, it is telling us the M1 split was wrong — worth watching.

**M3 depends on all of M1 and on `asset-kinds` in M2.** On M1 because `gen` is only
useful once there is something to do with what it returns; on `asset-kinds` because
`gen image` reads its prompt template out of the kind profile. That second dependency
is the whole reason a tile does not need its own command: `gen image` on a `tile`-kind
asset gets the tile template, a square canvas and no pose board, and `gen image` on a
`banner`-kind asset gets a different one. Building `gen-fal` against the character case
alone and generalising later is the failure mode — the template would harden into the
signature. `job-store` before `gen-fal` — the job is the contract and generation is
merely one producer of it. `budget-guard` can land alongside or right after, but not
after the first real batch.

**`job resume` is confirmed viable, from the client source.** `fal-client` exposes
`submit(application, arguments) -> handle` carrying `request_id`, and then
`get_handle(application, request_id)`, `status`, `result` and `cancel` — all taking the
pair as plain arguments, with no process-local state. That is exactly the shape
`job-store` assumes: submit, record the id, die, collect an already-paid result from a
fresh process. The Fal documentation site refused every read (HTTP 429), so this was
settled by reading the client on GitHub instead; the same route is the one to use when the
docs are unreachable again. The client also supports `webhook_url` on submit, which is a
polling-free alternative worth weighing inside the leaf but not a precondition for it.

**Local files have to become URLs before a model sees them, and that is a privacy
decision.** Fal models take `image_url`, so every board, anchor and frame `ssc` sends is
either uploaded to Fal's CDN via `upload_file` or inlined as a data URL via `encode_file`.
The two differ in more than latency: uploading puts the user's art on a third-party CDN
with a lifetime nobody in this project controls, while a data URL keeps it in the request
body. Default to `encode_file` and make the upload an explicit choice for payloads too
large to inline — the same instinct as never spending money without being asked.

**An unknown model option must fail before submission, not after.** Passing options
straight through to the provider looks like flexibility and is a money leak: type
`--opt guidance_scale=7` at a model whose field is `cfg` and the call succeeds, the
parameter is dropped, the job is billed, and the image that comes back is plausible
enough that nobody notices it ignored you. So `model show` reads the model's schema —
from the provider at runtime, cached, with the shipped registry as the offline fallback
— and `gen` validates against it. A registry hard-coded in the package would be stale
the week after Fal adds a model, which is why the shipped copy is the fallback and not
the source. The model id joins the cache key for the same reason the CV execution
provider does: the same prompt against two models is two different results, and a cache
that conflates them is worse than no cache.

**`gen` means "the provider does it and charges", not "it creates something".** Fal hosts
BiRefNet, so background removal by model can be a remote call with no `onnxruntime`, no
model download and no GPU story at all — which makes it the third path alongside chroma
and the local `[cv]` model. It costs money and returns a job, but it is plainly not
generation, and that forced the question of what the two verbs actually mean. The answer
that keeps the guarantee is cost, not creativity: everything under `tool` is local, free
and synchronous; everything under `gen` bills. An agent scanning the command list can
still tell which calls burn credit without inspecting a single flag — which is a safety
property worth one slightly awkward word, and which a `--provider` flag would have
destroyed. It also leaves room for `gen upscale` and `gen relight` without another
argument about where they go.

Consequence worth naming: model-quality background removal arrives in **M3**, not M6, and
the `[cv]` extra becomes the offline option rather than the only one. `cv-runtime` and
`cv-background-removal` still earn their place — a local model is free per call and works
with no key — but they stop being on the critical path to a good mask.

**The layout asks for a size; the model offers a set of sizes; somebody has to
reconcile them — and it must not be the prompt.** Six icons in a row is 6:1. Almost no
image model generates 6:1, so it returns something squarer with the icons crushed, and
the result looks plausible enough to pass review. The honest answers are "lay them out
3×2" or "generate them one at a time", and an agent can only choose between those with
both numbers in front of it: what the board layout requires, and what the model's schema
allows. That is why `tool board` computes the layout and `gen image` reconciles rather
than trusting whatever `--size` was typed.

This is also what makes `--dry-run` the agent's real interface. Returning the fully
resolved call — chosen model, chosen size and how far it is from the requested one, the
template that will be used, every option after validation, the estimated cost — turns
parameter choice into something inspectable and adjustable before money moves. An agent
that can only see its inputs is guessing; an agent that can see the resolved call is
deciding.

**Normalise a small core, pass the rest through raw.** Fal documents parameters per
model, and the same idea wears different names and ranges across them — Grok Imagine
Video's `duration` is literally the "1 second loops better" knob from one transcript,
against the 4-second clip another one samples. Normalising everything would mean owning a
translation table that goes stale silently and hides options the model has. Normalising
nothing would push the per-model divergence into every skill and every prompt template.
So a handful of concepts that genuinely exist everywhere — prompt, input image, seconds,
size, seed — get stable flags that the skills and templates can rely on, and the long
tail stays raw and validated. Whether a given model's spelling of a core concept can
actually be mapped is a per-model fact, so the mapping lives in the registry beside the
schema, not in the code.

Fal is the only provider in M3 and `model-registry` should not be shaped so tightly
around it that a second one cannot fit — `budget-guard` already has to tolerate a
provider that meters by subscription rather than per call.

**The free path wins, and the expensive command is the one that has to know it.** Two
cases exist already and they have the same shape. Ask `gen expand` to widen an image
whose border is flat chroma and the honest answer is `tool expand --fill chroma`: padding
with the key colour *is* what the outpaint would have produced, so paying for it buys a
`np.pad`. Ask `gen image` for the East-facing anchor when West exists and the answer is
`tool mirror`. In both, the deterministic command is not an approximation of the paid one
— it is the same result.

The discriminator is the prompt, not an override flag. No content prompt means the caller
wants *canvas*, and canvas is free; a prompt means they want *invented content*, and that
is what a model is for. Expressing intent through the argument that already carries it
beats adding `--force`, which would make the cheap path something you opt into rather
than the default.

Putting the check inside `gen` rather than in a skill is deliberate. A rule that lives in
a skill is a rule an agent can forget under load, and the failure is silent — money spent,
correct output, nobody notices. A refusal carrying the free command as its `fix` is the
same shape as every `doctor` finding, so the harness already knows what to do with it.

**Generating a tile that tiles is generate → fix → verify, never prompt-and-pray.** No
image model reliably closes a wrap seam on request, so the tile path is three steps
that already exist: `gen image` with the tile template, `tool tile --seamless` to close
the wrap, `doctor` to measure `seam` and say whether it actually closed. That is the
same loop as every other defect in this tool, and it is why `seam` had to be a
measurement rather than a judgement.

**M4 depends on M3** — there is nothing to gate without expensive generation — and
`sprite-skills` is the last leaf of the milestone, because a skill is written about
commands that already exist. `sprite-resource` is the one skill covering the
non-animated kinds; if the judgement for a seam and the judgement for a nine-patch turn
out to have nothing in common, splitting it costs one edit.

**Video length is a per-model fact, not a project setting.** The sources disagree
head-on: one samples 8–12 frames out of a 4-second, 80–120-frame Seedance/Kling clip;
the other sets Grok Imagine to 1 second precisely because a short clip loops better.
Both are reporting honestly about different models. So `gen video` must not hard-code a
duration, and `extract --cycle` has to return a loop score — the decision is empirical
per model, and the score is what makes it decidable rather than a matter of taste.

**`budget-guard` cannot assume per-call pricing.** Two sources note that Codex ships
image generation inside an existing subscription with no API key, against Fal's
per-call metering. The provider interface therefore reports cost as *unknown or zero*
without that meaning free, and `budget.max_usd` has to tolerate a provider that never
increments it. Designing the counter around Fal alone is the mistake to avoid, and it
is cheap to avoid now and expensive later.

**`pixelart` (M1) and `style` (M4) are not the same thing.** `tool pixelart` converts
*one image or one set*, with the parameters passed in the call, and it is the answer
to art that arrives with no direction at all. `tool style` applies the *project's
decision* — the locked `palette.json` — and is where cross-asset coherence lives. The
second uses the first's core; the boundary is who decided the palette.

**`sprite-animation` replaces `sprite-walkcycle` and `sprite-animate`.** The design
document had both, split by input origin (a finished sheet vs a video). Generalising
walkcycle to animation in general makes the two overlap: the judgement is identical —
how many frames per action, what is redundant, where the cycle closes, what loops and
what is one-shot. One skill, two entry paths. If the trigger turns out to be genuinely
different in practice, splitting again costs one edit.

**The competitor's own wiki settled four things.** Their tool documentation is more
useful than their marketing, and reading it changed four decisions rather than confirming
them. Their chroma key has a **Global/Flood** mode, which is the failure our plan would
have shipped: matching every pixel of the key colour eats a green gem inside the
character, and only a flood from the border avoids it. Their atlas export has
**transparency padding**, which is the classic GPU-sampling bleed at entry boundaries and
was missing from `atlas-packing`. Their sprite tool **auto-detects grid, frame size,
margin and spacing** on an imported sheet, which our `cut` could not do — it had to be
told, and a sheet of unknown origin is precisely the M1 promise. And their animation model
has **ping-pong, reverse and named sections within one sheet**, which is how an attack's
windup/hit/recovery actually ships and which our index could not express.

**Hitboxes are carried, never invented — and that is what keeps `ssc` out of the
engine.** Damage and knockback are game balance; a tool that guessed them would be wrong
in a way nobody could correct systematically. What `ssc` can honestly own is the geometry
and the bookkeeping: the alpha bounding box per frame is free and exact, the authored
boxes live in a sidecar, and the frame count is validated so that curating one frame away
cannot silently shift every marker after it. That last part is the actual value — hand-
authored per-frame data going stale against a re-cut sheet is the failure this prevents,
and it is invisible until something hits the wrong pixel in play.

**3D → 2D was considered and left out.** Rendering a model from N angles is the
deterministic answer to cross-direction consistency that this whole plan works around with
anchors, mirroring and a consistency embedding. It is also a different product: it needs a
renderer, a scene format and rigged input, and the user who has a rigged 3D model is not
the user who has one AI image. Kept out on that basis, not on merit.

**Their tileset tool has no autotile either.** No Wang tiles, no bitmask variants, no
terrain transitions in a paid, shipping product. That is not proof the deferral was right,
but it does mean leaving it out is not a gap against the market — and it is a data point
about cost that a single-line roadmap item would not have given.

**Seamless generation is not guaranteed, and they say so in their own docs.** Their
answer to verification is a 2×2 tiled preview with a grid overlay — a human looking at
four copies. That is the same loop as ours with the roles reversed: `doctor.seam`
measures, `preview` shows. Keeping both is deliberate; the measurement is what an agent
acts on, the picture is what a person trusts.

**Paid prior art, and what it teaches.**
[True Pixel](https://sorceress.games/pages/true-pixel) (US$49, the Sorceress suite)
covers the same path — frame extraction, chroma, palette conversion, sheets for
Godot/Unity/GameMaker — which confirms the product shape. What it has and the design
document did not: temporal smoothing against flicker, a shared palette across frames,
and classic presets beyond pico8/nes. All three are folded in above. What stays ours is
agent-operability: JSON output, exit codes, a `doctor` that names the fix, and state on
disk instead of a GUI.

**CPU or GPU is a runtime concern, not a flag on one command.** Only the model-based
paths have the choice at all — chroma removal is numpy and will never be anything else —
but both M6 leaves have it, so it belongs to neither. Two things make it more than a
flag. It is a **packaging** decision: `onnxruntime` and `onnxruntime-gpu` are different
distributions, which is why the extras split into `[cv]` and `[cv-gpu]` rather than one
extra with a switch. And it may be a **cache** decision: if CUDA and CPU produce
bit-different masks — they do, through different kernels and precision — then the
execution provider has to be part of the content-addressed key, or a hit computed on a
GPU is silently not reproducible on a laptop. `cv-runtime` lands before the two leaves
that consume it, and `ssc info` exists so a failing machine can be diagnosed without
guessing which provider was actually used.

**Detecting the GPU must not require the GPU runtime.** The obvious implementation asks
`onnxruntime` which providers it has, which answers "CPU only" on exactly the machine
the hint is for — a box with a real GPU and the `[cv]` extra installed. So detection
reads the hardware directly (nvidia-smi, DXGI on Windows, Metal on macOS) and compares
it against the providers the installed runtime offers; the hint is the difference
between those two lists. Two disciplines keep it from becoming noise: it is emitted once
per run, never once per file, because a 200-frame batch would print it 200 times; and it
travels as a field in the JSON with the install command in it, so a harness can act on
it and a human can ignore it. A hint nobody can act on is an advert, and a hint printed
every frame is worse than none.

**Seams that are deliberately in no leaf.** There is no migration and no backfill:
nothing prior is in production. What has to keep working is M1 on its own — no API key,
no `[cv]` — and every later milestone is additive. That is a requirement of
`workspace-foundation` and is what `cv-background-removal` has to degrade cleanly
around.

**Turning it off if it goes wrong** is always `git checkout` of a new file: no command
mutates its input, so there is no state to revert outside `jobs/` and the budget
counter — both in ignored directories.
