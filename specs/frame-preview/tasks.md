# Frame preview — tasks

**What already covers these paths:** `tests/core/test_preview.py` covers `core.preview`
(`order`, `contact`, `tiled`) and `tests/cli/test_preview_command.py` covers the GIF encoder
and `ssc preview` — both run before and after this work, and the encoder tests are what R3.2
is argued against: this command adds no encoder, so they stay green unchanged.

## 1 · The renderer the command shares

- [x] 1.1 (Unit) Cut a sheet into frames by its grid in `core.preview`, pure — R1.2, R1.4

## 2 · The command

- [x] 2.1 (Unit) `ssc tool preview` rendering an animated GIF from a frame set at `--fps` in `--mode` — R1.1, R2.1, R2.2, R2.3, R2.4, R3.1, R3.2
  _Reason plan task 5.1 ships the GIF; this task reaches the same requirement set so the spec's traceability holds_
- [x] 2.2 (Unit) `--contact` rendering a labelled contact sheet to `--out` — R3.3
  _Reason plan task 5.2 ships the contact sheet; this task reaches R3.3 so the spec's traceability holds_
- [x] 2.3 (Unit) Cut a sheet by `--cell`/`--cols`/`--rows` into frames, refusing a partial or ill-fitting grid — R1.2, R1.3, R1.4
  _Reason plan task 5.1 ships the sheet path; this task reaches R1.2-R1.4 so the spec's traceability holds_

## 3 · The index path renders through this

- [x] 3.1 (Unit) Resolve an asset and its playback out of `dist/index.json` and render through `tool preview`'s renderer, with the matching delta written into the engine-index spec — R3.2
  _Reason plan task 5.3 ships the index reuse; this task reaches R3.2 so the spec's traceability holds_
  _Depends 2.1_