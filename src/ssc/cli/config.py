"""`ssc.yaml`, read once.

`kinds:` was the first setting anything read, so the reader lived in `kinds.py`. `models:` is
the second — `model-registry` takes the model per media from here — and a second reader would
mean a second ceiling, a second loader and a second answer to "what does a malformed config
do". This project already made that call once about images: one reader, one ceiling, in the
module that owns it.
"""

from __future__ import annotations

from typing import Any

import yaml

from ssc.cli.errors import SscError
from ssc.cli.workspace import MARKER, Workspace

__all__ = ["MARKER", "MAX_CONFIG_BYTES", "StrictLoader", "document"]

#: A configuration file is a few dozen lines. The ceiling is here because everything below
#: it — the parse, the alias expansion, the map of maps — is work proportional to the file,
#: and `ssc.yaml` is a file that survives hand-editing by an agent.
MAX_CONFIG_BYTES = 1 << 20


class StrictLoader(yaml.SafeLoader):
    """`safe_load` without anchors.

    `safe_load` refuses to construct arbitrary objects but does **not** bound alias
    expansion: six levels of `&a: [*b, *b, ...]` is a kilobyte on disk and hundreds of
    millions of nodes in memory, and it hangs every config-reading command in the workspace.
    A configuration file has no legitimate use for an anchor, so the answer is to refuse
    them rather than to count them.
    """

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.events.AliasEvent):  # type: ignore[no-untyped-call]
            event = self.peek_event()  # type: ignore[no-untyped-call]
            raise yaml.YAMLError(
                f"anchors and aliases are not allowed in ssc.yaml "
                f"(line {event.start_mark.line + 1})"
            )
        return super().compose_node(parent, index)


def document(workspace: Workspace | None) -> dict[str, Any]:
    """The whole of `ssc.yaml`, or nothing outside a workspace."""
    if workspace is None or not workspace.config_path.is_file():
        return {}

    try:
        # One open, and at most the ceiling plus a byte. `stat()` then `read_bytes()` bounds
        # what the stat reported an instant earlier rather than what is read — and this
        # project anticipates concurrent writers to this exact file, so the window is not
        # hypothetical.
        with workspace.config_path.open("rb") as handle:
            raw = handle.read(MAX_CONFIG_BYTES + 1)
        if len(raw) > MAX_CONFIG_BYTES:
            raise SscError(
                "invalid-config",
                f"{workspace.config_path} is over the {MAX_CONFIG_BYTES:,}-byte ceiling",
                fix="a workspace config is a few dozen lines; check what is in there",
            )
        found = yaml.load(raw.decode("utf-8"), Loader=StrictLoader)
    except (yaml.YAMLError, RecursionError, UnicodeDecodeError) as broken:
        # RecursionError as well: deeply nested flow collections blow the stack inside
        # PyYAML's own scanner, and it is not a YAMLError, so it escaped as a traceback.
        raise SscError(
            "invalid-config",
            f"{workspace.config_path} is not valid YAML: {broken}",
            fix="fix it by hand, or restore it from git",
        ) from broken

    if found is None:
        return {}
    if not isinstance(found, dict):
        raise SscError(
            "invalid-config",
            f"{workspace.config_path} is a {type(found).__name__}, not a map of settings",
            fix="the file is `schema: 1` and settings under it",
        )
    return found
