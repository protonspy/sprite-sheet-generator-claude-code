# Model pricing — tasks

Existing tests that cover the paths this work changes, run before anything is written:
`tests/test_model_registry_fallback.py` (every `core.json` field pinned against that
endpoint's own properties), `tests/cli/test_models.py` (registry load, option checking,
defaults), `tests/cli/test_model_commands.py` (`model list` / `model show` output shape).

## 1 · The refresh

- [x] 1.1 (Unit) Write `scripts/fetch_model_schemas.py`: read each endpoint's OpenAPI document and the provider's model listing without credentials, and write `models.json` — R3.1, R3.2, R3.5
- [x] 1.2 (Unit) Stamp each price with its fetch date, and keep an entry whose document failed to fetch, reporting it and exiting non-zero — R3.3, R3.4

## 2 · The catalogue

- [x] 2.1 (Unit) Refresh `models.json` through the script: the three video models added, and a `price` object on every entry — R1.1, R2.1
- [x] 2.2 (Unit) Map the core concepts for the three added models in `core.json`, `null` where the model has no such concept, leaving both defaults where they are — R1.2, R1.3

## 3 · Reading the price

- [x] 3.1 (Unit) Carry the price on `Model`, as the provider's text and its fetch date, `null` where there is none and never absent — R2.1, R2.4, R2.5
  _Depends 2.1_
- [x] 3.2 (Unit) `ssc model show` reports the price text, its date, and the sentence saying it is indicative and `ssc budget` is what a run cost; `ssc model list` reports whether each model has one — R2.2, R2.3, R2.6
  _Depends 3.1_

## 4 · Choosing, in the shipped text

- [x] 4.1 (Unit) Give each agent's root instruction file a "Choosing a model" section: the default per media, `ssc model list` / `ssc model show` for the rest and their prices, and which options move what a call costs — R4.1, R4.2
  _Depends 3.2_
- [x] 4.2 (Unit) Name in each `sprite-*` skill the model and options its generating steps reach for, and what to set at each end of the property that scales the work — R4.3, R4.4
  _Depends 4.1_
- [x] 4.3 (Unit) Pin every endpoint named in a shipped text against the registry — R4.5
  _Depends 4.2_

## Notes

Group 1 precedes group 2 because the script is what writes the catalogue: hand-editing
`models.json` and writing the script afterwards would leave the two disagreeing on the
first refresh, which is the drift `core.json`'s own note warns about.
