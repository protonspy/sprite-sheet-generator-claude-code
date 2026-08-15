# Box art — design

## What changes

Serves R1.1, R1.2, R1.3, R1.4, R1.5, R2.1, R2.2, R3.1.

One command, one field on the ask, and one refusal in the reference reader.

`ssc gen boxart` in `src/ssc/cli/commands/gen.py` is the pipeline with three defaults set
and three options absent. It fixes `template="box-art"` (R1.2) and `stage="boxart"`, and it
offers no `--ref`, no `--from-stage`, no `--board` and no `--style` — which is how R2.1 and
R1.4 are met: not by a check, but by there being nothing to pass. The same argument
`docs/wiki/reference-boards.md` makes for `gen video` carrying no board.

`Ask.cell` is new: the cell the prompt's `{width}` and `{height}` are filled from, where
that is not the asset's own. `build` reads `ask.cell or profile.cell`. Box art is the one
call whose size has nothing to do with the asset's cell — a character's cell is 64x64 and
its concept piece is a 1024x1536 portrait — and the number comes from the `box-art` kind's
profile rather than from a constant here, so a project that redeclares that kind moves both
(R1.3).

R1.4 needs no code at all. The `box-art` template names no `{style}` slot, so a style has
nowhere to land; the style spec already refuses `--style` against a template with no slot,
and this command does not offer the flag. The test asserts the property rather than a branch.

**R3.1 is the one new check**, and it runs on both routes a stage reaches a call by:
`references_for`, which is `gen image`'s, and `source_image`, which is the subject case the
other three share. It refuses a stage whose provenance says `gen boxart` produced it.

**Which of those three it runs for is the whole of R3.2.** `gen video` passes
`into_a_sprite=True`: a clip is frames, and frames at box art's fidelity are the same
unusable frames an anchor drawn from it would be. `gen expand` and `gen bgremove` pass
nothing: widening the concept piece and cutting the character out of it both produce box
art, which is a roster image somebody may legitimately want, and refusing them would block
real work to prevent nothing. The line is not *which command* but *what comes out* — a
sprite, or another concept piece. Against the provenance rather than the stage name, because
`--stage` renames the stage and the record is what remembers where a file came from. This
enforces what `docs/wiki/box-art-and-style.md` describes as a rule nobody enforces: box art
passed to the anchor comes back at box art's fidelity, richly shaded and finely detailed,
and the detail cannot survive the trip down to a cell — it arrives as noise
`tool normalise` then has to fight. The refusal names `tool pixelart`, which is what that
image is for.

R2.2 is `meta.record`'s existing refusal for a stage an asset already holds, reached by
fixing the stage name. Nothing new; named here because it is a requirement somebody will
look for.

## Boundaries and contracts

The recorded stage is `boxart`, `source` class like every generated file, and the result
carries a `derive` field naming the command that turns it into a sprite (R1.5). No schema
moves: a stage name and a result field are both open.

## Alternatives considered

**`gen image --box-art`, a flag on the command that already exists.** Rejected. The flag
would have to disable `--ref`, `--from-stage`, `--board` and `--style` and override the
template and the cell — six behaviours conditional on one flag, which is a second command
wearing a disguise. `tool board`'s two subcommands were split for the same reason.

**Refusing box art on a kind that is not a character.** Rejected as over-fitting: a kind is
a profile and not an enum, and a check that reads `kind == "character"` is exactly what
`adr:0008` says not to write.

## Risks

**The refusal in R3.1 is the whole enforcement, and it only sees a stage this tool
recorded.** A caller who copies the file out of the asset and passes it with `--ref` gets
no refusal, because
nothing then connects those bytes to the record that says where they came from. That is
the honest limit of enforcing this at the command surface, and it is worth having anyway:
the path it does close is the one an agent takes.
