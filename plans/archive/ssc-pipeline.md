---
autonomy: auto
ci: wait
pr: per-group
worktree: per-group
merge: auto
status: draft
---

# ssc — the 2D sprite pipeline

Twenty-eight leaves in six milestones, taking any image to a game-ready asset with real pixels, a transparent background and metadata an engine can read. Each command repairs one systematic defect, is either deterministic or explicitly expensive, and writes a new file.

## Why

`ssc` is the set of primitives that takes any image to a game-ready asset with real
pixels, a transparent background, and metadata the engine can read — a character
spritesheet, but equally an icon atlas, a seamless tileset, a nine-slice UI panel, a
banner. Image and video models produce art that is not game-ready, and the defects are
systematic rather than accidental: fake pixel art, frame bleeding, drift, opaque
backgrounds, palette drift, flicker between frames, silhouettes that stop reading at the
size they are played at, visible tiling seams, broken cycles. Each command repairs one of those, is either deterministic or explicitly
expensive, and writes a new file — nothing ever mutates its input.

Every milestone is deliverable on its own: M1 already repairs a sheet you have today, with no API key.

## References

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
  dithering as a project decision, and palette coherence across every asset. Plus
  **`ssc tool recolour`**, which maps one palette onto another: a red slime and a blue slime
  are one asset and a colour map, not two generations. Same economics as `mirror` —
  deterministic, instant, and free where the paid path is not — so it belongs in the free
  path `budget-guard` refuses against, for the same reason `mirror` does.
