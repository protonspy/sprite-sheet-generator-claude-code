---
autonomy: auto
ci: wait
---

# Asset listing — requirements

## Purpose

An agent driving `ssc` cannot glob. It has to ask what exists before it can decide what to
do, and the honest answer has to come from a command with a JSON contract rather than from
a caller reconstructing paths out of a layout it has memorised. `workspace-foundation`
recorded a stage, a class and a lineage for every file; this leaf is the two commands that
read that record back — `list`, which answers *what is here*, and `show`, which answers
*where is the file at this stage, what produced it, and is it any good*.

The nouns are `image` and `video` because generation has exactly two modalities and
everything `ssc` writes is one or the other: a frame is an image, a sheet is an image, an
atlas is an image.

## R1 · Which medium a file is

- **R1.1** The `ssc` CLI shall classify a recorded file as an image or a video from its filename extension.
- **R1.2** If a recorded file's extension names neither medium, then the `ssc` CLI shall omit it from both listings and report it as unclassified.

## R2 · Listing

- **R2.1** When `ssc image list` runs, the `ssc` CLI shall report every image recorded by an asset in the workspace, with each file's key, kind, stage, class and path.
- **R2.2** When `ssc video list` runs, the `ssc` CLI shall report every recorded video in the same form.
- **R2.3** Where a kind is given, the `ssc` CLI shall report only files belonging to assets of that kind.
- **R2.4** Where `--stage` is given, the `ssc` CLI shall report only files carrying that stage.
- **R2.5** Where `--class` is given, the `ssc` CLI shall report only files of that class.
- **R2.6** The `ssc` CLI shall order a listing by kind, then key, then position in the asset's chain.
- **R2.7** When no recorded file matches, the `ssc` CLI shall report an empty listing and exit `0`.

## R3 · Showing one file

- **R3.1** When `ssc image show <key>` or `ssc video show <key>` runs, the `ssc` CLI shall report the file at the requested stage together with its stage, class, path, and the command and parameters that produced it.
- **R3.2** The `ssc` CLI shall accept an asset as `<kind>/<key>` or as a bare `<key>`.
- **R3.3** If a bare key names an asset in more than one kind, then the `ssc` CLI shall exit `2` and name the kinds it matched.
- **R3.4** Where `--stage` is not given, the `ssc` CLI shall report the last file of that medium in the asset's chain.
- **R3.5** If the asset records no file of that medium at the requested stage, then the `ssc` CLI shall exit `2` and report the stages of that medium it does record.
- **R3.6** When it reports a file, the `ssc` CLI shall report that file's lineage: every file it was derived from, transitively, ordered from the root of the chain.
- **R3.7** If a recorded file reaches itself through its own lineage, then the `ssc` CLI shall exit `1` and name the file the cycle closes on.
- **R3.8** Where the reported file is an image, the `ssc` CLI shall include a `doctor` report measured on it.
- **R3.9** If the reported file is not an image, then the `ssc` CLI shall report no `doctor` and shall say why.
- **R3.10** Where `--no-doctor` is given, the `ssc` CLI shall report the file without measuring it.

## Out of scope

- **What a kind means.** A kind filters a listing as a name and nothing more. The profile
  behind it — cell, anchor mode, applicable checks — is `specs/asset-kinds/`.
- **`doctor`'s parameters.** `show` measures what can be measured with no arguments; a
  check needing a cell, a palette or a grid reports itself skipped, which is
  `sheet-doctor`'s own contract and not a gap here. A caller who wants those runs
  `ssc tool doctor` with them.
- **Listing anything but assets.** `jobs/`, `review/` and `dist/` are listed by the leaves
  that create them.
