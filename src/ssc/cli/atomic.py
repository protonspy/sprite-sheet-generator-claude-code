"""Two ways to write a file, and no third.

`write_new` is how every artefact is written: it refuses a path that already exists (R3.5),
which is what makes "nothing mutates its input" a property of the code. `replace` is for
the one file that is genuinely rewritten — `meta.json` — and it is atomic, so an
interrupted command leaves either the previous record or the new one (R3.6).

`Directory` is not a third way to write. It is *where* those two write: a directory opened
once, with every write made relative to what was opened rather than re-resolved from a
path (R3.7). The module-level pair are that same pair, bound to the parent of the path they
were handed — which is the right binding for a `--out` somebody typed, and the wrong one
for an asset directory a caller checked and then wrote into.
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import stat
from pathlib import Path
from types import TracebackType

from ssc.cli.errors import SscError

# Windows needs O_BINARY or it translates newlines; POSIX has no such flag.
_BINARY = getattr(os, "O_BINARY", 0)

# Likewise absent on Windows, and only ever passed on the branch that has descriptors.
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)

#: Whether writes can be bound to a descriptor rather than to a path. POSIX: yes. Windows:
#: `os.supports_dir_fd` is empty and `os.open` will not open a directory at all, so there
#: is nothing to bind to and `Directory` falls back to checking identity — see its
#: docstring for what that does and does not buy.
#:
#: `os.rename` and not `os.replace`, even though `replace` is what the code below calls.
#: `os.supports_dir_fd` is built by name from the syscalls CPython found — `HAVE_RENAMEAT`
#: registers `"rename"` and nothing registers `"replace"`, on any platform or version —
#: while `os.replace` is the same `renameat` underneath and honours `src_dir_fd` fine. So
#: naming `replace` here made this set unsatisfiable and quietly turned every platform into
#: the Windows fallback: the whole descriptor-bound branch below was dead code. Found by
#: review, on Linux, because two tests that assert the POSIX behaviour failed there while
#: the Windows-only run they were written on stayed green. `_the_binding_is_real` is the
#: test that now fails loudly rather than degrading silently.
_DIR_FD = {os.open, os.rename, os.mkdir, os.unlink} <= os.supports_dir_fd


def _segment(name: str) -> str:
    """One component, because everything below resolves it against a directory.

    Deliberately weaker than `names.check_name`: this also carries `--out somebody typed
    with spaces.png`, and the only property the code below actually depends on is that the
    name does not walk anywhere.

    A drive letter is the third way to walk and the one that does not look like walking.
    `Path("C:/assets/hero") / "D:evil"` is `WindowsPath("D:evil")` — the left side is
    discarded outright — so the branch below that joins paths would leave the directory
    without a separator in sight. `names.check_relative_path` refuses the same shape for
    the same reason.
    """
    if (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or os.sep in name
        or re.match(r"^[A-Za-z]:", name)
    ):
        raise SscError(
            "invalid-name",
            f"{name!r} is not a file name; it has to be one component of a directory",
        )
    return name


class Directory:
    """A directory opened once, with every write made relative to what was opened.

    Checking a path and writing to it are two acts on two different objects: between them a
    component can be replaced with a link — a symlink, or a junction, which Windows lets an
    unprivileged user create — and the write follows it. `listing.under_assets` says the
    directory is inside the workspace; without this, what is written a few statements later
    is whatever the path resolves to *then*.

    On POSIX the binding is literal. A descriptor names an inode, `dir_fd=` resolves
    against it, and nothing done to the path afterwards is visible to a write: swapping
    `<kind>/` for a link cannot move a file that is already being written relative to the
    directory that was checked.

    Windows has no equivalent — `os.supports_dir_fd` is empty there and `os.open` refuses a
    directory outright — so the binding degrades to identity: `(st_dev, st_ino)` read when
    the directory was opened, and read again immediately before each write. What that buys
    is worth stating exactly, because it is less than the descriptor. It does not stop a
    swap; it narrows the window from the length of the command to the two statements around
    one `os.open`, and it turns a lost race into a refusal rather than into a file written
    somewhere nobody asked for. That is the honest limit of what Python offers on Windows.
    """

    __slots__ = ("_fd", "_identity", "path")

    def __init__(self, path: Path, fd: int | None, identity: tuple[int, int]) -> None:
        self.path = path
        self._fd = fd
        self._identity = identity

    @classmethod
    def open(cls, path: Path) -> Directory:
        """Open `path` as a directory and hold it. It has to exist already."""
        if _DIR_FD:
            descriptor = os.open(path, os.O_RDONLY | _DIRECTORY)
            try:
                status = os.fstat(descriptor)
            except BaseException:
                os.close(descriptor)
                raise
            return cls(path, descriptor, (status.st_dev, status.st_ino))
        status = os.stat(path)
        if not stat.S_ISDIR(status.st_mode):
            # O_DIRECTORY is what says this on the branch above. Windows has neither the
            # flag nor a descriptor, so the check is explicit or it does not happen.
            raise NotADirectoryError(path)
        return cls(path, None, (status.st_dev, status.st_ino))

    def confirm(self, path: Path) -> None:
        """Assert that `path` — just validated by whatever validates paths — names the
        directory being held.

        The order matters and is the whole point: open first, then check, then confirm the
        thing that was checked is the thing that is held. Checking and then opening leaves
        the swap that this exists to close.
        """
        if self._identity_of(path) != self._identity:
            raise self._changed(path)

    def child(self, name: str) -> Directory:
        """Create a subdirectory relative to what is held, and hold that too.

        Creating rather than opening, because the one caller — `frames/` — is writing a set
        that must not land on top of a set that is already there (R3.5).
        """
        name = _segment(name)
        self._guard()
        try:
            if self._fd is not None:
                os.mkdir(name, dir_fd=self._fd)
            else:
                (self.path / name).mkdir()
        except FileExistsError:
            raise SscError(
                "file-exists",
                f"{self.path / name} already exists, and nothing in ssc overwrites",
                fix=f"ssc clean, or remove {self.path / name} by hand",
            ) from None
        if self._fd is None:
            return Directory.open(self.path / name)
        descriptor = os.open(name, os.O_RDONLY | _DIRECTORY, dir_fd=self._fd)
        try:
            status = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        return Directory(self.path / name, descriptor, (status.st_dev, status.st_ino))

    def write_new(self, name: str, data: bytes) -> Path:
        """Create `name` in this directory and write `data`. Refuse if it is there (R3.5).

        Uses `O_EXCL` rather than checking first: two commands racing for the same path both
        seeing "not there" and both writing is exactly the outcome the refusal exists to
        prevent.
        """
        name = _segment(name)
        self._guard()
        try:
            descriptor = self._open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise SscError(
                "file-exists",
                f"{self.path / name} already exists, and nothing in ssc overwrites a file",
                fix=f"delete it, or write to another path: rm {self.path / name}",
            ) from None
        _fill(descriptor, data)
        return self.path / name

    def replace(self, name: str, data: bytes) -> Path:
        """Write `data` to `name`, replacing what is there, without a moment where it is
        half written. The temporary is a sibling so the rename stays on one filesystem."""
        name = _segment(name)
        self._guard()
        # `tempfile.mkstemp` takes a directory as a path and not as a descriptor, so it
        # cannot be used on a bound write at all: naming the temporary here is what keeps
        # both branches going through the same `_open`.
        temporary = f".{name}.{secrets.token_hex(8)}.tmp"
        descriptor = self._open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            _fill(descriptor, data)
            if self._fd is not None:
                os.replace(temporary, name, src_dir_fd=self._fd, dst_dir_fd=self._fd)
            else:
                os.replace(self.path / temporary, self.path / name)
        except BaseException:
            self._discard(temporary)
            raise
        return self.path / name

    def delete(self, relative: str) -> None:
        """Delete a recorded file — or the one recorded directory, `frames/` — relative to
        what is held (R3.7).

        Deleting is where this matters most and it was nearly left out. `clean` is the only
        command that removes anything, it removes what a `meta.json` names, and one of those
        names is a directory: a swap under a re-resolved path turns `shutil.rmtree` on a
        `derived` frame set into `shutil.rmtree` on whatever the link points at. A write
        under the same swap creates one stray file, so binding the writes and not the
        deletes would have hardened the cheaper half.

        A recorded path may have segments — `frames/003_walk.png` — and each one is a way
        out. On POSIX every intermediate segment is opened `O_NOFOLLOW`, so a `frames/` that
        somebody replaced with a link fails rather than being followed; the last segment is
        never followed either, because `unlink` removes a link and `shutil.rmtree` refuses
        one. On Windows there is no `O_NOFOLLOW` and no descriptor, so the confinement is
        the resolved-path check `listing.inside` already makes, taken here against a
        directory whose identity was just re-checked.
        """
        segments = [_segment(part) for part in relative.split("/")]
        self._guard()
        if self._fd is None:
            self._delete_by_path(segments)
            return
        held: list[Directory] = []
        try:
            here = self
            for segment in segments[:-1]:
                here = here._descend(segment)
                held.append(here)
            here._remove(segments[-1])
        finally:
            for handle in held:
                handle.close()

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Directory:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __del__(self) -> None:
        # A held directory is a descriptor, and a command that raises between opening one
        # and its `close` should not leak it. `with` is still how the callers write it.
        self.close()

    def _descend(self, name: str) -> Directory:
        """Open an existing subdirectory without following a link into one."""
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        assert self._fd is not None
        try:
            descriptor = os.open(name, os.O_RDONLY | _DIRECTORY | nofollow, dir_fd=self._fd)
        except OSError as refused:
            # ELOOP is what O_NOFOLLOW raises on a symlink, and it arrives as an ordinary
            # OSError rather than as anything more specific.
            raise SscError(
                "path-escapes-asset",
                f"{self.path / name} is not a directory ssc can descend into: {refused}",
                fix="remove that record from meta.json, or move the real directory back",
            ) from refused
        try:
            status = os.fstat(descriptor)
        except BaseException:
            os.close(descriptor)
            raise
        return Directory(self.path / name, descriptor, (status.st_dev, status.st_ino))

    def _remove(self, name: str) -> None:
        """Delete the last segment, whatever it turned out to be."""
        assert self._fd is not None
        try:
            status = os.lstat(name, dir_fd=self._fd)
        except FileNotFoundError:
            # A record whose file already went by hand is still a record to drop, which is
            # `clean`'s own rule: the delete is what is missing, not the caller's mistake.
            return
        if stat.S_ISLNK(status.st_mode):
            # `unlink` here would be safe — it removes the link and never what it points at
            # — but it would also be silent, and the two platforms would disagree, because
            # the path branch resolves and refuses. A recorded entry that is a link is a
            # corrupt record either way: nothing in `ssc` ever writes one. So both refuse,
            # and `clean` reports it instead of quietly tidying the evidence away.
            raise SscError(
                "path-escapes-asset",
                f"{self.path / name} is a link, and ssc does not delete one it did not write",
                fix="remove that record from meta.json, or remove the link by hand",
            )
        if stat.S_ISDIR(status.st_mode):
            shutil.rmtree(name, dir_fd=self._fd)
        else:
            os.unlink(name, dir_fd=self._fd)

    def _delete_by_path(self, segments: list[str]) -> None:
        """Windows: no descriptor to descend through, so the confinement is the resolved
        path, taken against a directory `_guard` has just re-identified."""
        root = self.path.resolve()
        target = self.path.joinpath(*segments)
        resolved = target.resolve()
        if resolved == root or root not in resolved.parents:
            raise SscError(
                "path-escapes-asset",
                f"{'/'.join(segments)!r} resolves to {resolved}, which is outside {root}",
                fix="remove that record from meta.json",
            )
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)

    def _open(self, name: str, flags: int) -> int:
        # 0o600 on both branches. os.open would otherwise default to 0o777 masked by the
        # umask — world-readable data files with an execute bit, for no reason.
        if self._fd is not None:
            return os.open(name, flags | _BINARY, 0o600, dir_fd=self._fd)
        return os.open(self.path / name, flags | _BINARY, 0o600)

    def _discard(self, name: str) -> None:
        try:
            if self._fd is not None:
                os.unlink(name, dir_fd=self._fd)
            else:
                (self.path / name).unlink()
        except FileNotFoundError:
            pass

    def _guard(self) -> None:
        """Windows only: the path is about to be resolved again, so check it still names
        what was opened. On POSIX the descriptor makes this unnecessary by construction."""
        if self._fd is not None:
            return
        if self._identity_of(self.path) != self._identity:
            raise self._changed(self.path)

    @staticmethod
    def _identity_of(path: Path) -> tuple[int, int]:
        status = os.stat(path)
        return (status.st_dev, status.st_ino)

    def _changed(self, path: Path) -> SscError:
        return SscError(
            "directory-changed",
            f"{path} is no longer the directory ssc checked, so nothing was written to it",
            fix="run the command again, and check what is creating links under assets/",
        )


def _fill(descriptor: int, data: bytes) -> None:
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def write_new(path: Path, data: bytes) -> Path:
    """`Directory.write_new` for a caller with a path and no directory to bind to.

    This is the right shape for a `--out` somebody typed: there is no earlier check to stay
    faithful to, so the parent is opened here and the write is relative to that. It is the
    wrong shape for an asset directory, which is why the routes that write into one hold
    their own `Directory` instead.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with Directory.open(path.parent) as directory:
        return directory.write_new(path.name, data)


def replace(path: Path, data: bytes) -> Path:
    """`Directory.replace`, bound the same way and with the same caveat."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with Directory.open(path.parent) as directory:
        return directory.replace(path.name, data)
