# Model options — tasks

## 1 · The four endpoints

- [x] 1.1 (Unit) Add the four endpoint schemas to `data/models.json`, copied from Fal's document — R1.1, R1.2, R1.3, R1.4
- [x] 1.2 (Unit) Map the four endpoints in `data/core.json`, recording seed as absent — R1.1, R1.2, R1.3, R1.4, R1.8
  _Depends 1.1_
- [x] 1.3 (Unit) Record the package defaults in `core.json` and consult them last in `Registry.chosen` — R1.5, R1.6
  _Depends 1.2_
- [x] 1.4 (Unit) Report the default model for each media in `ssc model list` — R1.7
  _Depends 1.3_
- [x] 1.5 (Unit) Pin the four endpoints and their shapes in the fallback registry test — R1.1, R1.2, R1.3, R1.4
  _Depends 1.2_

## 2 · A size in pixels

- [x] 2.1 (Unit) Record the pixel size shape and its bounds for both GPT Image 2 endpoints — R2.1
  _Depends 1.2_
- [x] 2.2 (Unit) Accept a mapping for a field whose schema offers an object branch — R2.2
- [x] 2.3 (TDD) Fit a requested size to the pixel bounds, or refuse the ratio — R2.3, R2.5
  _Depends 2.1_
- [x] 2.4 (Unit) Send the fitted size as width and height, and report both sizes — R2.2, R2.4
  _Depends 2.2, 2.3_

## 3 · Options with names

- [x] 3.1 (Unit) Add `count`, `quality` and `format` to the core concepts and to every model's mapping — R3.1
  _Depends 1.2_
- [x] 3.2 (Unit) Take `--count`, `--quality` and `--format` on the commands whose models have them — R3.2, R3.5
  _Depends 3.1_
- [x] 3.3 (TDD) Refuse a count outside the range the model offers — R3.4
  _Depends 3.2_
- [x] 3.4 (Unit) Refuse a named option the chosen model does not have — R3.3
  _Depends 3.2_
- [x] 3.5 (Unit) Report each core option's field and accepted values in `ssc model show` — R3.6
  _Depends 3.1_

## 4 · Defaults on a kind

- [x] 4.1 (Unit) Carry default options on a kind profile and report them in `ssc kind show` — R4.1, R4.4
- [x] 4.2 (Unit) Fill the core options a caller did not name from the kind — R4.1, R4.3
  _Depends 3.2, 4.1_
- [x] 4.3 (Unit) Skip a kind default the chosen model lacks, and report it as skipped — R4.2
  _Depends 4.2_

## 5 · Every image a call produced

- [x] 5.1 (Unit) Return every file URL a result carries from `fal.file_urls` — R5.1
- [x] 5.2 (TDD) Write every file of one call as its own `source` stage, and report them — R5.1, R5.2, R5.4
  _Depends 5.1_
- [x] 5.3 (Unit) Cache a set of files behind one call key — R5.3
  _Depends 5.2_

## 6 · The record

- [x] 6.1 (Unit) Record the transcribed pixel bounds as an ADR — R2.1
  _Depends 2.1_
- [x] 6.2 (Unit) Update the wiki for the six image models, the pixel size and the named options — R1.1, R2.1, R3.1
  _Depends 2.4, 3.2_
