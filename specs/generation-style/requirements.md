---
autonomy: auto
ci: wait
lang: en
---

# Generation style — requirements

## Purpose

`ssc` generates one look. Pixel art is written into every prompt template in
`src/ssc/data/templates.json`, so a project that wants hand-painted, vector or rendered art
has no surface to ask for it — the only way to answer "how is this drawn" was to not ask
the question. This makes the look a decision: a style is named per call or carried by the
asset's kind, and the template stops saying anything about how the art is drawn. It is for
the author choosing what their game looks like, and for the harness generating on their
behalf, which cannot pick a look it has no flag for.

## R1 · The style axis

- **R1.1** When `ssc gen image` runs, the `ssc` CLI shall wrap the caller's prompt in a style, taken from `--style` where it is given and from the asset's kind where it is not.
- **R1.2** The `ssc` CLI shall ship the styles `pixel-art`, `vector`, `hand-painted`, `3d-render` and `flat`, each carrying the wording a model is sent.
- **R1.3** Where `--style` names a style the package does not ship, the `ssc` CLI shall send that text to the model unchanged.
- **R1.4** If `--style` is given as blank text, then the `ssc` CLI shall refuse the call.
- **R1.7** If a style is longer than a phrase about how the art is drawn, then the `ssc` CLI shall refuse the call, whether that style was typed on the command line or declared for a kind in `ssc.yaml`.
- **R1.5** The `ssc` CLI shall report the style it applied and whether that style is one it ships.
- **R1.6** Where a shipped style names a reference board, the `ssc` CLI shall report which board it names.

## R2 · The templates

- **R2.1** The `ssc` CLI shall take the wording that says how art is drawn from the resolved style rather than from the prompt template.
- **R2.2** The `ssc` CLI shall substitute the style into a template's `{style}` slot in the same single pass that fills every other slot.
- **R2.3** If `--style` is given and the template names no `{style}` slot, then the `ssc` CLI shall refuse the call rather than bill for a prompt the style never reached.

## R3 · Whose decision the look is

- **R3.1** The `ssc` CLI shall let a kind profile name the style its assets are generated in.
- **R3.2** Where a project declares `style` for a kind in `ssc.yaml`, the `ssc` CLI shall generate that kind's assets in it.
- **R3.3** Where nothing names a style, the `ssc` CLI shall use `pixel-art`, so a workspace generates what it generated before this feature existed.

## Out of scope

**Sending a style's attachment.** `pixel-art` is words plus the checkerboard, and this leaf
records which board a style names without putting it in the payload. Carrying more than one
reference on a call is `specs/reference-images/`, and that is where the board starts being
sent.

**Box art.** Its template deliberately names the look it needs — painterly, never pixel art
— because the brief is not drawn in the deliverable's style. It names no style slot, and
under R2.3 that is a refusal rather than a silent no-op. `specs/box-art/` owns it.

**Judging whether the style came out right.** `doctor` measures defects against a kind's
checks. "Does this read as hand-painted" is a question for a person, which is what
`specs/generation-gates/` is for.

**A style on `gen video`.** A video animates an image that already exists, so the look was
decided when that image was generated. The video templates stop *asserting* a look here;
they do not gain a flag to choose one.
