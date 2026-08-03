"""Credentials do not reach output, whatever built the string (R4.6).

The catch-all in `main.py` puts an exception's `str()` into the one JSON object a command
emits, and that is the right call — a machine-readable envelope beats a traceback, and
discarding the message would leave `internal-error` and nothing else. But HTTP clients
routinely put the request URL in the message, and a URL routinely carries a credential in
its query string. `gen-fal` is the first leaf that will hold a key, so the guard has to
exist before it lands, not after the first key ends up in somebody's CI log.

Two rules, because a credential arrives two ways:

- **By value.** Anything the environment holds under a secret-looking name is replaced
  wherever it appears — in any format, whether it came through a URL, a header, a config
  dump or a `KeyError`. This is the one that catches the leak nobody predicted, because it
  matches the secret itself rather than the shape of the thing carrying it.
- **By shape.** `token=…`, `api_key=…`, `Authorization: Bearer …`, and the password in a
  `scheme://user:password@host` connection string. This catches a credential that never
  passed through the environment — typed on a command line, read out of a provider's
  config file, or returned in an error the provider itself composed.

Neither rule is complete on its own and neither is complete together; the point is that
the guard is at the boundary rather than at the one call site somebody remembered. What is
knowingly out of reach: a secret transformed on the way — percent-encoded, base64'd, or
line-wrapped — no longer matches the value it came from, so a leaf that reformats a
credential-bearing string before returning it defeats the by-value rule. Nothing here does
that today, and a leaf that needs to should scrub before it reformats.
"""

from __future__ import annotations

import os
import re
from typing import Any

PLACEHOLDER = "***"

# An environment variable whose name reads like it holds a credential.
SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH", re.IGNORECASE)

# Below this, a value is not distinctive enough to match on: `LANG=C` would redact every
# `C` in the output, which is worse than the leak it prevents. A real credential is long.
MIN_SECRET_LEN = 8

# `name=value` or `name: value`, where the name reads like a credential. The value runs to
# the first delimiter — `&` ends a query parameter, whitespace and quotes end everything.
CREDENTIAL_PAIR = re.compile(
    r"((?:api[-_]?key|access[-_]?token|auth[-_]?token|token|secret|password|passwd"
    r"|credential|signature|sig)[\"']?\s*[=:]\s*[\"']?)([^\s&\"',;]+)",
    re.IGNORECASE,
)

# The other half of the same idea, for the scheme that carries the credential positionally.
# `auth` has to precede it: on its own, `bearer` and `basic` are ordinary English, and a
# guard that turns "a basic bounding box" into "a basic *** box" is a guard somebody
# disables — which costs more than the narrower pattern does.
AUTH_SCHEME = re.compile(
    r"((?:proxy-)?authorizations?|auth)([\"']?\s*[=:]?\s*)((?:bearer|basic)\s+)(\S+)",
    re.IGNORECASE,
)

# `scheme://user:password@host`. Neither rule above sees this one: there is no keyword in
# front of the password, and a connection string is routinely held under a name like
# `DATABASE_URL` that reads nothing like a credential.
URL_USERINFO = re.compile(r"(://[^/\s:@]+:)([^/\s@]+)(@)")


def environment_secrets() -> list[str]:
    """Every value the environment holds under a name that reads like a credential.

    Read at call time rather than at import: a test sets one with `monkeypatch.setenv`, and
    a long-lived process could be handed one after start-up.
    """
    return [
        value
        for name, value in os.environ.items()
        if SECRET_NAME.search(name) and len(value) >= MIN_SECRET_LEN
    ]


def scrub(text: str) -> str:
    """The text with every credential this can recognise replaced by `***`."""
    for secret in environment_secrets():
        text = text.replace(secret, PLACEHOLDER)
    text = CREDENTIAL_PAIR.sub(lambda match: match.group(1) + PLACEHOLDER, text)
    text = AUTH_SCHEME.sub(
        lambda match: match.group(1) + match.group(2) + match.group(3) + PLACEHOLDER, text
    )
    return URL_USERINFO.sub(lambda match: match.group(1) + PLACEHOLDER + match.group(3), text)


def scrubbed(value: Any) -> Any:
    """`scrub` over a whole payload, strings at any depth.

    Every string is a candidate, not just the error message: a command that reports the
    call it made — which is exactly what `gen --dry-run` is specified to do — carries the
    URL in `data`, and a guard that covered only `error.message` would miss it.
    """
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return {scrubbed(key): scrubbed(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(scrubbed(item) for item in value)
    return value