- `specs/asset-derivation/` — `ssc asset new <key> --extends <parent>` and the
  `<asset>.yaml` behind it: it inherits the recipe (kind, pixel_size, palette, cell,
  frame counts, fps, the parent's anchors as a generation reference), never the pixels.
- `specs/image-transforms/` — the exact transforms nothing offers yet: mirror about either
  axis, rotation by a quarter turn, `trim` to one box across a frame set, and `offset` by a
  whole number of pixels — each moving the recorded anchor with the pixels. Written as a map
  ahead of its milestone; nothing in it is implemented.

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

- [x] 0.1 (Unit) Build spritefusion-pixel-snapper for `wasm32-wasip1` — write the thin
      wrapper crate exposing a flat ABI over `process_image`, vendor
      `vendor/pixel-snapper.wasm` alongside the upstream `LICENSE`, and prove with a
      test that `wasmtime` loads the module and snaps a fixture
- [x] 0.2 (Unit) Record the decisions already made in `docs/adr/` — Python + uv, the
      snapper vendored via WASI, generation inside v1, a job always exists — plus the
      outcome of 0.1 as its own record
- [x] 0.3 (Unit) Fill in `.claude/rules/project.md` (build, test, scoped test, lint,
      format) and `docs/stack.md` with the core dependencies, `fal-client` among them
- [x] 0.4 (Unit) Settle in `docs/glossary.md` the vocabulary all twenty-seven specs
      inherit: key, kind, stage, source, derived, output, anchor, cell, sheet, frame,
      atlas, tile, seam, nine-slice, job, gate, snap, pixelart, flicker
- [x] 0.5 (Unit) Distil the design document and the three transcripts in `docs/raw/`
      into `docs/wiki/` pages reachable from `index.md`, then delete the raw files
- [x] 0.6 (Unit) Record as an ADR that `job-store` is built on `fal-client`'s
      `submit` → `get_handle(application, request_id)` → `status`/`result`/`cancel`
      surface, and pin the client version that provides it
- [x] 0.7 (Unit) Pull the endpoint ids and parameter schemas for the four models this
      workflow names — Nano Banana 2, GPT Image 1.5, Grok Imagine Video, BiRefNet — into
      the shipped registry fallback, and confirm whether Fal exposes them machine-readably
      or they have to be transcribed
- [x] 0.8 (Unit) Stand up CI — `pyproject.toml`, the package skeleton, and a GitHub
      Actions workflow running ruff, ruff format, mypy, pytest on Linux and Windows plus
      `scc validate` on the artifacts
- [x] 0.9 (Unit) Put `asset new` behind `listing.under_assets` and call `meta.check_layout`
      from somewhere, as a delta against `workspace-foundation` — `asset new` builds its
      directory with `workspace.asset_dir` and never re-resolves it, so a linked
      `assets/<kind>/` makes it create a directory and write `meta.json` outside the
      workspace; `check_layout` is defined and called from nowhere. Both found while
      auditing `asset-listing`, both that leaf's to fix rather than this one's.
      **The escape check goes on every route, the layout check only where a caller named
      one asset.** Putting both in `under_assets` was the first attempt and the review
      killed it: `asset_dirs` scans the whole workspace, so refusing there means one stray
      directory in one asset stops `list`, `clean` and every unrelated asset — while the
      read paths beside it skip what they cannot use rather than aborting. So `addressed`
      carries the layout check for `show` and `recover`, and `under_assets` stays the
      escape gate everywhere. The review also found a **third creating route**, `tool
      slice`, with the same hole `asset new` had, and a **TOCTOU window** in both: the
      first check runs before `mkdir`, against a `<kind>/` that may not exist yet, and a
      missing component resolves to itself — so both re-check after `mkdir`, which moves
      what a race can win from a written `meta.json` to an empty directory
- [x] 0.10 (Unit) Decide what `cli/main.py` does with an exception that is not an `SscError`,
      as a delta against `workspace-foundation` — it catches `SscError` and nothing else, so
      anything unexpected leaves the command as a Python traceback rather than the one JSON
      object R4.1 promises. `pixel-art-conversion` translates its own foreign-runtime traps
      at that boundary, which closes that path and not the general one. The decision worth
      making is what a catch-all reports without swallowing the diagnosis a traceback carries.
      **Done in `asset-kinds`**: four reviews of that one leaf found four different uncaught
      exception types, each reaching the user as a traceback, so the general case stopped
      being deferrable. A catch-all reports `internal-error` as JSON on stdout *and* prints
      the traceback to stderr — the machine gains an envelope without the developer losing
      the file and the line. It covers the command and the rendering; **click's own argument
      parsing still exits before any of it runs**, so a missing argument is still plain text
      and exit 2, which would need wrapping at the group's `standalone_mode`
- [x] 0.11 (Unit) Guard the catch-all's message before `gen-fal` lands — it puts an
      exception's `str()` verbatim into structured output, and HTTP clients routinely embed
      the full URL, sometimes with a credential in the query string. Nothing leaks today
      because nothing in `src/` touches a secret; the guard has to exist before the first
      one does, not after. **The guard is at `render`, not at the catch-all** — the same
      URL reaches output through the `SscError` a leaf composes from a provider's response,
      which is the path written on purpose, and through `gen --dry-run`'s resolved call,
      which is not an error at all. Two rules, because a credential arrives two ways: by
      value, matching what the environment holds under a secret-looking name in whatever
      format it appears; and by shape, matching `api_key=…`, `Authorization: Bearer …` or
      a connection string's password for one that never passed through this process's
      environment. Recorded as `workspace-foundation` R4.6
- [x] 0.12 (Unit) Bind an asset write to the directory that was checked, as a delta against
      `workspace-foundation` — `asset new` and `tool slice` re-check with `under_assets`
      after `mkdir`, which is what moves a lost race from a written `meta.json` to an empty
      directory, but `atomic.write_new` and `atomic.replace` each call
      `parent.mkdir(parents=True, exist_ok=True)` again and open by path, so a component
      swapped in the few statements after the second check is still followed. The honest
      close is a directory handle opened once and every write made relative to it
      (`os.open(dir, O_DIRECTORY)` + `dir_fd=`), which is a change to the write helpers
      rather than to their callers. `record_frames`, which `tool cut` uses, has the same
      shape with a wider window and belongs in the same pass.
      **Done as `workspace-foundation` R3.7**, and the write helpers alone were not enough:
      a helper that opens `path.parent` binds to whatever the path resolves to *then*, which
      is the same window one statement later. The directory has to be held by the caller
      that checked it, so `listing.bound` opens it, checks it and confirms the checked path
      is the directory being held — in that order, because check-then-open leaves the gap it
      closes — and `meta.save` takes that object rather than a path, which is what makes the
      unbound write unwritable rather than merely discouraged. Four routes, not three:
      `clean` rewrites a record per asset too. It also does **not** get `addressed`'s layout
      check, because `clean` sweeps the whole workspace and refusing there over one asset's
      stray directory aborts a sweep mid-delete — the blast radius 0.9 already ruled on.
      **Windows has no `dir_fd`**: `os.supports_dir_fd` is empty and `os.open` will not open
      a directory, so the binding degrades there to an identity check before each write. It
      narrows the window rather than closing it, and turns a lost race into a refusal.
      **The security review then caught what "an asset write" left out**: `clean`'s deletes
      still went through a re-resolved path, and one of the things a record names is
      `frames/`, a directory — so the operation left unbound was `shutil.rmtree`, the widest
      blast radius in the tool, while the writes beside it were hardened. Deleting is bound
      too now, `O_NOFOLLOW` per segment on the way to a recorded path, and R3.7 says "writes
      or deletes" rather than "writes".
      **And a second review round found the whole POSIX branch was dead code.** The feature
      gate read `os.replace in os.supports_dir_fd`, and that set is built by name from the
      syscalls CPython found — `HAVE_RENAMEAT` registers `"rename"`, nothing ever registers
      `"replace"` — so the gate was unsatisfiable and every platform silently took the
      weaker Windows fallback. Nothing went red, because the machine this was written on is
      the one where `False` is the right answer. The lesson is not the typo: **a
      platform-conditional hardening needs the other platform run before the PR**, so this
      one was verified under WSL on ext4 as well as on Windows, and `_DIR_FD is True` is now
      an assertion rather than an assumption
- [x] 0.13 (Unit) Read a `meta.json` through the directory that was checked, as a delta against
      `workspace-foundation` — 0.12 bound every write and every delete, and left the reads by
      path: `meta.load`, `meta.check_layout` and `listing`'s scan all resolve the asset
      directory again, so a swap in that window feeds a foreign record into the command that
      asked for the real one. Lower stakes than a write and much wider: `load` is called from
      almost every command, so the honest version changes `meta.load`'s signature the way
      `meta.save`'s changed rather than patching the one call site `tool cut` uses. Two
      smaller findings belong in the same pass: `under_assets` proves a directory is *under*
      `assets/` and never that it is the `<kind>/<key>` the caller named, so a link aliasing
      one valid asset onto another passes every check there is; and on Windows the identity
      guard rests on `(st_dev, st_ino)`, which NTFS reports honestly and FAT32, exFAT and
      some network volumes historically do not — worth measuring before trusting.
      **Done as `workspace-foundation` R3.7 — widened from "writes or deletes" to "reads,
      writes or deletes" — plus R3.9, and `asset-listing` R4.1.** `Directory` gained `read`
      and `subdirectories` descending exactly as `delete` does, and `meta.load` takes the
      held directory the way `meta.save` does, which is what keeps the unbound read
      unwritable rather than merely discouraged. `clean`'s ordering moved with it: the record
      is loaded *through* the binding its deletes will land in, where before it decided what
      to delete from a record it could not prove came from that directory.
      **The second finding was a misnamed check, and the name is how the gap survived.**
      `under_assets` proved a directory resolved somewhere under `assets/`, which admits
      `assets/character/hero` linked to `assets/icon/coin` — it never leaves the workspace,
      so every check passed and `show character/hero` reported `icon/coin`'s record under the
      name that was asked for. The address is the caller's whole statement of which asset it
      means, so the check is now that the directory is at the `<kind>/<key>` place naming it,
      and the rename to `placed` is part of the fix. `assets/` itself may still be a link —
      it is the root both sides resolve against, so art on another disk keeps working.
      **The third was worth measuring and the measurement changed the answer.** `st_ino` is a
      property of the volume, not of the platform: FAT32, exFAT and some SMB mounts report
      `0`, which makes every directory identical to every other and turns the Windows guard
      into a comparison that always succeeds — the same shape as 0.12's dead branch, a
      hardening reporting success while doing nothing. So `bindable` is measured at open and
      refuses rather than acting under a guard it knows is inert. Conservative on purpose: a
      volume with no file index has no reparse points either, so the swap cannot be staged
      there at all; what it costs is a workspace on exFAT under Windows, what it buys is that
      the guard never lies about which case it is in.
      **And 0.12's lesson was applied rather than re-learned** — the suite was run on ext4
      under WSL as well as on Windows, with `_DIR_FD` asserted `True` there, before the PR.
      **Both reviews then found the same thing independently, and it is the pattern rather
      than the incident that is worth keeping.** "Bind the reads" was read as "bind
      `meta.load`", so `show` went on holding a descriptor for the whole command and then
      read the image it measures through `Entry.file`, a re-resolved path — the one read a
      caller of `show` actually asked about, answering with another image's `doctor` numbers
      under the asset name that was typed. Fixed here rather than deferred, because R3.7's
      widened wording would otherwise have been *believed*: `measure_or_say_why` takes the
      binding, `frames.decode_image` decodes what was read instead of reopening a path, and
      `Entry.file` is deleted rather than left as a second route to the same file. Four
      rounds now — writes, deletes, records, bytes — each binding what it had named and
      leaving the next thing looking covered, which is why R3.7 is worded as *acting on a
      file in an asset* rather than as a list of verbs that kept coming up one short.
      **The second review round then found what binding the read had itself cost**: a path
      handed to `Image.open` is parsed lazily, so the pixel ceiling refuses an oversized
      image from its header, while bytes read through a binding are in memory before
      anything can look at them — the fix for a swap had opened a way to read an arbitrarily
      large recorded file into memory. `Directory.read` now takes a `max_bytes` and reads one
      byte past it rather than trusting a `stat`, set above what a `MAX_PIXELS` image
      occupies uncompressed so the two ceilings cannot disagree about one file. And the
      cross-platform run paid for itself twice: a recorded name that is a *directory* was
      reported as `path-escapes-asset` on Windows and as an `IsADirectoryError` traceback on
      POSIX, because a directory opens fine under `O_RDONLY` there and only fails a step
      later at `fdopen` — caught by the WSL run, not by the reviews, and not by Windows

## Done when

M6 has shipped: an agent starts from a base image, generates the poses and the video, converts to real pixel art, assembles the sheet or the atlas, measures the result with `doctor`, and publishes `dist/index.json` for the engine — stopping only at the human gates, and resuming from disk after any session dies. Every milestone before it is deliverable on its own.
