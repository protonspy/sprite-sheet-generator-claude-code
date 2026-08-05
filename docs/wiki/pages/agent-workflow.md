# The agent workflow

Every page before this one explains a step. This one explains the run: how an agent goes
from nothing to `dist/index.json` without a person typing a command, and where the run
stops because a decision is a person's to make. The six skills under `.claude/skills/`
are the vehicle — each owns a leg of the relay, names the commands it runs, stops at its
gate, and says what it hands to the next.

They are shipped inside the package and written out by `ssc init`, beside `ssc.yaml` and
`assets/`. A game project installs `ssc` and has the relay; it does not copy files out of
this repository, which is what would leave a project driving a version's commands with
another version's skills. `ssc init --no-skills` lays out the workspace without them, and
a skill a project has already edited is kept rather than overwritten.

The commands themselves prove the relay holds: `tests/cli/test_chain.py` drives the whole
chain on one fixture, and goes red when any leg's contract with the next drifts.

## The relay

Two skills start a run, depending on what the asset is. The other four are the same relay
for everything that animates.

| Skill | Owns | Hands over |
|---|---|---|
| `sprite-character` | the anchor image: `gen image` against the kind's template, `tool bgremove`, the neutral-pose discipline of [[anchor-and-directions]] | one approved anchor image, keyed and recorded |
| `sprite-resource` | the kinds that do not animate — tile, icon, ui: generation against the kind's profile, `tool tile` for wrap, `tool ninepatch` for stretch borders | approved sources, ready for style |
| `sprite-animation` | poses and cycles: `tool board`, `gen image` for pose sheets, `gen video` for walk cycles, `tool cut`, `tool curate` — see [[generating-animations]] | a curated frame set per animation |
| `sprite-cleanup` | the repairs of [[frame-normalisation]]: `tool snap`, `tool align`, and `tool doctor` to measure the result | frames that pass `doctor`, or a named defect it cannot repair |
| `sprite-style` | the project's look: `tool style` against the locked `palette.json`, the workspace's dither decision, `tool recolour` for variants | frames quantized against the one palette |
| `sprite-integrate` | the handover of [[into-an-engine]]: `ssc index`, then `ssc preview` on what the index declares | `dist/index.json`, and the preview a person approves |

A skill runs its commands through the workspace's `pipeline:` where one is declared, so
`ssc run` records each stage and a killed session resumes from disk rather than from
memory. What a skill never does is decide at a gate.

## Where the gates fall

A gate is a decision reserved for a human, held as state in the workspace — a pending one
is exit code `3` and a `review/` directory, never a question asked in conversation. The
run stops at four, and only these:

1. **The anchor image**, at the end of `sprite-character`. Every direction and every
   animation derives from this one image, so a wrong one is every later paid call wasted.
   The cheapest moment to reject it is before anything derives from it.
2. **The curated frame set**, at the end of `sprite-animation`. The paid calls have
   happened by now; what is being judged is whether the motion reads, which no `doctor`
   check can measure.
3. **The palette lock**, once per project, inside `sprite-style`. A palette is a project
   decision recorded in `palette.json`, not a per-call argument — locking it is the
   decision, and every asset after it inherits the choice silently.
4. **The preview**, at the end of `sprite-integrate`. `ssc preview` renders from `dist/`,
   so what is being approved is exactly what an engine will load.

Everything between gates is measurable, and the skills act on measurements: a `doctor`
defect names its fix, a budget refusal names the free command that answers the same
question, a pending job is collected rather than resubmitted.

## What the handover is made of

The relay works because each leg's output is a recorded stage, not a loose file. A skill
finds its input by stage in `meta.json`, never by filename; authored intent — playback,
sections, markers, hitboxes and hurtboxes — travels in the sidecar; and the index at the
end reads both. A skill that wrote a file without recording its stage would break the leg
after it, which is the drift `tests/cli/test_chain.py` exists to catch.
