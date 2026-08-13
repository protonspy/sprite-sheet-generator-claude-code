# The agent workflow

Every page before this one explains a step. This one explains the run: how an agent goes
from nothing to `dist/index.json` without a person typing a command, and where the run
stops because a decision is a person's to make. The skills under `.claude/skills/`
are the vehicle — four per-type skills (`sprite-sheet`, `sprite-icons`,
`sprite-tilemap`, `sprite-ui`) each drive a whole run for one kind of creation, name the
commands in order, stop at their gates, and hand over `dist/index.json`.

They are shipped inside the package and written out by `ssc init`, beside `ssc.yaml` and
`assets/`. A game project installs `ssc` and has the runs; it does not copy files out of
this repository, which is what would leave a project driving a version's commands with
another version's skills. `ssc init --no-skills` lays out the workspace without them, and
a skill a project has already edited is kept rather than overwritten.

Each skill is self-contained — it names the commands and the rules directly, and does not
open this wiki. The wiki is how the workflow was designed, not something a skill reads at
run time. The commands themselves prove the runs hold: `tests/cli/test_chain.py` drives a
whole chain on one fixture, and goes red when a skill's contract with the commands drifts.

## The four runs

One per kind of creation. The first stage distinguishes them; the middle stages are the
same shared work measured by the same `doctor` checks; the handover is a sheet, an atlas
or a tileset depending on the profile.

| Skill | Owns | Ends at |
|---|---|---|
| `sprite-sheet` | an animated sprite's whole sheet — anchor, poses and cycles, cleanup, style, `ssc index` | one **sheet** per asset: equal cells, grid, fps, loop, anchor |
| `sprite-icons` | a set of icons, source then style then index | one **atlas** per `icon` kind, a rect and an anchor per asset |
| `sprite-tilemap` | a tile set that wraps — `tool tile` closes the seam, then style then index | one **tileset** per `tile` kind, equal cells with an id per tile |
| `sprite-ui` | a UI/HUD panel — `tool ninepatch` reports the guides, `tool doctor` measures `nineslice`, then style, index | one **atlas** per `ui` kind with the four stretch borders per entry |

A skill runs its commands through the workspace's `pipeline:` where one is declared, so
`ssc run` records each stage and a killed session resumes from disk rather than from
memory. What a skill never does is decide at a gate.

## Where the gates fall

A gate is a decision reserved for a human, held as state in the workspace — a pending one
is exit code `3` and a `review/` directory, never a question asked in conversation. The
run stops at four, and only these:

1. **The anchor image**, inside `sprite-sheet`, before any direction is generated. Every
   direction and every animation derives from this one image, so a wrong one is every
   later paid call wasted.
2. **The curated frame set**, inside `sprite-sheet`, after the pose sheets are cut. The
   paid calls have happened by now; what is being judged is whether the motion reads,
   which no `doctor` check can measure.
3. **The palette lock**, once per project, before anything is quantized. A palette is a
   project decision recorded in `palette.json`, not a per-call argument — locking it is
   the decision, and every asset after it inherits the choice silently.
4. **The preview**, at the end of every run. `ssc preview` renders from `dist/`, so what
   is being approved is exactly what an engine will load.

The first two gates belong to motion and fall only in `sprite-sheet`; the last two every
run stops at. Everything between gates is measurable, and the skills act on measurements:
a `doctor` defect names its fix, a budget refusal names the free command that answers the
same question, a pending job is collected rather than resubmitted.

## What the handover is made of

The runs work because each stage's output is recorded, not a loose file. A skill finds
its input by stage in `meta.json`, never by filename; authored intent — playback,
sections, markers, hitboxes and hurtboxes — travels in the sidecar; and the index at the
end reads both. A skill that wrote a file without recording its stage would break its own
handover, which is the drift `tests/cli/test_chain.py` exists to catch.