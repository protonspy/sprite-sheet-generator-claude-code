---
autonomy: auto
ci: wait
status: draft
---

# Sprite normalisation gate

Three leaves that make an asset's animations measurable and correctable as one set — bounds, cross-set normalisation, and a preview a person can look at before an engine reads any of it.

## Why

Generated frames are not game-ready until scale, alpha, padding and anchors are stable —
and the instability that survives everything `ssc` builds today is **between the animations
of one asset**, not inside any one of them. `tool align` locks a common anchor across the
frames of a set; nothing makes idle's baseline agree with walk's, nothing makes the
character the same height in both, and nothing measures either. The failures that reach a
running game come from exactly there: the sprite grows two pixels when it starts walking,
the feet sink through the floor mid-animation, the frame size differs per action so the
engine's cell is wrong for one of them.

## Out of scope

- Per-frame hit and hurt boxes and named markers. `plans/ssc-completion.md` owns those; the
  box `tool bounds` measures is the derived one they are validated against.
- A second preview renderer. `ssc preview` resolves an asset out of `dist/index.json` and
  renders through `tool preview`; the index leaf is where that delta is written.

## Tasks

- [x] 1.1 (Unit) Settle in `docs/glossary.md` the vocabulary the three leaves inherit —
      **visible height** (the height of a frame's alpha bounding box, never the canvas
      height), **baseline** (the canvas row a set's feet land on, which is the anchor's row
      once `align` has run and the thing that has to agree between two animations),
      **centre column**, **frame set** and **scale** as the name of the defect — each with
      the synonyms to avoid, before any requirement is written against them
- [x] 2.1 (Unit) Write `docs/wiki/sprite-normalisation-gate.md` once the three leaves have
      landed: the six steps as one ordered sequence with the exact command and flags at
      each, what `doctor` reports between them, and which failure mode each step is there to
      catch — reachable from `index.md`, recorded in `changelog.md`
      _Depends 3.2, 4.3, 5.3_
- [x] 3.1 (Unit) `ssc tool bounds` reporting, per frame, the alpha bounding box, the visible
      height and width, the baseline row and the centre column — one implementation of "where
      is the sprite in this frame", since the normaliser, the `scale` check and the
      per-frame box all read the same number
      _Depends 1.1_
- [x] 3.2 (Unit) Per set, each of those measurements as a median with its spread, written to
      stdout as structured output: no image, no workspace
      _Depends 3.1_
- [x] 4.1 (TDD) The scale decision: one visible-height factor across the frame sets of one
      asset, resampled the way the project's single resampler allows — the sprite growing two
      pixels when it starts walking is the defect, and it is arithmetic nobody sees go wrong
      _Depends 3.2_
- [x] 4.2 (Unit) `ssc tool normalise` putting the sets of one asset on one baseline, one
      centre column and one canvas, delegating padding to `tool expand` and layout to
      `tool pack` rather than reimplementing either
      _Depends 4.1_
- [x] 4.3 (Unit) Carry the `scale` check into `doctor` — the variation in visible height
      across the sets of one asset, as a number, with `tool normalise` named as its fix — and
      write the matching delta into the sheet-doctor spec
      _Depends 4.2_
- [x] 5.1 (Unit) `ssc tool preview` rendering an animated GIF from a frame set, or from a
      sheet plus its cell, honouring fps and loop mode
- [x] 5.2 (Unit) The contact sheet from the same input, each frame labelled with its index
      _Depends 5.1_
- [x] 5.3 (Unit) Resolve an asset and its playback out of `dist/index.json` and render through
      this, so `ssc preview` grows no second renderer, with the matching delta written into
      the engine-index spec
      _Depends 5.2_

## Done when

The three leaves have shipped: `ssc tool bounds` reports each frame's box and each set's medians, `ssc tool normalise` puts the sets of one asset on one baseline, one centre and one scale, and `ssc tool preview` renders a GIF and a contact sheet. `doctor` carries the `scale` check with `normalise` as its fix, the vocabulary is settled in `docs/glossary.md`, and the six-step gate is written down in `docs/wiki/`.
