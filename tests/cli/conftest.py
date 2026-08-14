"""Shared plumbing for the CLI tests."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from ssc.cli import fal, jobs, meta, models
from ssc.cli import gen as pipeline
from ssc.cli.atomic import Directory
from ssc.cli.commands import gen as commands

#: A real PNG header, so `extension_for` names a collected file from its content.
PNG = b"\x89PNG\r\n\x1a\n" + b"the rest of a png"


class Completed:
    error = None


@dataclass
class Handle:
    request_id: str = "req-42"


@dataclass
class FakeClient:
    """The five functions `cli/fal.py` needs, and a record of what each was asked."""

    payload: dict[str, Any] = field(
        default_factory=lambda: {"images": [{"url": "https://v3.fal.media/files/a.png"}]}
    )
    submitted: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    encoded: list[bytes] = field(default_factory=list)
    uploaded: list[bytes] = field(default_factory=list)

    def submit(self, application: str, arguments: dict[str, Any]) -> Any:
        self.submitted.append((application, dict(arguments)))
        return Handle()

    def status(self, application: str, request_id: str) -> Any:
        return Completed()

    def result(self, application: str, request_id: str) -> dict[str, Any]:
        return self.payload

    def cancel(self, application: str, request_id: str) -> None:  # pragma: no cover
        raise AssertionError("nothing here cancels")

    def encode(self, data: str | bytes, content_type: str) -> str:
        self.encoded.append(bytes(data))  # type: ignore[arg-type]
        return f"data:{content_type};base64,AAAA"

    def upload(self, data: str | bytes, content_type: str) -> str:
        self.uploaded.append(bytes(data))  # type: ignore[arg-type]
        return "https://v3.fal.media/files/uploaded.png"


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeClient:
    """The fake, wired in where the commands look for a provider and where the pipeline
    fetches a result. The registry is pinned to the shipped copy, so no test reaches fal for
    a schema either.

    Here rather than in `test_gen_commands.py`, where it was: `specs/box-art/` needed the
    same fake in a second file, and importing a fixture by name from another test module
    makes it a redefinition rather than a reuse. A fixture two files share is what a
    `conftest.py` is.
    """
    client = FakeClient()
    # The original, captured before the patch: `pipeline.models` *is* the models module, so a
    # lambda calling `models.load` after the patch would call itself.
    shipped = models.load
    monkeypatch.setattr(commands, "provider", lambda: fal.Fal(api=client))
    monkeypatch.setattr(models, "load", lambda: shipped(fetch=lambda _: None))
    monkeypatch.setattr(pipeline.fal, "fetch", lambda url, **rest: PNG)
    # `gen` reaches its provider through `commands.provider`; `ssc job resume` reaches one
    # through the registry instead. Patching only the first left every `job` command talking
    # to the real fal client — which failed on a missing credential *before* reaching what
    # the test meant to exercise, so the assertion passed on nothing and the run made a live
    # HTTPS call. Both reviews caught it; this is the fix.
    monkeypatch.setitem(jobs.PROVIDERS, fal.PROVIDER, fal.Fal(api=client))
    return client


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(fal.KEY_VARIABLE, "a-fal-key-for-tests")


def save_meta(directory: Path, record: meta.AssetMeta) -> Path:
    """`meta.save` for a test building a fixture on disk.

    `meta.save` takes a held directory on purpose (R3.7) — the type is what stops a
    production caller checking a path and then writing to it. A test putting a `meta.json`
    somewhere has nothing to be faithful to, so it opens the directory here and says so
    once, rather than each fixture growing a `with`.
    """
    with Directory.open(directory) as held:
        return meta.save(held, record)


def load_meta(directory: Path) -> meta.AssetMeta:
    """`meta.load` for a test reading back what a command wrote.

    The read counterpart of `save_meta`, and there for the same reason: `meta.load` takes a
    held directory (R3.7) so that no production caller can check one directory and read
    another, while a test asserting on a `meta.json` it just watched a command write has
    nothing to stay faithful to.
    """
    with Directory.open(directory) as held:
        return meta.load(held)


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
