"""`ssc gen image|video|expand|bgremove|collect` — specs/gen-fal R1, R2, R4.

Every test runs against a fake client and a stubbed fetch. Nothing here reaches the network
and nothing reads a real credential: the suite has to pass with no `FAL_KEY`, which is the
same discipline `model-registry` applied to the schema fetch and matters more here, because
this half bills.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner
from conftest import load_meta

from ssc.cli import fal, jobs, meta, models
from ssc.cli import gen as pipeline
from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.atomic import Directory
from ssc.cli.commands import gen as commands
from ssc.cli.errors import UsageError

NANO = "fal-ai/nano-banana-2"
NANO_EDIT = "fal-ai/nano-banana-2/edit"
GROK = "xai/grok-imagine-video/image-to-video"
BIREFNET = "fal-ai/birefnet/v2"

#: A real PNG header, so `extension_for` names the collected file from its content.
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
    a schema either."""
    client = FakeClient()
    # The original, captured before the patch: `pipeline.models` *is* the models module, so a
    # lambda calling `models.load` after the patch would call itself.
    shipped = models.load
    monkeypatch.setattr(commands, "provider", lambda: fal.Fal(api=client))
    monkeypatch.setattr(models, "load", lambda: shipped(fetch=lambda _: None))
    monkeypatch.setattr(pipeline.fal, "fetch", lambda url, **rest: PNG)
    return client


