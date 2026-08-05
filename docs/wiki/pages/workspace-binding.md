# Binding a write to a directory, and what the rounds cost

`ssc` checks that a path is the asset directory the caller named, and then writes into it.
Those are two acts on two different objects, and between them a component can be replaced
with a link — a symlink on POSIX, or a junction, which Windows lets an unprivileged user
create without any elevation at all. The check passes and the write lands somewhere nobody
asked for.

Closing that took four review rounds across two branches. The fixes are in the code and
the code explains them. What is worth keeping is what the rounds cost, because two of the
three lessons are about *how the work was verified*, not about what it did.

## The binding is not the same thing on both platforms

On POSIX it is literal. A descriptor names an inode, `dir_fd=` resolves against it, and
nothing done to the path afterwards is visible to a write already relative to the directory
that was checked. Swapping `<kind>/` for a link cannot move the file.

On Windows there is no equivalent. `os.supports_dir_fd` is empty and `os.open` refuses a
directory outright, so there is nothing to bind to. The fallback is identity: read
`(st_dev, st_ino)` when the directory is opened, read it again immediately before each
write. That is **less than the descriptor and the difference has to be stated in full** —
it does not stop a swap, it narrows the window from the length of the command to the two
statements around one `os.open`, and it turns a lost race into a refusal rather than a file
written elsewhere.

Writing that sentence honestly is most of the work. A fallback described as "the Windows
equivalent" is a fallback nobody will re-examine.

## A platform-conditional hardening needs the other platform run before the PR

The flag that chooses between the two branches asks whether the syscalls it needs accept a
directory descriptor. It was written naming `os.replace`, which is what the code below it
actually calls.

`os.supports_dir_fd` is built by name from the syscalls CPython found. `HAVE_RENAMEAT`
registers `"rename"`; nothing registers `"replace"`, on any platform or any version. So the
set was unsatisfiable, the flag was `False` everywhere, and **every platform silently took
the Windows fallback**. The entire descriptor-bound branch — the stronger half, the reason
the module was written — was dead code.

It was written and tested on Windows, where the fallback is the correct answer, so the
suite was green and stayed green. It was found by review running the same suite on Linux,
where two tests asserting the POSIX behaviour failed immediately.

Nothing about this is subtle in hindsight, and no amount of care on one machine would have
caught it: the failing tests already existed and had never been run anywhere they could
fail. The rule that follows is narrow and mechanical — **a change whose behaviour branches
on the platform is not verified until it has run on the other branch**, and for this project
that means before the pull request rather than after CI notices.

The lasting fix is not the corrected name. It is that the flag now has a test that fails
loudly on POSIX instead of degrading into the weaker path.

## A guard that cannot work has to refuse, not report success

The Windows fallback rests on `(st_dev, st_ino)`, and that is a **measurement of the
volume, not a property of the platform**. NTFS reports both honestly. FAT32, exFAT and some
SMB mounts have no file index at all and Windows returns `0` for it — which makes every
directory on such a volume identical to every other one, and turns the comparison into one
that always succeeds.

That is the same shape of failure as the dead branch above, arriving by a different route:
a hardening that reports success while doing nothing. Both are worse than having no guard,
because the absence of a guard is at least legible.

So it is measured per volume rather than assumed per platform, and a handle that cannot
prove what it holds says so and the command refuses. The refusal is deliberately
conservative — a volume with no file index also has no reparse points, so the swap being
guarded against cannot be staged there — and it is still the right answer, because **a
guard that cannot say which case it is in has no business claiming either.**

## Re-run the gates; a fix is not a fix until it is

The second review round found two regressions that the first round's fixes had introduced.
Replacing a read loop with the bound primitive closed the link hole and dropped the ceiling
on the set: each file was bounded, N files were not, so a stage with individually legal
frames decoded without limit. And a redaction added to one writer missed its sibling, which
persisted the same free text to a different file.

Neither is a careless fix. Both are the ordinary consequence of changing the path a value
travels: the new path has its own invariants and does not inherit the old one's. The habit
worth keeping is that **a fix round ends by re-running the gates, not by re-reading the
diff** — the second round existed because the first was trusted.

## Where this shows up

Every command that reads or writes inside a workspace goes through the bound primitives,
including the `dist/` writes described in [[into-an-engine]]. The binding for a read arrived
a task after the binding for a write, and the reason is worth keeping: a swap under a read
corrupts nothing, it feeds the command a foreign record and lets it report that record as
the asset the caller asked for. Lower stakes, much wider surface — almost every command
loads a `meta.json`.
