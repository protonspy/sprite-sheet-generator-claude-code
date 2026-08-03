"""The provider adapter: `specs/gen-fal/` R1.1, R1.3, R1.5, R2.2, R2.3, R2.4.

Nothing here imports `fal_client` and nothing reaches the network. The client is a fake
because the suite has to pass with no `FAL_KEY` and no key is worth a test run.
"""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from ssc.cli import fal, jobs
from ssc.cli.errors import SscError, UsageError

#: A public address, for the guard in `fetch` to be satisfied by. Any routable address does;
#: this one is documentation-reserved so it cannot be mistaken for somewhere real.
PUBLIC = "93.184.216.34"


@pytest.fixture
def resolves(monkeypatch: Any) -> Callable[[str], None]:
    """Answer `fetch`'s address check without asking DNS.

    The guard resolves the host to decide whether it is somewhere this process should be
    reaching, and a suite that resolves real names is a suite that fails on a plane and
    passes differently depending on whose network it runs on. Every test says what the name
    resolves to; that is the input under test, not an incidental.
    """

    def answer(address: str = PUBLIC) -> None:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port, **rest: [(0, 0, 0, "", (address, port or 443))],
        )

    answer()
    return answer


def serve(monkeypatch: Any, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    """Put `handler` behind every request `fetch` makes, without a socket."""
    real = httpx.Client

    def client(**kwargs: Any) -> httpx.Client:
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)


class Queued:
    """Named after the client's own status classes, which is how `state_of` matches."""


class InProgress:
    pass


@dataclass
class Completed:
    error: str | None = None


@dataclass
class Handle:
    request_id: str = "req-1"


@dataclass
class FakeClient:
    """Five functions, and a record of what each one was asked."""

    submitted: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    statuses: list[Any] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)
    cancelled: list[tuple[str, str]] = field(default_factory=list)
    uploaded: list[bytes] = field(default_factory=list)
    encoded: list[bytes] = field(default_factory=list)
    handle: Any = field(default_factory=Handle)
    fails_with: Exception | None = None

    def submit(self, application: str, arguments: dict[str, Any]) -> Any:
        if self.fails_with is not None:
            raise self.fails_with
        self.submitted.append((application, dict(arguments)))
        return self.handle

    def status(self, application: str, request_id: str) -> Any:
        return self.statuses.pop(0)

    def result(self, application: str, request_id: str) -> Any:
        return self.payload

    def cancel(self, application: str, request_id: str) -> None:
        self.cancelled.append((application, request_id))

    def encode(self, data: str | bytes, content_type: str) -> str:
        self.encoded.append(bytes(data))  # type: ignore[arg-type]
        return f"data:{content_type};base64,AAAA"

    def upload(self, data: str | bytes, content_type: str) -> str:
        self.uploaded.append(bytes(data))  # type: ignore[arg-type]
        return "https://v3.fal.media/files/rabbit/uploaded.png"


def test_submit_returns_the_request_id_that_makes_recovery_possible() -> None:
    api = FakeClient()
    assert fal.Fal(api=api).submit("fal-ai/x", {"prompt": "a hero"}) == "req-1"
    assert api.submitted == [("fal-ai/x", {"prompt": "a hero"})]


def test_a_submit_with_no_request_id_is_a_refusal_not_an_empty_job() -> None:
    api = FakeClient(handle=object())
    with pytest.raises(SscError) as refused:
        fal.Fal(api=api).submit("fal-ai/x", {})
    assert refused.value.code == "no-request-id"


def test_the_client_statuses_become_job_states() -> None:
    assert fal.state_of(Queued()) == "submitted"
    assert fal.state_of(InProgress()) == "running"
    assert fal.state_of(Completed()) == "done"


def test_a_completed_call_carrying_an_error_is_a_failure() -> None:
    """The client reports completion for a call that finished badly, and `done` would leave
    a job claiming a result nobody can collect."""
    assert fal.state_of(Completed(error="content policy")) == "failed"


def test_an_unknown_status_is_refused_rather_than_guessed() -> None:
    with pytest.raises(SscError) as refused:
        fal.state_of(object())
    assert refused.value.code == "unknown-status"


def test_status_and_result_and_cancel_are_the_provider_protocol() -> None:
    api = FakeClient(statuses=[InProgress()], payload={"images": [{"url": "https://x/y.png"}]})
    provider = fal.Fal(api=api)
    assert provider.status("fal-ai/x", "req-1") == "running"
    assert provider.result("fal-ai/x", "req-1") == {"images": [{"url": "https://x/y.png"}]}
    provider.cancel("fal-ai/x", "req-1")
    assert api.cancelled == [("fal-ai/x", "req-1")]


