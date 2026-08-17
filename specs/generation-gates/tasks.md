# Generation gates — tasks

**What already covers these paths:** `tests/cli/test_pipeline.py` covers `declared` and the
refusal a paid step currently gets; `tests/cli/test_run_commands.py` covers the run loop, the
gate that opens after a step and the inherited default; `tests/cli/test_gates.py` and
`tests/cli/test_gate_commands.py` cover the store and `ssc gate list`; `tests/cli/test_budget.py`
covers the reservation. All were run green before this work started.

## 1 · A paid step, declared

- [x] 1.1 (Unit) A registry of the `gen` verbs a step may name, and the parameters each takes — R2.1, R2.3
- [x] 1.2 (Unit) Read a paid step, refusing one that declares no gate — R1.2
  _Depends 1.1_
- [x] 1.3 (Unit) Send the stage a step names as the call's reference — R2.2
  _Depends 1.1_

## 2 · The gate in front of the money

- [x] 2.1 (Unit) Open the gate before the call, carrying the model and the estimate — R1.3, R1.4
  _Depends 1.2_
- [x] 2.2 (Unit) Submit once it is approved, and record what came back — R1.1, R1.5
  _Depends 2.1_
- [x] 2.3 (Unit) Stop with nothing submitted where it is rejected, or where the budget refuses — R1.6, R3.1, R3.2
  _Depends 2.1_
- [x] 2.4 (Unit) Report the resolved call on a dry run, submitting nothing — R2.4
  _Depends 2.1_
- [x] 2.5 (Unit) Bind the approval to the call it was shown, and ask again where the call has changed — R1.7, R1.8
  _Depends 2.2_

## 3 · Standing approvals

- [x] 3.1 (Unit) `ssc gate list` reports the topics with a standing approval and where each came from — R4.1, R4.2
- [x] 3.2 (Unit) Honour a standing approval only where the gate it came from is here and approved — R4.3
  _Depends 3.1_

## 4 · The delta the decision owes

- [x] 4.1 (Unit) Fold `specs/gates-and-resume/` R4.9 from a refusal into a condition, and say so in the wiki — R1.1, R1.2
  _Depends 2.2_

## Notes

**2.1 was annotated TDD and was not built that way.** The risk is real — it is the task that
decides whether money is spent before a person is asked — but the code landed before the
test, and a red was never observed, so claiming the cycle would be false. It is marked
`(Unit)` for what actually happened. What the tests do assert is the property the annotation
was for: `api.submitted == []` after the first run, after a second run while the gate is
pending, and after a rejection. **This is the task in this leaf worth a human glance**, per
`.claude/rules/autonomy.md`.

**R3.2 is inherited rather than built.** A paid step goes through `gen.run`, so the
reservation and its refusal are `budget-guard`'s, asserted in that leaf's own suite. Nothing
here can exercise the refusal end to end: no model in the shipped registry carries a price a
number can be parsed from — deliberately, `specs/model-pricing/` says why — so
`budget.estimate_for` returns `None` and no ceiling can bite in a test. What is asserted
here is that the reservation is taken at all: the call is counted and a job file exists.
