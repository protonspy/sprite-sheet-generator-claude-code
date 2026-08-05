---
status: accepted
---

# 0011 · Two extras for onnxruntime, and detection that ignores them

## Context

M6 runs models locally. `onnxruntime` is how, and its packaging forces a decision before
any of it is built.

`onnxruntime` and `onnxruntime-gpu` are two distributions that publish the **same import
name**. Installing both into one environment leaves whichever landed last, silently, and
the loser's shared libraries stay on disk. There is no runtime flag that selects between
them, because by the time Python is running the choice was made by `pip`. So a single
`[cv]` extra with a `--gpu` switch is not an option that exists — it would install one
build and then pretend the other was reachable.

The second half is a failure that has nothing to do with packaging. Somebody installs
`ssc[cv]` on a machine with a CUDA GPU, runs `bgremove`, waits, and never learns that the
tool could have been thirty times faster. If the only thing that reports on hardware is the
runtime that is installed, a CPU-only install can only ever report a CPU. The install that
most needs to be told about the GPU is precisely the one that cannot see it.

## Decision

**Two extras, and hardware detection that does not consult the installed runtime.**

- **`[cv]` installs `onnxruntime`; `[cv-gpu]` installs `onnxruntime-gpu`.** They are
  alternatives, never both. `rembg` is in each, because it is the model layer and not the
  runtime.
- **Detection reads the machine, not the Python environment.** `ssc info` reports the GPUs
  physically present and, separately, the execution providers the current install can
  actually use. Two lists, never conflated.
- **A gap between them is a structured hint carrying the exact install command.** A CUDA
  device present with only `CPUExecutionProvider` usable is reported as such, with the
  command that closes it. It is a hint and not a warning: nothing is wrong, something is
  merely unrealised, and a command that is working must not print a failure.
- **`--device auto|cpu|cuda|directml|coreml`.** `auto` takes the best provider actually
  usable. **A device named explicitly never falls back** — `--device cuda` on a CPU-only
  install fails, naming the extra to install. A silent fallback is the same defect as the
  paragraph above, moved into a single command.
- **The execution provider is part of the cache key**, folded in through the `salt`
  argument `ssc.cli.cache.cache_key` already carries. Two providers on the same input can
  differ in the last bit; one key over both returns art from a machine the caller is not on.

## Consequences

- `ssc info` works with neither extra installed, and that is the point: the machine that
  cannot run a model is the one that has to be told what it would take.
- Detection is now a second thing to maintain, per platform, against vendors who rename
  things. It is allowed to be uncertain — "no GPU detected" and "cannot tell" are different
  answers and are reported differently. It is never allowed to gate execution: the runtime
  decides what runs, detection only explains.
- **`--device directml` is not covered by either extra as declared.** DirectML ships in a
  third distribution, `onnxruntime-directml`, and `onnxruntime-gpu` on Windows carries CUDA
  rather than DirectML. `specs/cv-runtime/` has to either add a third extra or drop
  `directml` from the accepted set; recording the gap here is what stops it being
  discovered by a Windows user instead.
- Warming the cache under `[cv-gpu]` and reinstalling as `[cv]` re-runs everything. Correct
  — those are different results — and it will read as the cache being broken, so the miss
  has to say which provider it was keyed on.
- Reversing this means telling people who installed one extra to uninstall it and install
  another, and it invalidates their cache. The install line is public surface, which is why
  it is a record.
