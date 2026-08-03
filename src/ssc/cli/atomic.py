"""Two ways to write a file, and no third.

`write_new` is how every artefact is written: it refuses a path that already exists (R3.5),
which is what makes "nothing mutates its input" a property of the code. `replace` is for
the one file that is genuinely rewritten — `meta.json` — and it is atomic, so an
interrupted command leaves either the previous record or the new one (R3.6).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from ssc.cli.errors import SscError

# Windows needs O_BINARY or it translates newlines; POSIX has no such flag.
_BINARY = getattr(os, "O_BINARY", 0)


def write_new(path: Path, data: bytes) -> Path:
    """Create `path` and write `data`. Refuse if anything is already there.

    Uses `O_EXCL` rather than checking first: two commands racing for the same path both
    seeing "not there" and both writing is exactly the outcome the refusal exists to
    prevent.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _BINARY)
    except FileExistsError:
        raise SscError(
            "file-exists",
            f"{path} already exists, and nothing in ssc overwrites a file",
            fix=f"delete it, or write to another path: rm {path}",
        ) from None
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def replace(path: Path, data: bytes) -> Path:
    """Write `data` to `path`, replacing what is there, without a moment where it is half
    written. The temporary file is a sibling so the rename stays on one filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path
