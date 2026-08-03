"""Shared plumbing for the CLI tests."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest


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
