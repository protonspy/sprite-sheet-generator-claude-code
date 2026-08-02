# ssc — sprite-sheet-generator-claude-code

Turn AI-generated art into game-ready 2D assets: real pixels on a real grid, aligned
frames, a transparent background, and metadata an engine can read.

Image and video models produce art that looks finished and is not usable. The defects are
systematic rather than accidental — fake pixels, frame bleeding, drift, halos, palette
drift, flicker, visible tiling seams — so each one can be **measured** rather than judged.
`ssc` is the set of primitives that measures them and repairs them, one command at a time.

> **Status: planning.** The decomposition is in [`plans/ssc-pipeline.md`](plans/ssc-pipeline.md);
> the reasoning behind it is in [`docs/wiki/`](docs/wiki/index.md). No implementation yet.

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
