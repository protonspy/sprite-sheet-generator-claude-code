"""Nothing that looks like a credential leaves a command — workspace-foundation R4.6."""

from __future__ import annotations

import pytest

from ssc.cli import redact

# By value: what the environment holds under a secret-looking name, wherever it appears.


def test_a_secret_from_the_environment_is_replaced_wherever_it_appears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAL_KEY", "abcd1234-secret-value")
    message = "HTTPError: 401 for https://fal.run/x?k=abcd1234-secret-value (abcd1234-secret-value)"

    scrubbed = redact.scrub(message)

    assert "abcd1234-secret-value" not in scrubbed
    assert scrubbed.count(redact.PLACEHOLDER) == 2
    assert "401" in scrubbed


@pytest.mark.parametrize("name", ["FAL_KEY", "API_TOKEN", "CLIENT_SECRET", "DB_PASSWORD", "AUTH_X"])
def test_a_name_that_reads_like_a_credential_is_matched(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "longenoughvalue")
    assert redact.scrub("saw longenoughvalue here") == f"saw {redact.PLACEHOLDER} here"


def test_an_ordinary_variable_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """The guard must not redact the workspace out of every message it appears in."""
    monkeypatch.setenv("SSC_WORKSPACE", "/home/artist/game")
    assert redact.scrub("wrote /home/artist/game/assets") == "wrote /home/artist/game/assets"


def test_a_short_value_is_not_matched(monkeypatch: pytest.MonkeyPatch) -> None:
    """`KEYMAP=C` would otherwise redact every `C` in the output, which destroys more than
    it protects."""
    monkeypatch.setenv("KEYMAP", "C")
    assert redact.scrub("cell is 32x32, class C") == "cell is 32x32, class C"


def test_environment_secrets_reads_the_environment_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    assert "set-after-import" not in redact.environment_secrets()
    monkeypatch.setenv("FAL_KEY", "set-after-import")
    assert "set-after-import" in redact.environment_secrets()


# By shape: a credential that never passed through this process's environment.


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("https://fal.run/run?api_key=sk-live-9999&size=1024", "size=1024"),
        ("https://fal.run/run?token=sk-live-9999", "https://fal.run/run?token="),
        ("access_token: sk-live-9999", "access_token: "),
        ('{"password": "sk-live-9999", "user": "artist"}', '"user": "artist"'),
        ("Authorization: Bearer sk-live-9999", "Authorization: Bearer "),
        ("proxy auth Basic sk-live-9999", "proxy auth Basic "),
        ("could not connect to postgres://svc:sk-live-9999@10.0.0.5:5432/prod", "postgres://svc:"),
        ("amqp://guest:sk-live-9999@broker/", "@broker/"),
        # A managed cache's DSN is all password and no username.
        ("redis://:sk-live-9999@cache.internal:6379/0", "redis://:"),
        # What an HTTP client writes when it stringifies a prepared request, which is the
        # shape a provider's exception carries far more often than the bare header.
        ("{'Authorization': 'Bearer sk-live-9999'}", "'Authorization': 'Bearer "),
        ('{"Authorization": "Bearer sk-live-9999"}', '"Authorization": "Bearer '),
    ],
)
def test_a_credential_is_recognised_by_shape(text: str, kept: str) -> None:
    scrubbed = redact.scrub(text)
    assert "sk-live-9999" not in scrubbed
    assert kept in scrubbed


@pytest.mark.parametrize(
    "prose",
    [
        # `fix` strings say things like this all over this codebase.
        "choose another key, or work with the one that is there",
        # `bearer` and `basic` are ordinary English before they are authorization schemes,
        # and a guard that mangles a doctor finding is a guard somebody turns off.
        "a basic bounding box works",
        "Bearer of good news: the seam closed",
        "the basic cell is 32x32",
    ],
)
def test_prose_is_left_exactly_as_written(prose: str) -> None:
    assert redact.scrub(prose) == prose


def test_a_url_with_no_credential_in_it_survives() -> None:
    assert redact.scrub("fetched https://fal.run/models/x") == "fetched https://fal.run/models/x"


# Over a whole payload, because a command reports more than an error message.


def test_strings_are_scrubbed_at_any_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "abcd1234-secret-value")
    payload = {
        "ok": False,
        "call": {"url": "https://fal.run/x?k=abcd1234-secret-value", "opts": ["seed=1"]},
        "error": {"message": "failed with abcd1234-secret-value"},
    }

    scrubbed = redact.scrubbed(payload)

    assert redact.PLACEHOLDER in scrubbed["call"]["url"]
    assert scrubbed["error"]["message"] == f"failed with {redact.PLACEHOLDER}"
    assert scrubbed["call"]["opts"] == ["seed=1"]


def test_values_that_are_not_strings_survive_unchanged() -> None:
    payload = {"ok": True, "count": 7, "sizes": [32, 64], "cached": False, "cell": None}
    assert redact.scrubbed(payload) == payload


# A key names its value, and the two are separate strings in a dict.


def test_a_secret_under_a_credential_shaped_key_is_replaced() -> None:
    """`api_key=sk-live-…` is caught because the name and the secret are one string. In
    `{"api_key": "sk-live-…"}` they are two, and a value judged alone looks unremarkable —
    which is exactly the shape a resolved provider call carries."""
    payload = {
        "arguments": {
            "prompt": "a knight",
            "api_key": "sk-live-9999",
            "authorization": "Bearer sk-xyz",
            "password": "hunter22222",
        }
    }

    out = redact.scrubbed(payload)["arguments"]

    assert out["api_key"] == redact.PLACEHOLDER
    assert out["authorization"] == redact.PLACEHOLDER
    assert out["password"] == redact.PLACEHOLDER
    assert out["prompt"] == "a knight"


def test_a_list_under_a_credential_shaped_key_goes_too() -> None:
    assert redact.scrubbed({"tokens": ["one", "two"]})["tokens"] == [
        redact.PLACEHOLDER,
        redact.PLACEHOLDER,
    ]


def test_an_ordinary_key_still_gets_the_by_shape_rules() -> None:
    payload = {"summary": "called https://fal.run/x?api_key=sk-live-9999"}

    assert "sk-live-9999" not in redact.scrubbed(payload)["summary"]


@pytest.mark.parametrize("field", ["key", "kind", "stage", "id", "monkey", "keyframe"])
def test_an_ordinary_field_name_is_not_treated_as_a_credential(field: str) -> None:
    """`key` is this project's word for an asset's name. Matching it as a secret blanks a
    field every listing depends on — which is how the first version of this rule broke four
    tests in `test_media.py`."""
    assert redact.scrubbed({field: "hero"}) == {field: "hero"}


@pytest.mark.parametrize(
    "field", ["api_key", "FAL_KEY", "access_token", "client_secret", "authorization", "passwd"]
)
def test_a_credential_shaped_field_name_is(field: str) -> None:
    assert redact.scrubbed({field: "sk-live-9999"}) == {field: redact.PLACEHOLDER}
