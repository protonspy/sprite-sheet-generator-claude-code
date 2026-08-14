---
autonomy: auto
ci: wait
lang: en
---

# Reference images — requirements

## Purpose

A generation can be anchored to art that already exists, and `ssc` carries exactly one such
image: `--ref` takes a path, `--from-stage` takes a stage, and naming both is refused. The
payload has always modelled an array — `src/ssc/cli/gen.py` puts a list in the image field
where the model declares one — so the limit is the command surface rather than the
provider. Two references at once is the ordinary case and not the exotic one: an anchor plus
a checkerboard is how every direction after the first is generated, and the anchor template
already says *any image supplied alongside this prompt* is a board, which stops being true
the moment there are two. This is for the caller who has more than one thing to point at,
and for the harness generating a direction from an anchor it approved an hour ago.

## R1 · More than one reference

- **R1.1** The `ssc` CLI shall accept more than one reference on `ssc gen image`, given as any mixture of `--ref` and `--from-stage`.
- **R1.2** The `ssc` CLI shall send the references in the order they were given.
- **R1.3** If the chosen model takes a single image and more than one reference was given, then the `ssc` CLI shall refuse the call and say how many it was given.
- **R1.4** The `ssc` CLI shall cover every reference it sent in the key it caches the result under.
- **R1.5** The `ssc` CLI shall record each reference it sent by digest, name and size rather than by its bytes.
- **R1.6** If more references are given than one call carries, then the `ssc` CLI shall refuse before reading any of them.
- **R1.7** If a reference is larger than the ceiling a file is read at, then the `ssc` CLI shall refuse the call.

## R2 · What each reference is for

- **R2.1** Where a reference is given as `<path>:<role>`, the `ssc` CLI shall say in the prompt what that image is for.
- **R2.2** The `ssc` CLI shall accept the roles `identity`, `palette`, `pose` and `board`, and shall refuse any other.
- **R2.3** Where more than one reference carries a role, the `ssc` CLI shall name them in the order the images are sent.
- **R2.4** The `ssc` CLI shall report every reference it sent and the role each was given.

## R3 · The board a style names

- **R3.1** Where `--board` is given, the `ssc` CLI shall generate the board the resolved style names and send it as a reference in the role `board`.
- **R3.2** If `--board` is given and the resolved style names no board, then the `ssc` CLI shall refuse the call.
- **R3.3** The `ssc` CLI shall send a generated board after every reference the caller named.
- **R3.4** If the size asked for would draw a board past the side `ssc` bounds a board to, then the `ssc` CLI shall refuse the call.

## R4 · Where a reference must not go

- **R4.1** The `ssc` CLI shall offer no way to attach a board, or a second reference, to a video call.

## Out of scope

**Choosing which reference wins.** When two references disagree — an anchor in one palette
and a palette swatch in another — the model decides. `ssc` says what each image is for and
carries them in order; it does not weight them, and no model in the registry takes a
weight.

**A reference on `gen expand` or `gen bgremove`.** Both take the image they transform, which
is the subject and not a reference to derive from. One image is the whole of what they mean.

**Fetching a reference from a URL.** `--ref` names a file on disk and `--from-stage` names a
file in the asset. Anything else is a download, and downloading is not what a generation
command is for.
