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

## References

- `specs/frame-bounds/` — `ssc tool bounds`, the measurement every later step reads: per
  frame, the alpha bounding box, the visible height and width, the baseline row and the
  centre column; per set, each of those as a median with its spread. It writes no image and
  needs no workspace. It exists as its own leaf because three separate things want the same
  number — the normaliser, the `scale` check, and `specs/frame-metadata/`, whose per-frame
  box this is — and three private implementations of "where is the sprite in this frame"
  would be free to disagree.
- `specs/set-normalisation/` — `ssc tool normalise`, which takes the frame sets of one asset
  and returns them sharing one baseline, one centre column and one visible-height scale, on
  one canvas. It owns the scale decision and the cross-set anchor; it delegates padding to
  `tool expand` and layout to `tool pack` rather than reimplementing either. It carries the
  `scale` check into `doctor` as a delta against `specs/sheet-doctor/` — the variation in
  visible height across the sets of one asset, as a number, with `tool normalise` as its
  fix.
- `specs/frame-preview/` — `ssc tool preview`, an animated GIF and a contact sheet from a
  frame set, or from a sheet plus its cell: fps, loop mode, and each frame labelled with its
  index on the contact sheet. No workspace, no index. It carries the delta
  `specs/engine-index/` then owes: its `ssc preview` resolves an asset and its playback out
  of `dist/index.json` and renders through this, rather than growing a second renderer.

## Tasks

- [ ] 1.1 (Unit) Settle in `docs/glossary.md` the vocabulary the three leaves inherit —
      **visible height** (the height of a frame's alpha bounding box, never the canvas
      height), **baseline** (the canvas row a set's feet land on, which is the anchor's row
      once `align` has run and the thing that has to agree between two animations),
      **centre column**, **frame set** and **scale** as the name of the defect — each with
      the synonyms to avoid, before any requirement is written against them
- [ ] 2.1 (Unit) Write `docs/wiki/sprite-normalisation-gate.md` once the three leaves have
      landed: the six steps as one ordered sequence with the exact command and flags at
      each, what `doctor` reports between them, and which failure mode each step is there to
      catch — reachable from `index.md`, recorded in `changelog.md`

## Done when

The three leaves have shipped: `ssc tool bounds` reports each frame's box and each set's medians, `ssc tool normalise` puts the sets of one asset on one baseline, one centre and one scale, and `ssc tool preview` renders a GIF and a contact sheet. `doctor` carries the `scale` check with `normalise` as its fix, the vocabulary is settled in `docs/glossary.md`, and the six-step gate is written down in `docs/wiki/`.
