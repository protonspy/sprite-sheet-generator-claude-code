# Generating animations

There are two ways to get animation frames out of a model, and the choice is not a
preference — each one fails at what the other does.

## Image generation, for idle and attack

Pass the snapped anchor plus a pose board (see [[reference-boards]]) and describe the
sequence frame by frame. This works well for animations where the body stays roughly
put: idle, attack, hurt, jump, death.

Frame counts that hold up in practice:

| Action | Frames |
|---|---|
| Idle | ~10 |
| Attack | ~8 |
| Hurt | ~6 |
| Jump | ~6 |
| Death | ~10 |

Two things are always true of the result. The figures are **not** centred in their cells,
so the sheet cannot be cut on the grid lines — see [[frame-normalisation]]. And not every
frame earns its place: four frames of a blink with nothing else moving are three frames
of waste.

## Video generation, for walk cycles

Image generation never produces a usable walk cycle. No amount of prompting keeps the
arms and legs alternating correctly — they scramble, and the failure is consistent enough
across models to treat as a property rather than bad luck.

What works is image-to-video: pass the direction's anchor, prompt for the character
*walking or running in place*, forbid leaving the frame. Then sample a full cycle out of
the result — left leg forward, right leg forward, back to the start — and keep 8 to 12
frames spread across it.

**Never pass a board to a video model.** It merges the grid into the character. See
[[reference-boards]].

## Clip length is a per-model fact

The sources contradict each other, and both are right about different models. One
generates 4 seconds at 80–120 frames from Seedance or Kling and samples a cycle out of
it. Another sets Grok Imagine to 1 second precisely because a short clip loops better.

So there is no correct duration to write down — there is a parameter whose good value
differs per model, and a loop score to decide it empirically. This is one of the reasons
model options are validated against a per-model schema rather than normalised into a
single house style.

## Sections, not separate sheets

An attack is a windup, a hit and a recovery. Those are ranges of one animation, and an
engine wants to play them separately — hold the windup while a button is held, fire the
hit once, let the recovery cancel. Splitting them into three sheets loses the fact that
they are one continuous motion; naming ranges inside one animation keeps it.
