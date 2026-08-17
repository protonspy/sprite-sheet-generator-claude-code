# Skill coverage — tasks

**What already covers these paths:** `tests/cli/test_skills.py` covers the payload, the
frontmatter every skill carries and what `ssc init` writes; `tests/test_shipped_texts.py`
covers every shipped Markdown against the model registry and the cost levers;
`tests/cli/test_harness.py` covers the three instruction files against the CLI they
describe. All three were run green before this work started — 57 passed.

## 1 · The checkers, before the texts they check

- [x] 1.1 (TDD) Fail the suite when a built-in kind is named by no shipped skill's description — R1.1, R1.2, R1.4
- [x] 1.2 (TDD) Resolve every command and option a shipped skill names against the Click tree, and fail on one that does not exist — R3.1, R3.2

## 2 · The three new skills

- [x] 2.1 (Unit) Ship `sprite-background` — one generation into parallax layers, and the index that carries their scroll — R2.1, R1.2, R3.3, R3.4
  _Depends 1.1, 1.2_
- [x] 2.2 (Unit) Ship `sprite-still`, driving `banner` and `map` through the palette to the atlas — R2.2, R1.3, R2.5
  _Depends 1.1, 1.2_
- [x] 2.3 (Unit) Ship `sprite-boxart` — the brief, the gate a person answers, and the pixel art derived from what they approved — R2.3, R2.4, R3.4
  _Depends 1.1, 1.2_
- [x] 2.4 (Unit) Hold `ssc init` to laying the three out with no change to the installer — R1.5
  _Depends 2.1, 2.2, 2.3_

## 3 · The audit of the four that exist

- [x] 3.1 (Unit) Correct in the four existing skills what the resolution checker names — R3.1
  _Depends 1.2_
  _Priority 1_
- [x] 3.2 (Unit) Name in each existing skill the surfaces that landed after it was written — R3.3
  _Depends 3.1_
- [x] 3.3 (Unit) Settle `still` in the glossary and record the two new runs in the wiki — R1.3, R2.1, R2.2, R2.3
  _Depends 2.1, 2.2, 2.3_