def test_a_result_that_is_not_an_object_is_refused() -> None:
    api = FakeClient()
    api.payload = ["not", "an", "object"]  # type: ignore[assignment]
    with pytest.raises(SscError) as refused:
        fal.Fal(api=api).result("fal-ai/x", "req-1")
    assert refused.value.code == "unreadable-result"


def test_a_client_exception_is_reported_as_the_provider_failing() -> None:
    """Not as an `internal-error`: whose fault it is is part of what the report says."""
    api = FakeClient(fails_with=RuntimeError("502 Bad Gateway"))
    with pytest.raises(SscError) as refused:
        fal.Fal(api=api).submit("fal-ai/x", {})
    assert refused.value.code == "provider-failed"
    assert "502" in refused.value.message


def test_no_credential_refuses_before_anything_is_submitted(monkeypatch: Any) -> None:
    monkeypatch.delenv(fal.KEY_VARIABLE, raising=False)
    with pytest.raises(UsageError) as refused:
        fal.credential()
    assert refused.value.code == "no-credential"
    assert fal.KEY_VARIABLE in refused.value.message


def test_a_blank_credential_counts_as_none(monkeypatch: Any) -> None:
    monkeypatch.setenv(fal.KEY_VARIABLE, "   ")
    with pytest.raises(UsageError):
        fal.credential()


def test_a_credential_that_is_set_is_returned(monkeypatch: Any) -> None:
    monkeypatch.setenv(fal.KEY_VARIABLE, "fal-secret-value")
    assert fal.credential() == "fal-secret-value"


def test_an_image_travels_inline_by_default() -> None:
    api = FakeClient()
    url = fal.Fal(api=api).reference(b"\x89PNG-ish", "image/png", upload=False)
    assert url.startswith("data:image/png;base64,")
    assert api.uploaded == []


def test_uploading_is_something_a_caller_asks_for() -> None:
    api = FakeClient()
    url = fal.Fal(api=api).reference(b"\x89PNG-ish", "image/png", upload=True)
    assert url == "https://v3.fal.media/files/rabbit/uploaded.png"
    assert api.encoded == []


def test_an_image_past_the_inline_ceiling_names_the_option_that_uploads_it() -> None:
    api = FakeClient()
    too_big = b"0" * (fal.MAX_INLINE_BYTES + 1)
    with pytest.raises(UsageError) as refused:
        fal.Fal(api=api).reference(too_big, "image/png", upload=False)
    assert refused.value.code == "image-too-large"
    assert "--upload" in (refused.value.fix or "")
    assert api.encoded == [] and api.uploaded == []


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"images": [{"url": "https://f/a.png"}]}, "https://f/a.png"),
        ({"image": {"url": "https://f/b.png"}}, "https://f/b.png"),
        ({"video": {"url": "https://f/c.mp4"}}, "https://f/c.mp4"),
        ({"outputs": {"thing": {"url": "https://f/d.webp"}}}, "https://f/d.webp"),
    ],
)
def test_the_produced_file_is_found_in_each_shape(payload: dict[str, Any], expected: str) -> None:
    assert fal.file_url(payload) == expected


def test_a_result_with_no_file_is_a_refusal_that_says_the_call_was_paid_for() -> None:
    with pytest.raises(SscError) as refused:
        fal.file_url({"seed": 7})
    assert refused.value.code == "no-result-file"
    assert "job resume" in (refused.value.fix or "")


def test_only_https_is_fetched() -> None:
    with pytest.raises(SscError) as refused:
        fal.fetch("file:///etc/passwd")
    assert refused.value.code == "unreadable-result"


def test_fetch_reads_the_body(monkeypatch: Any, resolves: Callable[[str], None]) -> None:
    serve(monkeypatch, lambda request: httpx.Response(200, content=b"the file"))
    assert fal.fetch("https://v3.fal.media/files/rabbit/a.png") == b"the file"


