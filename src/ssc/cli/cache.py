"""Content-addressed results.

The key is the whole design. A cache that answers "same command, same file" without
noticing a changed parameter returns a stale image that looks plausible, and that is the
failure nobody catches — so everything that can change the result is in the key, and
anything that cannot be put in it is refused rather than coerced.

`cache/` has no index. The filename is the index, which is why deleting the directory is
always safe (R5.3) and why the store needs no migration when its shape changes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from ssc.cli.atomic import replace
from ssc.cli.errors import SscError


def cache_key(
    command: str,
    *,
    params: dict[str, Any],
    inputs: Sequence[str],
    salt: dict[str, Any] | None = None,
) -> str:
    """Derive the key from what the result depends on (R5.1).

    `inputs` are the sha256 digests of the input files, in order — order matters, because
    a frame set is an ordered thing and two orders are two different animations.

    `salt` is the extension point two later leaves need: `model-registry` folds in the
    model id, `cv-runtime` the execution provider. Both would otherwise produce two
    different results under one key.
    """
    document = {
        "command": command,
        "params": params,
        "inputs": list(inputs),
        "salt": salt or {},
    }
    try:
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    except TypeError as error:
        raise SscError(
            "uncacheable-params",
            f"a parameter cannot be represented in a cache key: {error}",
            fix="pass it as a string, a number, or a list of them",
        ) from error
    return hashlib.sha256(canonical.encode()).hexdigest()


def manifest_key(key: str) -> str:
    """Where a set's manifest lives, derived rather than stored beside the key.

    Hashed rather than suffixed: `path_for` shards on the first two characters, and a key with
    a suffix would file the manifest under the same shard as a real blob whose key starts the
    same way — legible, and one character from colliding with a content address.
    """
    return hashlib.sha256(f"set:{key}".encode()).hexdigest()


def member_key(key: str, index: int) -> str:
    """The key one member of a set is stored under."""
    return hashlib.sha256(f"member:{key}:{index}".encode()).hexdigest()


class Cache:
    """The store under `cache/`. Nothing here fails because the directory is missing."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for(self, key: str) -> Path:
        return self.root / key[:2] / key

    def get(self, key: str) -> bytes | None:
        entry = self.path_for(key)
        return entry.read_bytes() if entry.is_file() else None

    def put(self, key: str, data: bytes) -> Path:
        """Store `data` under `key`.

        `replace` rather than `write_new`: the key *is* the content's identity, so a
        second write is the same bytes, and refusing it would turn a harmless race
        between two runs into a failure.
        """
        return replace(self.path_for(key), data)

    def put_set(self, key: str, members: Sequence[bytes]) -> None:
        """Store several files under one key (`specs/model-options/` R5.3).

        One call with `--count 4` produces four files and one key, and a key here *is* a
        content's identity — so the set needs an indirection rather than a bigger value. What
        `key` holds is a manifest naming each member's own key, and each member is stored
        under that key like any other blob.

        The single-file case does not go through this: `get`/`put` stay exactly what they
        were, so nothing that files one result pays for a manifest.
        """
        entries = [member_key(key, index) for index in range(len(members))]
        for entry, data in zip(entries, members, strict=True):
            self.put(entry, data)
        self.put(manifest_key(key), json.dumps({"members": entries}).encode())

    def get_set(self, key: str) -> list[bytes] | None:
        """Every file stored under one key, or `None` if any of them is missing.

        Partly-present is a miss rather than a partial answer: `cache/` may be deleted at any
        time, in whole or in part, and half a set written into an asset is worse than paying
        for the call again.
        """
        manifest = self.get(manifest_key(key))
        if manifest is None:
            return None
        try:
            entries = json.loads(manifest)["members"]
        except (ValueError, KeyError, TypeError):
            return None
        if not isinstance(entries, list) or not entries:
            return None
        found: list[bytes] = []
        for entry in entries:
            if not isinstance(entry, str):
                return None
            data = self.get(entry)
            if data is None:
                return None
            found.append(data)
        return found

    def use(self, key: str, compute: Callable[[], bytes]) -> tuple[bytes, bool]:
        """Return the cached result, or compute and store it. The flag says which (R5.2).

        Commands pass that flag straight into their `Result`, so "this was reused" is one
        field a harness reads rather than something inferred from timing.
        """
        hit = self.get(key)
        if hit is not None:
            return hit, True
        data = compute()
        self.put(key, data)
        return data, False
