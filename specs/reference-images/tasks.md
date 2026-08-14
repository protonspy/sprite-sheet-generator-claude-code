# Reference images — tasks

**What already covers these paths:** `tests/cli/test_gen_commands.py` covers the reference a
call carries today — `--ref` and `--from-stage`, the refusal for naming both, the move to the
editing endpoint, the elided record and the cache key; `tests/cli/test_styles.py` covers the
style a call resolves and the board it names; `tests/cli/test_convert.py` covers
`tool board checker`. All three were run green before this work started.

## 1 · More than one reference

- [x] 1.1 (Unit) Carry references as a list through the ask, the call and the payload, in the order given — R1.1, R1.2
- [x] 1.2 (Unit) Refuse a second reference to a model whose image field holds one — R1.3
  _Depends 1.1_
- [x] 1.3 (Unit) Cover every reference in the cache key, and record each by digest rather than by its bytes — R1.4, R1.5
  _Depends 1.1_
- [x] 1.4 (Unit) Bound how many references a call carries and how large each may be — R1.6, R1.7
  _Depends 1.1_

## 2 · What each reference is for

- [x] 2.1 (Unit) Read `<path>:<role>`, refusing a role nobody defined — R2.2
- [x] 2.2 (Unit) Say in the prompt what each image is for, in the order they are sent — R2.1, R2.3
  _Depends 1.1, 2.1_
- [x] 2.3 (Unit) Report every reference sent and the role it was given — R2.4
  _Depends 1.1, 2.1_

## 3 · The board a style names

- [x] 3.1 (Unit) `--board` generates the board the style names and sends it after the rest — R3.1, R3.3
  _Depends 2.2_
- [x] 3.2 (Unit) Refuse `--board` where the resolved style names none — R3.2
  _Depends 3.1_
- [x] 3.3 (Unit) Hold a generated board to the side `tool board checker` holds one to — R3.4
  _Depends 3.1_

## 4 · Where a reference must not go

- [x] 4.1 (Unit) No board and no second reference on a video call — R4.1
  _Depends 3.1_
