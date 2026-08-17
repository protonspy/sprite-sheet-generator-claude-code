---
autonomy: auto
ci: wait
lang: en
---

# Clip sampling — requirements

## Purpose

`gen video` submits the call and `ssc video` lists what came back, and then the chain stops:
nothing takes a clip apart. A walk cycle arrives as four seconds and a hundred frames, and a
sheet needs eight to twelve spanning exactly one cycle — so the step between them is done by
hand today, or not at all. This is the part of the reference workflow with no surface. It
reads the clip, finds where the motion closes back on itself, and samples across that,
leaving a frame set `tool normalise` and `tool pack` treat like any other.

## R1 · Taking a clip apart

- **R1.1** When `ssc tool clip` runs, the `ssc` CLI shall read the frames of a clip and write the sampled ones as a frame set.
- **R1.2** The `ssc` CLI shall report how many frames the clip holds and the rate it plays at.
- **R1.3** If the clip cannot be read, then the `ssc` CLI shall refuse and name the file.
- **R1.4** If the clip holds more frames than will be decoded, then the `ssc` CLI shall refuse rather than decode part of it.
- **R1.5** If a clip's frames are larger than will be held, then the `ssc` CLI shall refuse, whether the container said so or not.

## R2 · Where the cycle closes

- **R2.1** The `ssc` CLI shall find the frame at which the motion returns to where it started, and shall report which frame that is.
- **R2.2** The `ssc` CLI shall not look for a cycle shorter than a cycle can be.
- **R2.3** Where no frame returns close enough to the first, the `ssc` CLI shall report that it found none and sample the whole clip.
- **R2.4** Where the whole clip is asked for, the `ssc` CLI shall sample across it without looking for a cycle.

## R3 · Sampling across it

- **R3.1** The `ssc` CLI shall write the number of frames it was asked for, evenly spaced across the range it sampled.
- **R3.2** The `ssc` CLI shall not write both ends of a cycle, because a sheet holding the closing frame and the opening frame stutters where it should loop.
- **R3.3** Where a range in seconds is given, the `ssc` CLI shall sample only inside it.
- **R3.4** If more frames are asked for than the range holds, then the `ssc` CLI shall refuse.
- **R3.5** If a range is given as something other than a finite number of seconds, then the `ssc` CLI shall refuse.

## R4 · Where the frames land

- **R4.1** The `ssc` CLI shall require exactly one of `--asset <kind>/<key>` and `--out <path>`.
- **R4.2** Where `--asset` is given, the `ssc` CLI shall record the frames as one stage, with what it sampled among that stage's parameters.

## Out of scope

**Judging the motion.** Whether a walk cycle reads is a gate — `specs/gates-and-resume/`
already puts one after the curated frame set, and no measurement decides it.

**Audio, colour management, and every other thing a video holds.** A clip here is a
sequence of frames and a frame rate. Anything else in the container is dropped, which is
what a sprite pipeline wants.

**Re-timing.** The frames come out at the positions they were sampled from; nothing is
interpolated, and nothing is resampled — this project's only resampler is nearest neighbour
and inventing intermediate frames is not what it is for.
