# Box art — tasks

**What already covers these paths:** `tests/cli/test_gen_commands.py` covers the pipeline
every paid command shares — the template a kind names, the recorded stage, the references a
call carries and the refusal for a stage that is not there; `tests/cli/test_kinds.py` covers
the `box-art` profile and its cell. Both were run green before this work started.

## 1 · The concept piece

- [x] 1.1 (Unit) `ssc gen boxart`, on the `box-art` template whatever the asset's kind names — R1.1, R1.2
- [x] 1.2 (Unit) Fill the prompt from the `box-art` kind's cell rather than the asset's — R1.3
  _Depends 1.1_
- [x] 1.3 (Unit) No style, and no way to pass one — R1.4
  _Depends 1.1_
- [x] 1.4 (Unit) Report the command that derives the sprite from it — R1.5
  _Depends 1.1_

## 2 · Only where there is nothing to derive from

- [x] 2.1 (Unit) No reference to give, and a second piece refused — R2.1, R2.2
  _Depends 1.1_

## 3 · Where box art must not go

- [x] 3.1 (Unit) Refuse box art named as the image a sprite is generated from — R3.1
  _Depends 1.1_
- [x] 3.3 (Unit) Allow a generation that turns box art into box art — R3.2
  _Depends 3.1_
- [x] 3.2 (Unit) Say in the wiki and the shipped skill that the trap is closed now — R3.1
  _Depends 3.1_
