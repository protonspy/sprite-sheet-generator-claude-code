"""Shared plumbing for the CLI tests."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from ssc.cli import meta
from ssc.cli.atomic import Directory


def save_meta(directory: Path, record: meta.AssetMeta) -> Path:
    """`meta.save` for a test building a fixture on disk.

    `meta.save` takes a held directory on purpose (R3.7) — the type is what stops a
    production caller checking a path and then writing to it. A test putting a `meta.json`
    somewhere has nothing to be faithful to, so it opens the directory here and says so
    once, rather than each fixture growing a `with`.
    """
    with Directory.open(directory) as held:
        return meta.save(held, record)


@pytest.fixture
def link_dir() -> Callable[[Path, Path], None]:
    """Make the directory link an unprivileged user can make on this platform.

    A symlink on POSIX; a junction on Windows, where a symlink needs a privilege and a
    junction does not. Testing only the POSIX one would leave the exposure untested on
    the platform where it is *easier* to create — which is also the platform this project
    is developed on.
    """

    def make(link: Path, target: Path) -> None:
        if sys.platform != "win32":
            link.symlink_to(target, target_is_directory=True)
            return
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        if made.returncode != 0:
            reason = made.stderr.decode(errors="replace").strip()
            pytest.skip(f"could not create a junction: {reason}")

    return make
