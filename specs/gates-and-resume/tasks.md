# Gates and resume — tasks

**What already covers these paths:** `tests/cli/test_jobs.py` and
`tests/cli/test_job_commands.py` cover the one-record-per-file store and the validate-on-read
discipline this leaf copies; `tests/cli/test_kinds.py` and `tests/cli/test_workspace.py` cover
reading a new key out of `ssc.yaml`, which `pipeline:` becomes; `tests/cli/test_meta.py`
covers the recorded stages R4.2 reads to decide a step is done; `tests/cli/test_errors.py` and
`tests/cli/test_main.py` cover the exit-code contract that `3` joins. All were run green
before this work started.

## 1 · The record

- [x] 1.1 (Unit) The gate record — its fields, its three states, the stamped history, and the refusal to decide one twice — R1.1, R1.2, R1.3
- [x] 1.2 (Unit) Save and load one gate, and list every gate, reporting the unreadable rather than failing the listing — R1.1, R1.4

## 2 · The verbs

- [x] 2.1 (Unit) `ssc gate open` — write a pending gate and exit `3`, reporting the existing one where a pending gate for that subject and topic is already there — R2.1, R2.2, R2.3
- [x] 2.2 (Unit) `ssc gate approve` and `ssc gate reject` — record the decision, the choice and the reason — R2.4, R2.5, R1.3
- [x] 2.3 (Unit) `ssc gate list` — every gate with its state, exit `0` — R2.6, R1.4

## 3 · The inheritable default

- [x] 3.1 (Unit) Record an approval as the default for its topic, and read the defaults back — R3.1
- [x] 3.2 (Unit) Open a gate against a recorded default already approved, citing what it inherited, without exiting `3` — R3.2, R3.3

## 4 · The pipeline

- [x] 4.1 (Unit) Read `pipeline:` out of `ssc.yaml` into declared steps, refusing a step whose command cannot be run and one that would bill — R4.7, R4.8, R4.9
- [x] 4.2 (TDD) Decide, for one asset and one pipeline, which steps are done, which is next and what blocks it — from the asset's recorded stages and the gates, and nothing else — R4.2, R4.4, R4.5, R4.6
- [x] 4.3 (Unit) `ssc run` — execute the outstanding steps in order, opening a declared step's gate once it has produced its output and stopping there — R4.1, R4.3, R4.5
- [x] 4.4 (Unit) `ssc status` — each step as done, blocked or outstanding, and the step that would run next — R4.6
