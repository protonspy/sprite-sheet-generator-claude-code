---
lang: en
---

# Skill coverage — design

## What changes, and where

Three directories under `src/ssc/data/skills/`, each holding one `SKILL.md`, and two tests
under `tests/`. No module changes: `skills.shipped()` already enumerates the payload
directory and `ssc init` writes what it finds, so a skill is data all the way through
(R1.5). The four existing texts are edited in place.

```
src/ssc/data/skills/sprite-background/SKILL.md   new — the layered kind
src/ssc/data/skills/sprite-still/SKILL.md        new — banner and map
src/ssc/data/skills/sprite-boxart/SKILL.md       new — the concept piece
tests/cli/test_skills.py                         coverage: a kind no skill names
tests/test_shipped_texts.py                      resolution: a command that does not exist
```

## Three skills for four kinds

`banner` and `map` are one run and not two. Both are a single unanimated full-colour
image: generate against the kind's template, quantize to the project's palette, let the
`palette` check measure it, pack into the `bin` atlas their profiles declare, index.
Nothing in either run reads the other's cell size — `256×64` against `128×128` is a number
the profile carries, not a stage. Shipping `sprite-banner` and `sprite-map` would put two
texts in the payload that differ in their title and nowhere else, and the second one to be
edited is the one that goes stale. R1.3 exists for this case.

`background` does not join them, and the reason is `layered=True`: its run splits one
generation into parallax layers and indexes them as a set with a scroll factor each.
That is a stage the other two do not have and cannot be told to skip.

`box-art` does not join them either. It is the only kind that is not a game asset — it is
the brief a person approves, `checks=()` because no check `doctor` ships measures a
painterly illustration, and it is never packed. Its run ends at a gate, and what follows
is a derivation (`tool pixelart`) rather than a stage of its own.

**The alternative was one skill per kind, and the alternative to that was one skill for all
four.** One per kind repeats a text (above). One for all four buys a skill whose
description has to claim four different runs, which is the field an agent reads to decide
whether the skill applies at all — and the failure of a too-broad description is silent:
the agent picks it and follows the wrong half.

## Naming

`sprite-still` is the run, not a kind: an asset that does not animate, is not cut out on
chroma, and packs whole. The term goes in `docs/glossary.md` because the alternative
names for it — flat art, plate, still image — are three names for one concept and this
project has hit that drift before.

## The two checkers

Both live where their corpus already is: coverage next to the payload tests in
`tests/cli/test_skills.py`, resolution next to the endpoint scan in
`tests/test_shipped_texts.py`, which already walks every `SKILL.md` and every harness doc.

**Coverage (R1.4)** — for every profile in `kinds.BUILT_IN`, assert its name appears as a
whole word in some shipped skill's `description`. The description rather than the body,
because that field *is* the routing surface: a kind named only in the body is a kind an
agent never reaches.

Claimed means one of two forms — the kind backticked, or `--kind <name>` — which is how
every description already names its own: `` `icon` `` and `--kind character` are both
there today. Plain prose does not count, and that is the point rather than pedantry:
`sprite-icons` says "background removal" in its description, and a whole-word match would
read that as a claim to drive the `background` kind and report the gap closed.

**Resolution (R3.2)** — walk the Click tree from `ssc.cli.app.main` once into a set of
command paths and, per path, its option names. Then, for every backticked token in a
shipped skill that starts with `ssc `, take the leading words up to the first placeholder
or flag, resolve that path, and resolve every `--flag` in the token against that command's
parameters.

The failure mode to design against is a checker that matches nothing and passes: a regex
that silently stops finding commands reports a clean audit forever. So the test asserts a
floor — a shipped skill names commands, and the corpus as a whole resolves more than a
handful — and that floor is what makes the task TDD rather than Unit.

## The audit

Run the resolution checker at RED against the four existing texts and correct what it
names. Then read each against the surfaces that landed after it was written — `--style` on
a generation, more than one reference, `tool crop`, the gate in front of a paid step,
`ssc clip` — and name the ones that change that kind's run (R3.3). A stage that is still
right is left alone: this is an audit, not a rewrite.

## Where a skill stops

Every new text carries the rule the existing four carry: at a gate the skill reports and
stops (R3.4). It matters most in `sprite-boxart`, whose whole purpose is the approval —
a skill that approved its own brief would have removed the only human step on the path.