def test_a_result_past_the_ceiling_is_refused_rather_than_held(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    monkeypatch.setattr(fal, "MAX_RESULT_BYTES", 16)
    serve(monkeypatch, lambda request: httpx.Response(200, content=b"0" * 64))
    with pytest.raises(SscError) as refused:
        fal.fetch("https://v3.fal.media/files/rabbit/a.png")
    assert refused.value.code == "result-too-large"


def test_an_unreachable_result_is_reported_as_such(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    def transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    serve(monkeypatch, transport)
    with pytest.raises(SscError) as refused:
        fal.fetch("https://v3.fal.media/files/rabbit/a.png")
    assert refused.value.code == "result-unreachable"


# R1.5 — where the fetch is allowed to end up. A result URL is chosen by whatever model ran
# the job, and the bytes it returns are written into the asset and cached under the call's
# own key, so "https" is not on its own a statement that the host is somewhere to reach.


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "169.254.169.254",  # link-local, and the cloud metadata endpoint
        "10.0.0.5",  # private
        "0.0.0.0",  # unspecified
        # Shared address space. `ipaddress` puts it under none of its own properties, so it
        # is the one range here that had to be named rather than asked about.
        "100.64.1.1",
        "::1",  # loopback, the other family
        "fd00::1",  # unique-local
    ],
)
def test_a_host_that_is_not_public_is_refused(
    monkeypatch: Any, resolves: Callable[[str], None], address: str
) -> None:
    """No redirect involved: an `https` URL naming an internal host passed the old check,
    which only ever read the scheme."""
    resolves(address)
    serve(monkeypatch, lambda request: httpx.Response(200, content=b"secrets"))
    with pytest.raises(SscError) as refused:
        fal.fetch("https://sneaky.example/a.png")
    assert refused.value.code == "unreadable-result"
    assert "not a public address" in refused.value.message


def test_a_redirect_out_of_https_is_refused(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    """`follow_redirects=True` checked the URL it was handed and nothing after it."""

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v3.fal.media":
            return httpx.Response(302, headers={"location": "http://elsewhere.example/a.png"})
        return httpx.Response(200, content=b"not the file")

    serve(monkeypatch, transport)
    with pytest.raises(SscError) as refused:
        fal.fetch("https://v3.fal.media/files/rabbit/a.png")
    assert refused.value.code == "unreadable-result"


def test_a_redirect_to_an_internal_address_is_refused(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    """The hop is https, so only resolving it says where it actually goes."""
    hosts = {"v3.fal.media": PUBLIC, "metadata.example": "169.254.169.254"}
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **rest: [(0, 0, 0, "", (hosts[host], port or 443))],
    )

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v3.fal.media":
            return httpx.Response(302, headers={"location": "https://metadata.example/latest"})
        return httpx.Response(200, content=b"an instance credential")

    serve(monkeypatch, transport)
    with pytest.raises(SscError) as refused:
        fal.fetch("https://v3.fal.media/files/rabbit/a.png")
    assert refused.value.code == "unreadable-result"


def test_an_ordinary_cdn_redirect_is_followed(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    """Refusing every redirect would break the signed-URL pattern a CDN actually uses."""

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/files/"):
            # Relative, as a real `Location` often is — it resolves against the URL just
            # fetched and is then checked like any other hop.
            return httpx.Response(302, headers={"location": "/signed/blob?token=x"})
        return httpx.Response(200, content=b"the file")

    serve(monkeypatch, transport)
    assert fal.fetch("https://v3.fal.media/files/rabbit/a.png") == b"the file"


def test_a_redirect_loop_gives_up_rather_than_following_forever(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    serve(
        monkeypatch,
        lambda request: httpx.Response(302, headers={"location": "https://v3.fal.media/again"}),
    )
    with pytest.raises(SscError) as refused:
        fal.fetch("https://v3.fal.media/files/rabbit/a.png")
    assert refused.value.code == "result-unreachable"
    assert "redirected more than" in refused.value.message


def test_a_redirect_with_no_destination_is_refused(
    monkeypatch: Any, resolves: Callable[[str], None]
) -> None:
    serve(monkeypatch, lambda request: httpx.Response(302))
    with pytest.raises(SscError) as refused:
        fal.fetch("https://v3.fal.media/files/rabbit/a.png")
    assert refused.value.code == "result-unreachable"


def test_registering_puts_the_adapter_where_the_job_commands_look() -> None:
    """`ssc job status|wait|cancel|resume` find a provider by the name a job records."""
    original = dict(jobs.PROVIDERS)
    try:
        jobs.PROVIDERS.clear()
        fal.register()
        assert isinstance(jobs.provider_for(fal.PROVIDER), fal.Fal)
    finally:
        jobs.PROVIDERS.clear()
        jobs.PROVIDERS.update(original)
