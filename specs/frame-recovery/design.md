# Frame recovery — design

## What changes

Serves R1.2, R1.8, R2.1, R3.1, R3.2, R3.3, R3.4.

- **`core/recover.py`** — pure: the three detectors, the grid detection, and the filters.
  Takes an `ndarray` and a params dataclass, returns a list of rectangles. It returns
  **rectangles, not images**, which is what lets the grid detector be tested against an 8×8
  array and what keeps the two bindings from each cropping their own way.
- **`core/curate.py`** — the redundancy measure, also pure.
- **`cli/commands/recover.py`** — `tool cut`, `tool slice` and `tool curate`. A new module
  rather than a fifth, sixth and seventh command in `convert.py`: these three write *into a
  workspace* when there is one, which is a different shape from the four that only ever take
  `--in`/`--out`, and that is the boundary `convert.py`'s own docstring says to split on.

## The two bindings

`cut` and `slice` are the same detector with different output bindings, and the difference
is entirely in what gets written:

| | `cut` | `slice` |
|---|---|---|
| result | one asset, N frames | N assets, one image each |
| on disk | `frames/001.png …` under the asset | `assets/<kind>/<key>-01/` … |
| lineage | every frame derives from the sheet | every asset's first file derives from the sheet |

Keeping them one leaf keeps the three detection modes in one place. Splitting them by
binding would have produced the same detector twice, and the second copy is the one that
drifts.

## Detecting a grid

R1.2 is the requirement that makes a sheet of unknown origin usable, and the plan put it
here rather than in `sheet-doctor` on purpose: `doctor`'s `check_bleed` takes the grid as a
parameter and says so in a comment, precisely so that two detectors could not disagree.
This is the one that detects.

The method is projection profiles. Sum the alpha (or the not-key mask) along each axis; a
run of zero-valued columns is a gutter between cells, and a run of non-zero is a cell. From
those runs come the margin, the cell size and the spacing, and the count follows. It handles
both of R2.2's cases because a sheet with no spacing is the same measurement with
zero-length gutters — the cell boundaries then come from the regular pitch of the content
runs rather than from the gaps.

**It reports the grid it can see, which is not always the grid somebody drew** — and
writing the test first is what surfaced that. A sprite does not fill its cell to the edge, so
a sheet of 10px cells with 4px gutters and a 1px inset presents as runs of 8 separated by
gaps of 6. Nothing in the image distinguishes that from 8px cells with 6px gutters: the cell
boundary is simply not observable where no content touches it. So the report is the
observable one — cells tight around the content, spacing being the gap actually measured —
which is self-consistent, tiles back to the image, and is what `cut` needs anyway, since
cropping to it yields the sprite rather than the sprite plus its padding.

R2.2's two cases collapse into that one measurement: cells that abut differ from cells that
are spaced only in how wide the gaps are, and a sheet with no gaps at all in either axis is
one solid block, which is not a layout and is refused.

This is a detector, so it can be wrong, and R1.3 is what that costs: it refuses and names
the flag rather than guessing a layout and cutting a sheet into nonsense. **Silently
returning a plausible wrong grid is the failure mode to design against** — every frame after
it would be off by a few pixels, and nothing downstream would notice. That is why regularity
is checked rather than assumed (R2.4): three blobs at unrelated positions are not a 3x1
sheet, and calling them one would cut somebody's illustration into thirds.

## Writing into a workspace, or not

R3.3 and R3.4 are one decision: these commands are useful both ways, and which one applies
is discovered rather than flagged. Inside a workspace they record provenance the way every
other writer does; outside one they write plain files, exactly as `snap` and `pixelart`
already do. A `--no-record` flag would be a second way to say something the filesystem
already says.

## Risks

**`slice` invents keys.** N assets need N keys, and they come from the source key plus an
index. A collision with an asset that already exists has to refuse rather than merge, which
is `workspace-foundation`'s R2.3 and comes for free by going through the same path `asset
new` does.
