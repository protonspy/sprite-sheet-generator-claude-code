# Sweep and review — tasks

**What already covers these paths:** `tests/cli/test_convert.py` covers `tool pixelart` and
`tool bgremove` end to end — the two commands task 2.1 lifts code out of — and
`tests/core/test_pixelart.py` and `tests/core/test_bgremove.py` cover the functions that
lift moves. `tests/cli/test_doctor.py` and `tests/core/doctor/test_checks.py` cover the
report shape R2.1 embeds. `tests/test_no_other_resampler.py` is what R3.3 answers to. All
111 were run green before this work started.

## 1 · The parameter grammar

- [x] 1.1 (Unit) Parse one `--vary name=values` into a name and a list of values, accepting both an explicit list and `first..last:step` — R1.3, R1.6
- [x] 1.2 (TDD) Expand the declared parameters into the ordered cross product, refusing above the ceiling before anything runs — R1.2, R1.4

## 2 · The registry of runnable commands

- [x] 2.1 (Unit) Lift the per-frame work of `pixelart` and `bgremove` out of their commands into functions both the command and the sweep call — R1.1
- [x] 2.2 (Unit) Declare the registry in `cli/steps.py`: per command, the parameters it accepts, how each value is parsed, and the bound it is checked against — R1.1, R1.5, R1.6, R1.7

## 3 · The contact sheet

- [x] 3.1 (TDD) Lay every variant out on one canvas at its own size, resampling nothing, with an empty cell where a variant failed — R3.1, R3.3, R3.5
- [x] 3.2 (Unit) Label each cell with its index and its parameter values, showing a multi-frame variant's first frame — R3.2, R3.4

## 4 · The command

- [x] 4.1 (Unit) Run the variants, measuring each with `doctor` and carrying on past one that fails — R1.1, R2.1, R2.2, R2.4
- [x] 4.2 (Unit) Report the fewest-defects variant as a measurement — R2.3
- [x] 4.3 (Unit) Write the review directory — variants, contact sheet and report — defaulting to `review/<key>/` inside a workspace and refusing to overwrite a sweep already there — R4.1, R4.2, R4.3, R4.4
- [x] 4.4 (Unit) Write nothing under `--dry-run`, and report the variants that would have been produced — R4.5

## Notes

**Two tasks were TDD, and both are geometry or counting rather than plumbing.** 1.2's cross
product decides how much work runs, and its ceiling has to refuse from the counts rather
than by building the product it is protecting against. 3.1's layout is the one artefact in
this leaf with no measurement behind it — a sweep whose contact sheet is subtly wrong is
green, and the human decision is taken on a bad picture.

**Both reds were observed and both were informative.** 1.2's was `AttributeError: module
'ssc.cli.sweep' has no attribute 'expand'`; 3.1's was `ModuleNotFoundError: No module named
'ssc.core.contact'`. A third red arrived from a *Unit* test in the same file and changed the
design: `--vary tol=a..b:c` fell through the range parser into the list parser and became
the single literal value `"a..b:c"`, sweeping one nonsense point instead of refusing. The
routing now keys on `..` being present rather than on whether the whole thing parsed.
