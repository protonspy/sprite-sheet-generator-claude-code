# Clip sampling — tasks

**What already covers these paths:** `tests/core/test_curate.py` covers the frame-difference
measure this leaf deliberately does *not* reuse — running it first is what showed why, since
it counts differing pixels rather than measuring how far apart two frames are;
`tests/cli/test_crop_command.py` and
`tests/cli/test_recover_commands.py` cover the `--in`/`--out`/`--asset` shape this joins,
including the recorded stage; `tests/cli/test_media.py` covers what the workspace calls a
video. All three were run green before this work started.

## 1 · Where the cycle closes

- [x] 1.1 (TDD) Find the frame at which the motion returns to its first, or report none — R2.1, R2.2, R2.3
- [x] 1.2 (TDD) Take N positions across a range, excluding its end — R3.1, R3.2

## 2 · Reading the clip

- [x] 2.1 (Unit) Decode a clip into frames and report its count and rate, refusing one too long to hold — R1.2, R1.3, R1.4
- [x] 2.2 (Unit) Bound the pixels as well as the frames, against the header and against what arrives — R1.5
  _Depends 2.1_
- [x] 2.3 (Unit) Read a header field that is not a number as none — R1.2
  _Depends 2.1_

## 3 · The command

- [x] 3.1 (Unit) `ssc tool clip` over a clip, writing the sampled frames — R1.1, R4.1
  _Depends 1.1, 1.2, 2.1_
- [x] 3.2 (Unit) Sample the whole clip where that is what was asked for — R2.4
  _Depends 3.1_
- [x] 3.3 (Unit) Sample inside a range in seconds, refusing more frames than it holds — R3.3, R3.4
  _Depends 3.1_
- [x] 3.5 (Unit) Refuse a range that is not a finite number of seconds — R3.5
  _Depends 3.3_
- [x] 3.4 (Unit) Record the frames as one stage, with what was sampled — R4.2
  _Depends 3.1_

## 4 · Saying it exists

- [x] 4.1 (Unit) Say in the wiki and the shipped skill how a clip becomes a frame set — R1.1
  _Depends 3.1_