@pytest.fixture
def space(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    (tmp_path / "ssc.yaml").write_text(
        yaml.safe_dump({"schema": 1, "models": {"image": NANO, "video": GROK}}), encoding="utf-8"
    )
    CliRunner().invoke(main, ["asset", "new", "hero", "--kind", "character"])
    return tmp_path


@pytest.fixture
def keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(fal.KEY_VARIABLE, "a-fal-key-for-tests")


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def asset_meta(space: Path) -> meta.AssetMeta:
    return load_meta(space / "assets" / "character" / "hero")


def png_at(space: Path, name: str = "anchor.png") -> Path:
    path = space / name
    path.write_bytes(PNG)
    return path


# ------------------------------------------------------------- the image  R2.2


def test_a_loose_file_is_read_by_path(space: Path) -> None:
    """`--in` names a file that is nobody's asset, so a path is the whole answer."""
    image = pipeline.image_at(png_at(space))
    assert image.data == PNG
    assert image.content_type == "image/png"


def test_a_staged_file_is_read_through_the_held_directory(space: Path) -> None:
    """R3.7 — `--from-stage` addresses a file inside an asset, and the bytes a paid call is
    built from have to come through the directory the address was checked against."""
    directory = space / "assets" / "character" / "hero"
    (directory / "001_hero.gen.png").write_bytes(PNG)

    with Directory.open(directory) as held:
        image = pipeline.image_in(held, "001_hero.gen.png")

    assert image.data == PNG
    assert image.content_type == "image/png"
    # Named by what the record calls it, so `elided()` reports the file rather than a
    # temporary path nobody can find again.
    assert image.path.name == "001_hero.gen.png"


@pytest.mark.parametrize("reader", ["at", "in"])
def test_a_file_ssc_does_not_send_is_refused_either_way(space: Path, reader: str) -> None:
    """Both readers refuse the same extensions: the model reads the content type, and a
    guessed one is a call that is paid for and fails at the far end."""
    directory = space / "assets" / "character" / "hero"
    (directory / "notes.txt").write_bytes(b"not an image")

    with pytest.raises(UsageError) as refused:
        if reader == "at":
            pipeline.image_at(directory / "notes.txt")
        else:
            with Directory.open(directory) as held:
                pipeline.image_in(held, "notes.txt")

    assert refused.value.code == "unsupported-image"


def test_a_stage_naming_a_file_that_is_gone_is_a_usage_error(space: Path) -> None:
    """A record can outlive the file it names — a hand-deleted frame, an interrupted write.
    That is the caller's to fix, so it is a refusal rather than the catch-all's traceback."""
    directory = space / "assets" / "character" / "hero"
    with Directory.open(directory) as held, pytest.raises(UsageError) as refused:
        pipeline.image_in(held, "001_hero.gen.png")

    assert refused.value.code == "no-input"


# --------------------------------------------------------------------- dry run


def test_dry_run_reports_the_resolved_call_and_submits_nothing(
    space: Path, api: FakeClient
) -> None:
    """R4.3, and the one command in this leaf that works with no credential at all: an agent
    inspecting what a call would be must not need a key to do it."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--size",
        "768x512",
        "--dry-run",
    )
    assert code == 0
    assert payload["dry_run"] is True and payload["submitted"] is False
    assert payload["model"] == NANO
    assert payload["template"] == "character"
    assert payload["arguments"]["aspect_ratio"] == "3:2"
    assert payload["arguments"]["resolution"] == "1K"
    assert payload["size"]["requested"] == "768x512"
    assert api.submitted == []
    assert list((space / "jobs").glob("*.json")) == []
    assert asset_meta(space).files == []


def test_the_prompt_is_the_kinds_template_around_what_was_asked(
    space: Path, api: FakeClient
) -> None:
    """R2.1 — a `character` asset and a `tile` asset are generated by two templates and one
    command, which is what keeps a kind a profile rather than a code change."""
    _, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )
    sent = payload["arguments"]["prompt"]
    assert "a knight" in sent
    assert "64x64" in sent  # the character profile's cell reached the template
    assert "chroma-green" in sent


def test_an_option_the_model_does_not_have_is_refused_before_the_money(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R2.5. The failure this prevents is invisible at the provider: the call succeeds, the
    parameter is dropped, and the job is billed for an image that ignored you."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--opt",
        "guidance_scale=7",
    )
    assert code == 2
    assert payload["error"]["code"] == "unknown-option"
    assert api.submitted == []


def test_a_six_by_one_layout_is_refused_rather_than_squashed(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R3.2, against the model that offers ratios: 6:1 is not close to anything nano offers."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "six poses",
        "--size",
        "1536x256",
    )
    assert code == 2
    assert payload["error"]["code"] == "size-unrepresentable"
    assert api.submitted == []


# ------------------------------------------------------------------ submitting


def test_no_credential_refuses_before_a_job_is_recorded(
    space: Path, api: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1.3 — and no job file, because a call that was never going to happen should not leave
    a record saying it was attempted."""
    monkeypatch.delenv(fal.KEY_VARIABLE, raising=False)
    code, payload = run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    assert code == 2
    assert payload["error"]["code"] == "no-credential"
    assert api.submitted == []
    assert list((space / "jobs").glob("*.json")) == []


def test_gen_image_records_submits_collects_and_files(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R1.1, R1.2, R4.1 — the whole path, and the class the file lands under."""
    code, payload = run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    assert code == 0
    assert payload["submitted"] is True and payload["collected"] is True
    assert payload["file"] == "001_hero.gen.png"
    assert payload["job"]["state"] == "done"
    assert payload["job"]["request_id"] == "req-42"

    written = space / "assets" / "character" / "hero" / "001_hero.gen.png"
    assert written.read_bytes() == PNG

    recorded = asset_meta(space).stage("gen")
    assert recorded.file_class == "source"
    assert recorded.produced_by.command == "gen image"
    assert recorded.produced_by.cache_key
    assert recorded.sha256 == meta.digest(PNG)


def test_the_job_is_written_before_the_call_is_made(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R1.1. `jobs.submit` owns the order; this is the assertion that `gen` goes through it
    rather than reimplementing record-then-call."""
    calls: list[str] = []
    original_save = jobs.save

    def watched(workspace: ws.Workspace, job: jobs.Job) -> Path:
        calls.append(f"save:{job.state}:{job.request_id}")
        return original_save(workspace, job)

    jobs.save = watched  # type: ignore[assignment]
    try:
        original_submit = FakeClient.submit

        def watched_submit(self: FakeClient, application: str, arguments: dict[str, Any]) -> Any:
            calls.append("submit")
            return original_submit(self, application, arguments)

        FakeClient.submit = watched_submit  # type: ignore[method-assign]
        try:
            run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
        finally:
            FakeClient.submit = original_submit  # type: ignore[method-assign]
    finally:
        jobs.save = original_save  # type: ignore[assignment]

    assert calls[0] == "save:submitted:None"
    assert calls[1] == "submit"


def test_the_job_records_the_call_and_not_the_payload(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The image travels as a data URL and is recorded as a digest: a job file is meant to
    answer "what did I pay for", and megabytes of base64 in it answers nothing."""
    reference = png_at(space)
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "armour",
        "--ref",
        str(reference),
    )
    recorded = payload["job"]["arguments"]["image_urls"]
    assert recorded == [{"sha256": meta.digest(PNG), "bytes": len(PNG), "from": "anchor.png"}]

    application, sent = api.submitted[0]
    assert application == NANO_EDIT  # R2.6 — a reference image is a different endpoint
    assert sent["image_urls"][0].startswith("data:image/png;base64,")  # R2.2


def test_uploading_is_opt_in(space: Path, api: FakeClient, keyed: None) -> None:
    """R2.3 — the same instinct as never spending money without being asked: art does not go
    to a third-party CDN unless somebody says so."""
    run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "armour",
        "--ref",
        str(png_at(space)),
        "--upload",
    )
    assert api.uploaded == [PNG] and api.encoded == []
    _, sent = api.submitted[0]
    assert sent["image_urls"] == ["https://v3.fal.media/files/uploaded.png"]


def test_no_wait_hands_back_the_job_and_files_nothing(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R1.4."""
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait"
    )
    assert code == 0
    assert payload["submitted"] is True and payload["collected"] is False
    assert "file" not in payload
    assert asset_meta(space).files == []

    stored = jobs.load(ws.Workspace(root=space), payload["job"]["id"])
    assert stored.request_id == "req-42"


def test_collect_files_a_result_that_is_already_paid_for(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R1.5 — the whole reason `--no-wait` is safe and a crash costs nothing but time."""
    _, submitted = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait"
    )
    code, payload = run(
        "gen", "collect", submitted["job"]["id"], "--asset", "character/hero", "--stage", "gen"
    )
    assert code == 0
    assert payload["file"] == "001_hero.gen.png"
    assert asset_meta(space).stage("gen").file_class == "source"
    assert len(api.submitted) == 1  # nothing was submitted a second time


def test_collecting_leaves_the_workspace_as_waiting_would_have(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R1.6 across the `--no-wait` seam — and the failure this catches costs real money.

    `gen collect` files the result but used to cache nothing, because the key covers the
    digests of the images sent and the job record elides them. So an agent that submitted
    with `--no-wait`, collected, then re-issued the command it remembered would miss the
    cache and be billed a second time for bytes already sitting in the asset. The job now
    carries the key its submission computed, which is the only place the whole input is
    known.
    """
    _, submitted = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait"
    )
    run("gen", "collect", submitted["job"]["id"], "--asset", "character/hero", "--stage", "gen")

    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--stage", "again"
    )
    assert code == 0
    assert payload["cached"] is True and payload["submitted"] is False
    assert len(api.submitted) == 1  # the second call was never paid for
    assert asset_meta(space).stage("again").file_class == "source"


def test_a_collected_job_records_the_key_it_was_submitted_under(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The job is the record of what was paid for, and the key is part of that — a collector
    reconstructing it would be working from less than the submitter had."""
    _, submitted = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait"
    )
    assert submitted["job"]["cache_key"] == submitted["cache_key"]

    stored = json.loads(
        (space / "jobs" / f"{submitted['job']['id']}.json").read_text(encoding="utf-8")
    )
    assert stored["cache_key"] == submitted["cache_key"]


def test_an_identical_call_is_served_from_the_cache(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R1.6, R4.2 — the one case where a `gen` command costs nothing, reported as `cached`
    like every other reuse in this tool."""
    run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--stage", "again"
    )
    assert code == 0
    assert payload["cached"] is True and payload["submitted"] is False
    assert len(api.submitted) == 1
    assert asset_meta(space).stage("again").file_class == "source"


def test_a_different_prompt_is_a_different_key(space: Path, api: FakeClient, keyed: None) -> None:
    run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    run("gen", "image", "--asset", "character/hero", "--prompt", "a wizard", "--stage", "second")
    assert len(api.submitted) == 2


# ------------------------------------------------------------- the other verbs


def test_gen_video_takes_the_video_model_and_its_own_template(
    space: Path, api: FakeClient, keyed: None
) -> None:
    _, payload = run(
        "gen",
        "video",
        "--asset",
        "character/hero",
        "--prompt",
        "walks",
        "--in",
        str(png_at(space)),
        "--seconds",
        "2",
        "--dry-run",
    )
    assert payload["model"] == GROK
    assert payload["template"] == "video"
    assert payload["arguments"]["duration"] == 2
    assert "loops back to the first frame" in payload["arguments"]["prompt"]


def test_gen_bgremove_takes_the_model_that_does_that_job(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """Not the configured image model: BiRefNet is an image model that makes an image, and
    `models.image` would have sent this to whatever generates pictures."""
    _, payload = run(
        "gen", "bgremove", "--asset", "character/hero", "--in", str(png_at(space)), "--dry-run"
    )
    assert payload["model"] == BIREFNET
    assert payload["template"] is None
    assert payload["stage"] == "nobg"


def test_gen_expand_goes_to_the_editing_endpoint(space: Path, api: FakeClient, keyed: None) -> None:
    _, payload = run(
        "gen",
        "expand",
        "--asset",
        "character/hero",
        "--prompt",
        "more sky",
        "--in",
        str(png_at(space)),
        "--size",
        "1024x1024",
        "--dry-run",
    )
    assert payload["model"] == NANO_EDIT


def test_an_input_from_the_assets_own_chain(space: Path, api: FakeClient, keyed: None) -> None:
    """`--from-stage` addresses a file by what it is rather than by where it sits — the whole
    point of a stage being a name and not a number."""
    run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    _, payload = run(
        "gen", "bgremove", "--asset", "character/hero", "--from-stage", "gen", "--dry-run"
    )
    assert payload["model"] == BIREFNET


def test_naming_neither_input_nor_stage_is_refused(
    space: Path, api: FakeClient, keyed: None
) -> None:
    code, payload = run("gen", "bgremove", "--asset", "character/hero")
    assert code == 2
    assert payload["error"]["code"] == "no-input"


def test_naming_both_is_refused_too(space: Path, api: FakeClient, keyed: None) -> None:
    code, payload = run(
        "gen",
        "bgremove",
        "--asset",
        "character/hero",
        "--from-stage",
        "gen",
        "--in",
        str(png_at(space)),
    )
    assert code == 2
    assert payload["error"]["code"] == "no-input"


def test_a_timeout_that_is_not_a_duration_is_refused(
    space: Path, api: FakeClient, keyed: None
) -> None:
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--timeout", "nan"
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-wait"
    assert api.submitted == []
