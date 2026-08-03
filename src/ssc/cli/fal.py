"""Fal AI, held behind one module.

Two things live here and nothing else: the provider adapter `job-store` asks for, and the
three jobs the client does not do for us — proving there is a credential before anything is
submitted, getting a local image to a model that only takes URLs, and fetching back the file
a finished call points at.

Nothing above this module imports `fal_client`. That is deliberate on two counts: the free
half of the tool must not pay for an HTTP client's import on every `ssc tool snap`, and the
first real call against the live provider should have exactly one file to correct — see
`specs/gen-fal/design.md` on what is and is not exercised by the suite.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from ssc.cli import jobs
from ssc.cli.errors import SscError, UsageError

#: The name a job records, and the key `jobs.PROVIDERS` holds this adapter under.
PROVIDER = "fal"

KEY_VARIABLE = "FAL_KEY"

#: What the client's three status dataclasses mean in this project's vocabulary, matched by
#: class name rather than by `isinstance`. The name is the stable part — a fake in the suite
#: is then a fake rather than a subclass of the client's own type, which is what keeps the
#: tests from importing the provider at all.
STATES = {"Queued": "submitted", "InProgress": "running", "Completed": "done"}

#: Inline is the default and this is where it stops. A data URL travels in the request body,
#: and past a few megabytes that is a request nobody's gateway wants — so the refusal names
#: `--upload` rather than letting the provider reject a payload it already received.
MAX_INLINE_BYTES = 4 * 1024 * 1024

#: What a finished call may hand back. A video is the large case, and this is well above any
#: clip the video model produces at its own resolution tiers.
MAX_RESULT_BYTES = 256 * 1024 * 1024

#: Per socket operation, and then in total — the pair `models.py` already needed for the same
#: reason: a server trickling a byte at a time keeps every read under the socket timeout and
#: never finishes.
SOCKET_TIMEOUT = 30.0
MAX_FETCH_SECONDS = 300.0

#: Where a completed result puts the thing it produced, in the order these models use.
#: `docs/wiki/model-parameters.md` names them; the fallback below is what happens when a
#: model this project has not met puts it somewhere else.
RESULT_KEYS = ("images", "image", "video", "videos", "audio", "file", "files")


class Client(Protocol):
    """What this module needs of `fal_client`, which is all of five functions.

    A Protocol rather than the module itself, because every test injects a fake: the suite
    must pass with no `FAL_KEY` and no network, and a test that pays money is a test nobody
    runs twice.
    """

    def submit(self, application: str, arguments: dict[str, Any]) -> Any: ...

    def status(self, application: str, request_id: str) -> Any: ...

    def result(self, application: str, request_id: str) -> dict[str, Any]: ...

    def cancel(self, application: str, request_id: str) -> None: ...

    def encode(self, data: str | bytes, content_type: str) -> str: ...

    def upload(self, data: str | bytes, content_type: str) -> str: ...


def client() -> Client:
    """The real client, imported at call time.

    Not at module import: `cli/app.py` imports every command, so a top-level import here
    would put `httpx`, `aiofiles` and the rest of the client's tree in front of `ssc tool
    snap` — a command that will never make a network call.
    """
    import fal_client

    return fal_client  # type: ignore[return-value]


def credential() -> str:
    """The key, or the refusal that names it (R1.3).

    Checked here rather than left to the client, which raises its own error somewhere inside
    the submit — by which point a job record has already been written for a call that was
    never going to happen.
    """
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise UsageError(
            "no-credential",
            f"{KEY_VARIABLE} is not set, and generating costs money",
            fix=f"export {KEY_VARIABLE}=<your fal key>, or use the tool commands, which are free",
        )
    return key


def state_of(status: Any) -> str:
    """One of `jobs.STATES`, from whatever the client returned (R1.1).

    A `Completed` carrying an error is a failure: the client reports completion for a call
    that finished badly, and reading it as `done` would leave a job claiming a result that
    is not there.
    """
    name = type(status).__name__
    if name == "Completed" and getattr(status, "error", None):
        return "failed"
    state = STATES.get(name)
    if state is None:
        raise SscError(
            "unknown-status",
            f"fal reported a status this build does not know: {name}",
            fix="upgrade ssc, or ssc job list to see what is on disk",
        )
    return state


@dataclass(frozen=True)
class Fal:
    """The provider, as `job-store` wants it and as `gen` needs it.

    `status`, `result` and `cancel` are `jobs.Provider` exactly — three calls taking
    `(application, request_id)` and holding nothing between them, which is
    `adr:0006-job-store-rides-the-fal-client-handle-surface` restated as an interface. That
    is what makes `ssc job resume` work from a fresh process.

    `api` left out is the real client, imported on first use. That is what lets this be
    registered in `jobs.PROVIDERS` at import time — so `ssc job status` reaches fal — without
    every `ssc` invocation paying for the client's import tree.
    """

    api: Client | None = None

    @property
    def _api(self) -> Client:
        return self.api if self.api is not None else client()

    def submit(self, application: str, arguments: dict[str, Any]) -> str:
        """Submit, and return the id that makes the call recoverable.

        Called from inside `jobs.submit`, which has already written the record. `subscribe`
        would be shorter and cannot be used: it blocks until the result arrives, so the id
        never reaches disk — see `adr:0005-a-job-always-exists`.
        """
        handle = self._ask(lambda: self._api.submit(application, arguments))
        request_id = getattr(handle, "request_id", None)
        if not isinstance(request_id, str) or not request_id:
            raise SscError(
                "no-request-id",
                "fal accepted the call and returned no request id",
                fix="ssc job list — the record is on disk either way",
            )
        return request_id

    def status(self, application: str, request_id: str) -> str:
        return state_of(self._ask(lambda: self._api.status(application, request_id)))

    def result(self, application: str, request_id: str) -> dict[str, Any]:
        collected = self._ask(lambda: self._api.result(application, request_id))
        if not isinstance(collected, dict):
            raise SscError(
                "unreadable-result",
                f"fal returned a {type(collected).__name__} where a result object was expected",
            )
        return collected

    def cancel(self, application: str, request_id: str) -> None:
        self._ask(lambda: self._api.cancel(application, request_id))

    def reference(self, data: bytes, content_type: str, *, upload: bool) -> str:
        """A URL the model can read, for bytes that are on this machine (R2.2, R2.3, R2.4).

        Inline by default, and that is a privacy decision rather than a performance one:
        uploading puts the caller's art on a third-party CDN with a lifetime nobody in this
        project controls, while a data URL stays in the request body. So the upload is
        something a caller asks for, the same way spending money is.
        """
        if upload:
            return str(self._ask(lambda: self._api.upload(data, content_type)))
        if len(data) > MAX_INLINE_BYTES:
            raise UsageError(
                "image-too-large",
                f"{len(data):,} bytes is past the {MAX_INLINE_BYTES:,}-byte inline ceiling",
                fix="pass --upload to put it on fal's storage instead, or scale it down first",
            )
        return str(self._ask(lambda: self._api.encode(data, content_type)))

    def _ask(self, call: Any) -> Any:
        """Every crossing into the client, in one place.

        The client's exceptions are its own — `FalClientHTTPError`, `httpx` transport errors,
        `MissingCredentialsError` — and each of them reaching `cli/main.py`'s catch-all would
        be reported as an `internal-error` in ssc, which is a lie about whose fault it is.
        The message travels; `output.render` is what scrubs a credential out of it.
        """
        try:
            return call()
        except SscError:
            raise
        except Exception as refused:
            raise SscError(
                "provider-failed",
                f"fal: {type(refused).__name__}: {refused}",
                fix="ssc job list — a submitted call has a record whatever happened next",
            ) from refused


def file_url(result: dict[str, Any]) -> str:
    """Where a finished call put the file it produced (R1.5).

    The four models answer in three shapes — `images: [{url}]`, `image: {url}`,
    `video: {url}` — so the known keys are tried in order and anything else falls back to the
    first `url` at any depth. A result nobody can find a file in is a refusal rather than an
    empty write: the call was paid for, and the honest report is that the payload is not what
    this build expects.
    """
    for key in RESULT_KEYS:
        found = _url_in(result.get(key))
        if found is not None:
            return found
    found = _url_in(result)
    if found is not None:
        return found
    raise SscError(
        "no-result-file",
        f"fal returned a result with no file in it: {sorted(result)}",
        fix="ssc job resume <id> reports the whole payload; the call is already paid for",
    )


def _url_in(value: Any) -> str | None:
    """The first `url` in whatever this is, breadth-first and bounded by the payload."""
    if isinstance(value, dict):
        found = value.get("url")
        if isinstance(found, str) and found:
            return found
        for item in value.values():
            nested = _url_in(item)
            if nested is not None:
                return nested
        return None
    if isinstance(value, list):
        for item in value:
            nested = _url_in(item)
            if nested is not None:
                return nested
    return None


#: How many hops a result URL may take before this gives up. A CDN legitimately redirects
#: once or twice — to a signed URL, to a regional edge. A chain longer than this is not a
#: delivery pattern, and following it indefinitely is a way to be walked somewhere.
MAX_REDIRECTS = 5

#: Shared address space (RFC 6598), which `ipaddress` classifies under none of the
#: properties `_reachable` checks — not `is_private`, not `is_reserved`. It is what carrier
#: NAT and a good many container and cloud fabrics number their internal hosts out of, so on
#: exactly the machines this guard is for it is an internal address wearing a public one's
#: clothes. Named here rather than assumed absent.
SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


def _reachable(url: str) -> None:
    """Refuse a fetch target that is not public https (R1.5).

    A result URL is chosen by whatever model ran the job, so it is attacker-controlled input
    in the ordinary case, not the paranoid one: the bytes it returns are written into the
    caller's asset directory as a `source` file and cached under the *original* call's key,
    so a poisoned fetch is both filed and replayable. `https` alone does not say a host is
    somewhere this process should be reaching — `https://169.254.169.254/` satisfies it, and
    so does anything on the loopback interface or the local network.

    The residual gap, stated rather than papered over: the name is resolved here and resolved
    again by the connection, so a record that changes between the two is not caught (a DNS
    rebind). Closing it means pinning the connection to the address that was checked, which
    is a custom transport for a CLI that fetches from one CDN — disproportionate to the
    exposure, and the wrong shape to hide behind a comment claiming otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        named = parsed.scheme or url.split(":", 1)[0]
        raise SscError(
            "unreadable-result",
            f"fal pointed at {named}:… , and ssc only fetches https",
            fix="ssc job resume <id> reports the payload; the result is still on fal",
        )
    host = parsed.hostname
    if not host:
        raise SscError(
            "unreadable-result",
            f"{url} names no host to fetch from",
            fix="ssc job resume <id> reports the payload; the result is still on fal",
        )

    try:
        found = socket.getaddrinfo(host, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as unresolved:
        raise SscError(
            "result-unreachable",
            f"{host} could not be resolved: {unresolved}",
            fix="ssc job resume <id> — the call is paid for and the URL is in the payload",
        ) from unresolved

    for entry in found:
        address = ipaddress.ip_address(entry[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
            or (address.version == 4 and address in SHARED_ADDRESS_SPACE)
        ):
            raise SscError(
                "unreadable-result",
                f"{host} resolves to {address}, which is not a public address",
                fix="ssc job resume <id> reports the URL; fetch it by hand if it is genuine",
            )


def fetch(url: str, *, timeout: float = SOCKET_TIMEOUT) -> bytes:
    """The produced file, bounded in size and in wall clock (R1.5).

    Public `https` only, and streamed: the same two rules `models.fetch_from_provider`
    needed, for the same reasons. A result URL is a string the provider chose, so it is
    treated as untrusted input — `read()` on it with no ceiling is how a response becomes
    this process's memory, and a trickling server is how a command becomes a hang.

    Redirects are followed by hand rather than by `follow_redirects=True`, because that flag
    checks the URL this was called with and nothing after it: an `https` URL that redirects
    to `http://localhost` was previously followed, and the body written into the asset. Every
    hop goes through the same guard as the first.
    """
    give_up_at = time.monotonic() + MAX_FETCH_SECONDS
    chunks: list[bytes] = []
    read = 0
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                _reachable(url)
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise SscError(
                                "result-unreachable",
                                "the result redirected with no destination "
                                f"({response.status_code})",
                                fix="ssc job resume <id> reports the URL; fetch it by hand",
                            )
                        # Against the URL just fetched, so a relative `Location` resolves the
                        # way a browser would — and is then checked like any other target.
                        url = str(response.url.join(location))
                        continue
                    response.raise_for_status()
                    for chunk in response.iter_bytes(64 * 1024):
                        if time.monotonic() > give_up_at:
                            raise SscError(
                                "result-timeout",
                                f"fetching the result took longer than {MAX_FETCH_SECONDS:g}s",
                                fix=(
                                    "ssc job resume <id> — the result is collected "
                                    "and already paid for"
                                ),
                            )
                        read += len(chunk)
                        if read > MAX_RESULT_BYTES:
                            raise SscError(
                                "result-too-large",
                                f"the result is over the {MAX_RESULT_BYTES:,}-byte ceiling",
                                fix="ssc job resume <id> reports the URL; fetch it by hand",
                            )
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise SscError(
                "result-unreachable",
                f"the result redirected more than {MAX_REDIRECTS} times",
                fix="ssc job resume <id> reports the URL; fetch it by hand",
            )
    except httpx.HTTPError as unreachable:
        raise SscError(
            "result-unreachable",
            f"the result could not be fetched: {type(unreachable).__name__}: {unreachable}",
            fix="ssc job resume <id> — the call is paid for and the URL is in the payload",
        ) from unreachable


def register() -> None:
    """Put the adapter in `jobs.PROVIDERS`, so `ssc job status|wait|cancel|resume` reach fal.

    Called from `commands/gen.py`, which is what `cli/app.py` loads. Registering from this
    module's import instead would make importing it a side effect, and this module is also
    imported by tests that want no provider registered at all.
    """
    jobs.PROVIDERS.setdefault(PROVIDER, Fal())
