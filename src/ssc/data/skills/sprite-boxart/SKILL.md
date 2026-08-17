---
name: sprite-boxart
description: The flow for a concept piece — the painterly brief a person approves before any sprite derives from it. Use it when a generation has no reference to anchor it, which is every first asset of a character or a set, and the work is a `box-art` asset: `asset new --kind box-art`, `gen boxart`, the gate a person answers, and `tool pixelart` deriving the sprite source from what they approved. Not a game asset and never packed or indexed — the sheet that follows is `sprite-sheet`, and an asset that already has a reference skips this run entirely.
---

You own the run for a concept piece: the roster or character-select illustration
a person approves, and the derivation that turns it into the source a sprite run
starts from. `box-art` is **the one kind that is not a game asset**. It is
painterly, it sits at `1024x1536` — a size no cell ever is — it is never packed
and it is never indexed. It exists because a character's art has to be generated
somewhere, and the alternative was a second command that bills.

**When this run happens, and when it does not.** A generation with no reference
has nothing anchoring it, so it stops here first: the concept piece is approved,
and everything after derives from it. A generation that *has* a reference does
not do this — you are already anchored, and a concept piece would be a paid call
that decides nothing.

## Stages you run, in order

Run through the workspace's `pipeline:` where one is declared, so `ssc run`
records each stage and a killed session resumes from disk rather than from
memory.

**Stage 1 — the brief.** `asset new <key> --kind box-art` creates the asset.
`gen boxart --prompt "the character, in a sentence"` produces the piece. **There
is no `--style` on this call, and that is deliberate**: the brief is not drawn in
the deliverable's style. Its template names painterly, never pixel art, because
a pixel-art brief approved at `1024x1536` tells you nothing about what the sprite
will look like at `64x64` — it tells you what a large picture of small squares
looks like.

  *The paid call, and what to set on it.* The default image model,
  `openai/gpt-image-2`. This is the one stage where `--count` is the point rather
  than an economy: ask for several at `--quality medium`, put them in front of a
  person, and generate the chosen direction once more at `--quality high` if it
  needs the finish. Everything downstream derives from this image, so it is the
  cheapest place in the pipeline to be wrong and the most expensive one to be
  wrong *late*. `ssc model show openai/gpt-image-2` names the options and the
  price text.

**Stage 2 — the gate.** `ssc gate open --topic box-art --question "which of these
is the character" --material <the images>` puts the choice in front of a person,
and `ssc gate list` shows what is waiting. A person answers with `ssc gate
approve` — or `ssc gate reject --why "what is wrong with it"`, which sends you
back to Stage 1 with something to change. **You do not answer this gate.**

`box-art` declares no checks, and that is not an oversight: every check `doctor`
ships measures a property of a pixel-art sprite — real pixels on a grid, a
bounded palette, a clean cut-out — and none of them applies to a painterly
illustration. So nothing here measures whether this is the right character. A
person does, at this gate, once.

**Stage 3 — the derivation.** The approved image becomes the sprite source
through `tool pixelart --palette palette.json`, not through a second generation.
Generating again would produce a different character wearing the same
description — the whole point of approving one image is that what follows is
*that* image, reduced. `--colors` and `--min-cluster` control how hard the
reduction is, and `--outline` adds one where the art needs to read at cell size.

**Stage 4 — hand over.** You hand over the approved piece and the derived source,
and the run that packages a game asset takes over: `sprite-sheet` for a
character, `sprite-icons` for a set of icons. **Do not run `ssc index` for a
`box-art` asset.** It is a brief, not something an engine loads.

## What you hand over

The approved illustration, the record of the gate that approved it, and the
pixel-art source derived from it. No atlas, no sheet, no index entry.
