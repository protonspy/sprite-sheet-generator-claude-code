---
autonomy: auto
ci: wait
lang: en
---

# Skill coverage — requirements

## Purpose

Eight kinds carry a profile and four carry a skill. An agent asked for a background, a
banner, a world map or a piece of box art has the root instruction file and nothing else:
it composes the run from scratch every time, and the commands it does not think of — the
parallax split, the palette quantize, the gate in front of a paid call — are the ones a
skill exists to remember. The four skills that do exist were written before `tool crop`,
`gen image --style`, a second reference, the box-art gate and `ssc clip` landed, and
nothing has ever checked their text against the CLI. This closes both halves: every
built-in kind is driven by a skill, and every command a skill names is a command that
runs.

## R1 · Every built-in kind is driven

- **R1.1** The `ssc` CLI shall ship a skill for every kind its package declares built in.
- **R1.2** The `ssc` CLI shall name, in each skill's description, the kinds that skill drives and the kinds it does not.
- **R1.3** Where two kinds are produced by the same run, the `ssc` CLI shall let one skill drive both rather than shipping a skill that repeats another.
- **R1.4** If a built-in kind is added that no shipped skill names, then the `ssc` test suite shall fail.
- **R1.5** The `ssc` CLI shall install a skill added to the package without any change to the installer.

## R2 · What the new skills drive

- **R2.1** The `ssc` CLI shall ship a skill that takes a `background` asset from generation through its parallax layers to `ssc index`.
- **R2.2** The `ssc` CLI shall ship a skill that takes a `banner` or a `map` asset from generation through the palette its project declares to the atlas `ssc index` writes.
- **R2.3** The `ssc` CLI shall ship a skill that takes a `box-art` asset from the brief to the image a person approved.
- **R2.4** The `ssc` CLI shall state, in the box-art skill, that the pixel art of an approved piece is derived by `ssc tool pixelart` rather than generated a second time.
- **R2.5** Where a kind declares no check that a skill's stage measures, the `ssc` CLI shall say in that skill which stage carries the judgement instead.

## R3 · The text answers to the CLI

- **R3.1** The `ssc` CLI shall name, in a shipped skill, only commands and options that resolve under `ssc --help`.
- **R3.2** If a shipped skill names a command or an option that does not resolve, then the `ssc` test suite shall fail.
- **R3.3** The `ssc` CLI shall name, in each shipped skill, the surfaces that changed the run its kind takes — the style a generation is drawn in, the references a call carries, the crop that frames a result, and the gate that stands in front of a paid step.
- **R3.4** When a shipped skill reaches a stage where a person decides, the `ssc` CLI shall send the agent at `ssc gate` rather than at a judgement of its own.

## Out of scope

**How a skill is installed.** `skills.shipped()` reads the payload directory and `ssc init`
writes what it finds, so a skill added to the package is already installed. `R1.5` is a
statement that this holds, not a change to it — `specs/agent-harness/` owns the installer.

**A kind a project declares itself.** A kind is a profile and not an enum (`adr:0008`), so
a project may declare its own. Nothing ships a skill for it, and that is not a gap: the
root instruction file already sends an agent at `ssc kind list`.

**Rewriting the four existing runs.** The audit corrects what no longer resolves and names
what landed since; a skill whose stages are still right keeps them.

**Judging whether the art is good.** A skill runs commands and stops at gates. Whether a
banner reads as a banner is a person's call at `ssc gate`, and `specs/generation-gates/`
owns that surface.
