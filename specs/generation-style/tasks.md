# Generation style — tasks

**What already covers these paths:** `tests/cli/test_gen_commands.py` covers `prompt_for`,
the template a kind names, the `--var` slots and the refusal for a slot nobody filled;
`tests/cli/test_kinds.py` covers a profile's fields, the `ssc.yaml` override and where each
field came from; `tests/test_shipped_texts.py` covers the shipped Markdown. All three were
run green before this work started.

## 1 · The styles the package ships

- [x] 1.1 (Unit) Ship `styles.json` and resolve a name or free text into the wording a prompt carries — R1.2, R1.3, R1.4
- [x] 1.2 (Unit) Report the style applied, whether it is shipped, and the board it names — R1.5, R1.6
  _Depends 1.1_
- [x] 1.3 (Unit) Hold a style to a phrase, on the flag and in `ssc.yaml` alike — R1.7
  _Depends 1.1_

## 2 · The templates

- [x] 2.1 (Unit) Give the image templates a `{style}` slot and move their drawing wording into `pixel-art` — R2.1, R2.2
  _Depends 1.1_
- [x] 2.2 (Unit) Refuse `--style` where the template names no style slot — R2.3
  _Depends 2.1_
- [x] 2.3 (Unit) Take the asserted look out of the video templates, which animate whatever the input already is — R2.1

## 3 · Whose decision the look is

- [x] 3.1 (Unit) A kind profile carries the style, declarable in `ssc.yaml`, defaulting to `pixel-art` — R3.1, R3.2, R3.3
- [x] 3.2 (Unit) `ssc gen image --style`, resolved per call and overriding what the kind names — R1.1
  _Depends 1.1, 2.1, 3.1_
- [x] 3.3 (Unit) Say in the wiki and in the shipped skill that the look is a choice now — R2.1, R3.3
  _Depends 3.2_
