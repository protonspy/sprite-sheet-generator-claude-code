# Frame preview — design

## What changes

Serves R1.1 to R1.4, R2.1 to R2.4, R3.1 to R3.3.

One `tool` command, `src/ssc/cli/commands/preview.py`, over the composition that already
lives in `src/ssc/core/preview.py` (`order`, `contact`) and the encoder in
`src/ssc/cli/preview.py` (`animated_gif`). Nothing here composes frames into a GIF or a
contact sheet itself — that is the point of R3.2: `ssc preview` and `tool preview` share one
renderer, and this command is the lower of the two, taking frames straight off disk rather
than out of `dist/index.json`.

```
src/ssc/core/preview.py        add frames_from_sheet — cut a sheet by its grid, pure
src/ssc/cli/commands/preview.py   the `tool preview` command: --in, --out, --fps, --mode,
                              --cell/--cols/--rows, --contact
```

`frames_from_sheet` is the pure mirror of the index reader's `cut_sheet`, for a caller that
has the grid from `--cell`/`--cols`/`--rows` rather than from `index.json`. It checks the
grid against the image before a single frame is cut, the same bound `cut_sheet` uses, so a
grid the picture cannot hold is refused once and not frame by frame. It is in `core/` because
it is array arithmetic, and because `specs/asset-listing/` calls the same cut without a CLI.

## Boundaries and contracts

`--in` follows the shape every other `tool` command's `--in` does: one image, or a directory
read as a frame set ordered by filename (`cli.frames.read_frames`). A single image with
`--cell` is a sheet; a single image without `--cell` is a one-frame set. That one flag is the
sole disambiguator, so a sheet previewed without its grid is reported as a one-frame set
rather than guessed at — the grid is what `tool bounds` measures and what `ssc index` writes,
and inventing it here would give the project three places that decide it.

`--out` is a file, written through `cli.frames.write_one` like every generated image, so the
no-overwrite contract holds. The suffix is the caller's: a GIF for the animation, a PNG for
`--contact`.

## Risks

- **A sheet previewed without its grid reads as one frame.** This is the deliberate side of
  the one-flag disambiguator above, and it is why the refusal in R1.3 is on a *partially*
  given grid rather than on an absent one: a grid nobody named is a one-frame set, a grid
  half-named is a usage error.