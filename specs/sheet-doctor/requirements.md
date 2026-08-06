---
autonomy: auto
ci: wait
---

# Sheet doctor — requirements

## Purpose

`ssc tool doctor` measures the defects in a finished asset and names the command that
repairs each one. It exists before the tools it measures because that is "measure, don't
guess" applied to this repo: without it, every later leaf would be judged by eye. It is
also what closes the loop for an agent — a number and a fix are actionable, a judgement
about whether something "looks right" is not.

## R1 · What doctor measures

- **R1.1** (MODIFIED) The `ssc` CLI shall measure `pixel_grid`, `bleed`, `drift`, `halo`, `palette`, `flicker`, `silhouette`, `consistency` and `scale` on every input, and `seam` or `nineslice` where either was asked for — see `specs/tile-assets/` and `specs/ui-assets/`, which own those checks. `consistency` arrives with the motion-consistency leaf (plan task 10.2) as a delta against this spec; `scale` arrives with the normalisation gate (plan task 4.3) the same way.
- **R1.2** The `ssc` CLI shall report every check as a number rather than as a judgement.
- **R1.3** Where a check does not apply to the input it was given, the `ssc` CLI shall report that check as skipped, with the reason.
- **R1.4** The `ssc` CLI shall name, on every defect it reports, the command that repairs it.
- **R1.5** The `ssc` CLI shall report each finding's severity as `defect` or `warning`.

## R2 · The checks

- **R2.1** The `ssc` CLI shall measure `pixel_grid` as the detected pixel size and the share of pixels differing from their own cell's dominant colour.
- **R2.2** The `ssc` CLI shall measure `bleed` as the number of cells whose content touches a boundary shared with a neighbouring cell.
- **R2.3** The `ssc` CLI shall measure `drift` as the largest distance, in pixels, between a frame's anchor and the median anchor of the set.
- **R2.4** The `ssc` CLI shall measure `halo` as the count of pixels whose alpha is neither 0 nor 255.
- **R2.5** The `ssc` CLI shall measure `palette` as the count of distinct opaque colours, the count of pixels outside a given palette, and whether that count exceeds a given colour budget.
- **R2.6** The `ssc` CLI shall measure `flicker` as the count of pixels changing colour between adjacent frames by no more than a stated distance while their alpha is unchanged.
- **R2.7** The `ssc` CLI shall measure `silhouette` on the alpha mask reduced to the target cell, as the count of enclosed background regions and the count of separate opaque regions.
- **R2.8** (ADDED) The `ssc` CLI shall measure `seam` as the difference across each wrap boundary against the same difference between the image's own neighbouring lines, per axis.
- **R2.9** (ADDED) The `ssc` CLI shall measure `nineslice` as the largest variation within a stretched region along the axis that region stretches on.
- **R2.10** (ADDED) The `ssc` CLI shall measure `consistency` as the mean cosine similarity across the per-frame shape embeddings of the set, reduced to a low-resolution silhouette, and shall report it as a number, judging it only where a minimum similarity was given.
- **R2.11** (ADDED) The `ssc` CLI shall measure `scale` as the variation in visible height across the sets of one asset — the range of the per-set median visible heights — and shall report it as a number, naming `ssc tool normalise` as its fix where the variation exceeds a stated tolerance.

## R3 · Running it

- **R3.1** (MODIFIED) The `ssc` CLI shall accept `--in` naming one image or a directory of frames, and shall run it without a workspace. The first `--in` is the set the checks run on; `--in` may be repeated to name the other sets of one asset, which the cross-set `scale` check compares, and which no other check reads.
- **R3.2** Where the input is a sheet, the `ssc` CLI shall take its grid from `--cols` and `--rows`.
- **R3.3** Where a check needs a target cell or a palette and neither is given, the `ssc` CLI shall skip that check rather than assume one.
- **R3.4** The `ssc` CLI shall exit `0` once it has measured the input, whether or not it found defects.
- **R3.5** If `--in` names neither an image nor a directory holding one, then the `ssc` CLI shall exit `1`.
- **R3.6** Where a sheet carries no alpha, the `ssc` CLI shall take the background for `bleed` from a given chroma colour.
- **R3.7** The `ssc` CLI shall refuse an input above a stated pixel ceiling, and a target cell outside a stated range, before decoding or measuring it.

## R4 · Proving the detectors

- **R4.1** The `ssc` CLI shall be validated against fixtures whose defects are known and measured.
- **R4.2** The `ssc` CLI shall have, for each of the seven checks, one fixture carrying that defect and one free of it.

## Out of scope

- **`seam` and `nineslice`.** They arrive with the tile and UI kinds, as deltas against
  this spec rather than as a second detector.
- **Broken cycles.** A loop that does not close is a property of where frames were sampled
  from a clip, not of the artefact on disk, so it is measured by the loop score
  `extract --cycle` returns and never by `doctor`.
- **Repairing anything.** Every check names its fix and runs none of them. `doctor` reads.
- **Reading an asset by key.** `ssc image show <key> --stage nobg` returning a file's
  `doctor` is `specs/asset-listing/`; what this leaf owes it is a callable measurement.
