# ssc — sprite-sheet-generator-claude-code

Turn AI-generated art into game-ready 2D assets: real pixels on a real grid, aligned
frames, a transparent background, and metadata an engine can read.

Image and video models produce art that looks finished and is not usable. The defects are
systematic rather than accidental — fake pixels, frame bleeding, drift, halos, palette
drift, flicker, visible tiling seams — so each one can be **measured** rather than judged.
`ssc` is the set of primitives that measures them and repairs them, one command at a time.

> **Status: implemented.** Install it with `pip install sprite-sheet-generator-claude-code`
> (or `uv tool install .`), run `ssc init` in a project, and drive the pipeline. `ssc init`
> also lays out the seven skills that drive a run per kind, for the coding agent you name.
> The deterministic core, every asset kind and the paid generation path are in
> [`plans/archive/ssc-pipeline.md`](plans/archive/ssc-pipeline.md); what an engine reads,
> the harness and the model-backed commands are in
> [`plans/ssc-completion.md`](plans/ssc-completion.md); and the reasoning behind all of it
> is in [`docs/wiki/`](docs/wiki/index.md).

## Principles

- **Primitives, not a pipeline.** Each command does one thing; the harness composes them.
- **The verb carries the price.** `tool` is local, free and synchronous. `gen` means the
  provider does it and charges for it. You can tell what burns credit without reading
  flags.
- **Nothing is destructive.** Every command writes a new file; nothing mutates its input.
- **All output is JSON.** A caller reads structure, never screen text.
- **Lineage lives on disk.** Every artefact records where it came from, so the workspace
  is reconstructible without any conversation context.
- **Measure, don't guess.** `ssc tool doctor` reports defects as numbers, and each finding
  carries the command that fixes it.

## Credits

Pixel snapping: [spritefusion-pixel-snapper](https://github.com/Hugo-Dz/spritefusion-pixel-snapper)
by Hugo Duprez, MIT. Vendored as a WASI module; its `LICENSE` ships alongside it.

## Licence

See [LICENSE](LICENSE).
