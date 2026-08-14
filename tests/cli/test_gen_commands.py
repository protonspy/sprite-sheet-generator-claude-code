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

from ssc.cli import budget, fal, frames, jobs, meta, models
from ssc.cli import gen as pipeline
from ssc.cli import workspace as ws
from ssc.cli.app import main
from ssc.cli.atomic import Directory
from ssc.cli.commands import gen as commands
from ssc.cli.errors import UsageError
from ssc.core import board

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
    # `gen` reaches its provider through `commands.provider`; `ssc job resume` reaches one
    # through the registry instead. Patching only the first left every `job` command in this
    # file talking to the real fal client — which failed on a missing credential *before*
    # reaching what the test meant to exercise, so the assertion passed on nothing and the
    # run made a live HTTPS call. Both reviews caught it; this is the fix.
    monkeypatch.setitem(jobs.PROVIDERS, fal.PROVIDER, fal.Fal(api=client))
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


def test_a_named_template_overrides_the_one_the_kind_names(space: Path, api: FakeClient) -> None:
    """R2.7 — one kind, more than one job.

    A `character` is generated several times over its life: the South anchor against a
    pixel-grid board, then the other directions, then the poses. Those want different words
    and they are all the same asset, so the override is per call rather than per kind.
    """
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "anchor",
        *HERO,
        "--dry-run",
    )
    assert payload["template"] == "anchor"
    sent = payload["arguments"]["prompt"]
    assert "South-facing idle" in sent
    assert "64x64" in sent  # still the kind's cell — the override changes words, not facts


def test_the_anchor_template_carries_the_rules_the_wiki_paid_for(
    space: Path, api: FakeClient
) -> None:
    """`docs/wiki/anchor-and-directions.md` has two lessons that cost someone real work, and
    a template that drops them is a template that will cost it again.

    The neutral pose is the expensive one: an object in the anchor becomes attached to the
    body in every frame derived from it, and removing it afterwards is hand-work per frame.
    The board's role is the other: unstated, the model paints the checkerboard into the art.

    The second lesson moved with `specs/reference-images/`: it used to be a sentence in the
    template saying *any image supplied alongside this prompt is a board*, which stopped
    being true the moment a call could carry two. It now travels with the image it is about,
    so it is asserted here where that image is attached.
    """
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "anchor",
        "--board",
        *HERO,
        "--dry-run",
    )
    sent = payload["arguments"]["prompt"]
    assert "every single frame derived from this one" in sent
    assert "never take its content" in sent


def test_box_art_keeps_its_background_where_every_other_template_refuses_one(
    space: Path, api: FakeClient
) -> None:
    """The one template that must not ask for chroma.

    Box art is the character-select illustration and is never cut out, so a chroma key would
    be asking the model to delete the setting that is the point. `docs/wiki/` is equally
    clear that it must not then be fed back as a sprite reference — that is a rule for the
    caller, and the template's job is only to not produce a sprite by accident.
    """
    CliRunner().invoke(main, ["asset", "new", "kael", "--kind", "box-art"])
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "box-art/kael",
        "--prompt",
        "a knight",
        "--var",
        "name=Kael",
        "--var",
        "archetype=frost warden",
        "--var",
        "costume=rime-blue plate",
        "--var",
        "prop=a rune-etched axe",
        "--var",
        "setting=a frozen fen under aurora light",
        "--dry-run",
    )

    sent = payload["arguments"]["prompt"]
    assert payload["template"] == "box-art"
    assert "chroma" not in sent
    assert "1024x1536" in sent
    assert "Painterly" in sent


def test_the_direction_template_names_only_the_direction_and_keeps_the_rest(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """West and North are generated from the approved anchor, and the whole risk is drift:
    a frame that is a slightly different character reads as one character flickering.

    So the template spends its words on preservation and leaves the direction itself to the
    caller's prompt — `docs/wiki/anchor-and-directions.md` is explicit that naming only the
    direction is what works.
    """
    written = png_at(space, "south.png")
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the approved South anchor, turned",
        "--template",
        "direction",
        "--var",
        "name=Kael",
        "--var",
        "direction=West, seen from the character's left",
        "--var",
        "silhouette=the axe head reads against the body, not across it",
        "--ref",
        str(written),
        "--dry-run",
    )
    sent = payload["arguments"]["prompt"]
    assert payload["template"] == "direction"
    assert "facing West" in sent
    assert "read as one character rather than two" in sent
    # The prop rule, which is the one the wiki says gets learned the hard way.
    assert "wrong side of the body" in sent


def test_the_correction_template_preserves_identity_and_strips_the_effect(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The remedy for an anchor that came back holding something.

    The wiki's rule is that an object in the anchor becomes attached to the body in every
    frame derived from it. When a model puts one there anyway, the fix is a second pass that
    changes exactly one thing — so the template spends most of its words on what must *not*
    change, which is the opposite of every other template here.
    """
    written = png_at(space, "bad-anchor.png")
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "neutral-pose",
        "--var",
        "name=Kael",
        "--var",
        "remove=the fireball charged in the right hand",
        "--ref",
        str(written),
        "--dry-run",
    )
    sent = payload["arguments"]["prompt"]
    assert payload["template"] == "neutral-pose"
    assert "identity to preserve" in sent
    assert "every single frame derived from this one" in sent
    assert "Do not redesign the character" in sent


# specs/reference-images R1 — more than one reference, in the order they were given.


def png_named(space: Path, name: str, body: bytes) -> Path:
    """A PNG that is a real PNG and is not the same bytes as the others."""
    path = space / name
    path.write_bytes(PNG + body)
    return path


def test_two_references_both_reach_the_payload_in_order(space: Path, api: FakeClient) -> None:
    """An anchor plus a checkerboard is how every direction after the first is generated, so
    two is the ordinary case rather than the exotic one."""
    anchor = png_named(space, "anchor.png", b"one")
    board = png_named(space, "board.png", b"two")

    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        str(anchor),
        "--ref",
        str(board),
        "--dry-run",
    )

    sent = payload["arguments"]["image_urls"]
    assert [entry["from"] for entry in sent] == ["anchor.png", "board.png"]
    assert payload["model"] == NANO_EDIT


def staged(space: Path, name: str = "001_hero.gen.png", stage: str = "gen") -> None:
    """A file recorded into the asset under a stage, so `--from-stage` can address it."""
    directory = space / "assets" / "character" / "hero"
    (directory / name).write_bytes(PNG + b"staged")
    record = load_meta(directory)
    with Directory.open(directory) as held:
        meta.record(
            record,
            path=name,
            stage=stage,
            file_class="source",
            data=PNG + b"staged",
            produced_by=meta.Provenance(command="test", params={}),
        )
        meta.save(held, record)


def test_a_stage_and_a_file_are_one_ordered_list(space: Path, api: FakeClient) -> None:
    """Stages first, then loose paths — the order a caller builds a call in: the asset's own
    chain is what a direction derives from, and the board is what is added to it."""
    staged(space)

    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        str(png_named(space, "board.png", b"two")),
        "--from-stage",
        "gen",
        "--dry-run",
    )

    sent = payload["arguments"]["image_urls"]
    assert [entry["from"] for entry in sent] == ["001_hero.gen.png", "board.png"]


def test_every_reference_is_uploaded_and_submitted(
    space: Path, api: FakeClient, keyed: None
) -> None:
    code, _ = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        str(png_named(space, "anchor.png", b"one")),
        "--ref",
        str(png_named(space, "board.png", b"two")),
    )

    assert code == 0
    assert len(api.encoded) == 2
    _, arguments = api.submitted[0]
    assert len(arguments["image_urls"]) == 2


def test_a_model_that_takes_one_image_refuses_the_second(space: Path, api: FakeClient) -> None:
    """Refused rather than truncated: the field holds one URL, and sending the first of two
    is a paid call missing half of what it was asked to work from."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--model",
        BIREFNET,
        "--ref",
        str(png_named(space, "anchor.png", b"one")),
        "--ref",
        str(png_named(space, "board.png", b"two")),
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "too-many-references"
    assert "1 image" in payload["error"]["message"] or "one image" in payload["error"]["message"]


def test_the_second_reference_is_part_of_the_key(space: Path, api: FakeClient) -> None:
    """A call differing only in its second image is a different call, and a cache that
    conflated them would file one result under both."""
    anchor = png_named(space, "anchor.png", b"one")
    argv = (
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--ref",
        str(anchor),
    )

    _, alone = run(*argv, "--dry-run")
    _, with_board = run(*argv, "--ref", str(png_named(space, "board.png", b"two")), "--dry-run")

    assert alone["cache_key"] != with_board["cache_key"]


def test_each_reference_is_recorded_by_digest_rather_than_by_its_bytes(
    space: Path, api: FakeClient
) -> None:
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--ref",
        str(png_named(space, "anchor.png", b"one")),
        "--ref",
        str(png_named(space, "board.png", b"two")),
        "--dry-run",
    )

    for entry in payload["arguments"]["image_urls"]:
        assert set(entry) == {"sha256", "bytes", "from"}
    digests = {entry["sha256"] for entry in payload["arguments"]["image_urls"]}
    assert len(digests) == 2


def test_more_references_than_ssc_carries_are_refused_before_any_is_read(
    space: Path, api: FakeClient
) -> None:
    """Before the first read: every reference is resident by the time the pipeline sees the
    list, so a ceiling checked there is a ceiling checked too late."""
    many = [
        argument
        for index in range(pipeline.MAX_REFERENCES + 1)
        for argument in ("--ref", str(space / f"missing-{index}.png"))
    ]

    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", *many, "--dry-run"
    )

    assert code == 2
    assert payload["error"]["code"] == "too-many-references"
    # not `no-input`: nothing was opened, which is the point of checking here
    assert "past" in payload["error"]["message"]


def test_a_reference_over_the_file_ceiling_is_refused(
    space: Path, api: FakeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """From the header rather than after the read, the way a frame set is refused: a file
    past the ceiling must not be resident before anything can decide about it."""
    monkeypatch.setattr(pipeline, "MAX_FILE_BYTES", 8)

    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--ref",
        str(png_named(space, "anchor.png", b"far more than eight bytes")),
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "file-too-large"


# specs/reference-images R2 — what each image is for, said in the prompt.


def test_a_role_says_in_the_prompt_what_the_image_is_for(space: Path, api: FakeClient) -> None:
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        f"{png_named(space, 'anchor.png', b'one')}:identity",
        "--dry-run",
    )

    sent = payload["arguments"]["prompt"]
    assert "The image supplied alongside this prompt is the character to stay faithful to" in sent


def test_two_roles_are_named_in_the_order_the_images_are_sent(space: Path, api: FakeClient) -> None:
    """Nothing in a payload of two URLs says which is the anchor, so the prompt does."""
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        f"{png_named(space, 'anchor.png', b'one')}:identity",
        "--ref",
        f"{png_named(space, 'swatch.png', b'two')}:palette",
        "--dry-run",
    )

    sent = payload["arguments"]["prompt"]
    assert "(1) the character to stay faithful to" in sent
    assert "(2) the colours to work in" in sent
    assert sent.index("(1)") < sent.index("(2)")


def test_an_image_with_no_role_keeps_its_place_in_the_numbering(
    space: Path, api: FakeClient
) -> None:
    """The numbering is the only thing tying a phrase to an image, so an unnamed one is
    listed rather than skipped."""
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        str(png_named(space, "anchor.png", b"one")),
        "--ref",
        f"{png_named(space, 'board.png', b'two')}:board",
        "--dry-run",
    )

    sent = payload["arguments"]["prompt"]
    assert "(1) a reference to derive from" in sent
    assert "(2) a pixel-grid board" in sent


def test_a_reference_with_no_role_at_all_adds_no_sentence(space: Path, api: FakeClient) -> None:
    """One image beside a template that already says what it expects needs no announcement,
    and a sentence saying nothing is words the model spends attention on for nothing."""
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--ref",
        str(png_named(space, "anchor.png", b"one")),
        "--dry-run",
    )

    assert "supplied alongside this prompt" not in payload["arguments"]["prompt"]


def test_a_role_nobody_defined_is_refused(space: Path, api: FakeClient) -> None:
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--ref",
        f"{png_named(space, 'anchor.png', b'one')}:identtiy",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "unknown-role"
    assert "identity" in payload["error"]["fix"]


def test_a_path_that_is_not_a_role_suffix_stays_a_path(space: Path, api: FakeClient) -> None:
    """A colon inside a path is a path — a Windows drive letter is the ordinary case — so
    the suffix is only read as a role where the head names a file that is really there."""
    path, role = commands.split_role(r"C:\art\anchor.png", is_path=True)

    assert (path, role) == (r"C:\art\anchor.png", None)


def test_a_stage_takes_a_role_the_same_way_a_path_does(space: Path, api: FakeClient) -> None:
    staged(space)

    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--from-stage",
        "gen:identity",
        "--dry-run",
    )

    assert payload["references"][0]["role"] == "identity"


def test_a_mistyped_role_on_a_stage_is_refused_as_a_role(space: Path, api: FakeClient) -> None:
    """A stage is a name and no legal one holds a colon, so a suffix was meant to be a role.
    Reading it as part of the stage name refuses for the wrong reason: `unknown-stage` sends
    the caller looking at their asset for something that was never the problem."""
    staged(space)

    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--from-stage",
        "gen:identtiy",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "unknown-role"


def test_every_reference_is_reported_with_its_role(space: Path, api: FakeClient) -> None:
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "the anchor, turned West",
        "--ref",
        f"{png_named(space, 'anchor.png', b'one')}:identity",
        "--ref",
        str(png_named(space, "swatch.png", b"two")),
        "--dry-run",
    )

    assert [(entry["file"], entry["role"]) for entry in payload["references"]] == [
        ("anchor.png", "identity"),
        ("swatch.png", None),
    ]
    assert all(entry["sha256"] for entry in payload["references"])


# specs/reference-images R3 — the board a style names.


def test_the_board_is_generated_and_sent_after_what_the_caller_named(
    space: Path, api: FakeClient
) -> None:
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--ref",
        f"{png_named(space, 'anchor.png', b'one')}:identity",
        "--board",
        "--dry-run",
    )

    assert [entry["file"] for entry in payload["references"]] == ["anchor.png", "checker.png"]
    assert payload["references"][-1]["role"] == "board"
    assert "a pixel-grid board" in payload["arguments"]["prompt"]


def test_the_board_alone_still_moves_the_call_to_the_editing_endpoint(
    space: Path, api: FakeClient
) -> None:
    """The board is an image this call carries and the ask does not name, so routing off the
    ask alone would send it to the endpoint that takes no image at all."""
    _, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--board", "--dry-run"
    )

    assert payload["model"] == NANO_EDIT
    assert [entry["file"] for entry in payload["references"]] == ["checker.png"]


def test_the_board_is_the_same_image_tool_board_checker_draws(space: Path, api: FakeClient) -> None:
    """Generated rather than vendored, and by the same function, so the two commands cannot
    drift into drawing two different boards."""
    drawn, _ = board.checkerboard(pipeline.BOARD_SQUARE, *pipeline.BOARD_SIZE)
    reference = pipeline.board_for(pipeline.style_for("pixel-art"), None)

    assert reference.image.data == frames.encode(drawn)
    assert reference.role == "board"


def test_a_board_past_the_side_tool_board_holds_one_to_is_refused(
    space: Path, api: FakeClient
) -> None:
    """`build` runs before the dry-run report, before the cache and before the budget, so an
    unbounded side here is an allocation big enough to take the process down without a call
    being made. The bound is `tool board checker`'s, taken from there rather than restated."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--board",
        "--size",
        "99999x99999",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-size"
    assert api.submitted == []


def test_a_style_that_names_no_board_refuses_the_flag(space: Path, api: FakeClient) -> None:
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--style",
        "vector",
        "--board",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "no-board"
    assert "tool board checker" in payload["error"]["fix"]


# specs/reference-images R4.1 — a board cannot be expressed on a video call.


def test_a_video_call_takes_one_image_and_offers_no_board() -> None:
    """A video model given a grid paints the grid onto the character. The wiki's argument for
    two commands rather than one with a flag is that a mistake which cannot be expressed
    cannot be made under time pressure — so this asserts the surface, not a refusal."""
    repeatable = {parameter.name for parameter in commands.gen_video.params if parameter.multiple}

    assert "board" not in {parameter.name for parameter in commands.gen_video.params}
    # `--opt` and `--var` are repeatable and neither carries an image; nothing that does is.
    assert repeatable == {"options", "variables"}
    assert "references" not in repeatable and "stages" not in repeatable


# specs/generation-style R1.1, R2.3, R3.2, R3.3 — how the art is drawn, on the command line.


def test_the_kinds_style_is_what_a_call_uses_when_nobody_says(space: Path, api: FakeClient) -> None:
    """Nothing declared and nothing passed, so a workspace generates what it always did."""
    _, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )

    assert payload["style"] == {"name": "pixel-art", "shipped": True, "board": "checker"}
    assert "16-bit console sprite work" in payload["arguments"]["prompt"]


def test_a_style_on_the_call_overrides_the_one_the_kind_names(space: Path, api: FakeClient) -> None:
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--style",
        "hand-painted",
        "--dry-run",
    )

    sent = payload["arguments"]["prompt"]
    assert payload["style"]["name"] == "hand-painted"
    assert "visible brushwork" in sent
    assert "16-bit" not in sent
    # the template's own half is untouched by the look
    assert "chroma-green" in sent and "64x64" in sent


def test_free_text_reaches_the_model_and_is_reported_as_unshipped(
    space: Path, api: FakeClient
) -> None:
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--style",
        "torn paper collage",
        "--dry-run",
    )

    assert payload["style"] == {"name": "torn paper collage", "shipped": False, "board": None}
    assert "torn paper collage" in payload["arguments"]["prompt"]


def test_a_project_that_declares_a_style_generates_in_it(space: Path, api: FakeClient) -> None:
    (space / "ssc.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "models": {"image": NANO, "video": GROK},
                "kinds": {"character": {"style": "vector"}},
            }
        ),
        encoding="utf-8",
    )

    _, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )

    assert payload["style"]["name"] == "vector"
    assert "flat vector art" in payload["arguments"]["prompt"]


def test_gen_expand_inherits_the_kinds_style_and_takes_no_flag_of_its_own(
    space: Path, api: FakeClient
) -> None:
    """Outpainting goes through the kind's own template, so it says what the asset is drawn
    in. The look is not a thing to pick again halfway through extending a canvas — which is
    why there is no `--style` here and the kind's answer is the whole of it."""
    (space / "ssc.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "models": {"image": NANO, "video": GROK},
                "kinds": {"character": {"style": "hand-painted"}},
            }
        ),
        encoding="utf-8",
    )

    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--dry-run",
    )
    assert "visible brushwork" in payload["arguments"]["prompt"]

    _, expanded = run(
        "gen",
        "expand",
        "--asset",
        "character/hero",
        "--prompt",
        "more of the frozen fen",
        "--in",
        str(png_at(space)),
        "--dry-run",
    )
    assert "visible brushwork" in expanded["arguments"]["prompt"]
    assert expanded["style"]["name"] == "hand-painted"


def test_a_style_against_a_template_that_takes_none_is_refused_before_the_money(
    space: Path, api: FakeClient
) -> None:
    """R2.3 — box art states the look it needs, so `--style` would never reach the model.
    Silently ignoring it is a paid image that is not what was asked for."""
    CliRunner().invoke(main, ["asset", "new", "kael", "--kind", "box-art"])

    code, payload = run(
        "gen",
        "image",
        "--asset",
        "box-art/kael",
        "--prompt",
        "a knight",
        "--style",
        "vector",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "style-not-taken"
    assert api.submitted == []


def test_a_blank_style_is_refused_before_the_money(space: Path, api: FakeClient) -> None:
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--style",
        "   ",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-style"
    assert api.submitted == []


# R2.8 — the named slots, and the refusal that keeps `{name}` out of a paid prompt.


HERO = (
    "--var",
    "name=Kael",
    "--var",
    "archetype=frost warden",
    "--var",
    "costume=rime-blue plate",
    "--var",
    "prop=a rune-etched axe",
    "--var",
    "silhouette=a heavy pauldron on the left shoulder",
)


def test_a_template_fills_its_named_slots_from_var(space: Path, api: FakeClient) -> None:
    """The structured half. What recurs across the character templates gets a name; anything
    that does not is prose, and prose stays in `--prompt`."""
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "standing on cracked ice",
        "--template",
        "anchor",
        *HERO,
        "--dry-run",
    )
    sent = payload["arguments"]["prompt"]
    assert "Kael" in sent and "frost warden" in sent
    assert "rime-blue plate" in sent and "rune-etched axe" in sent
    assert "heavy pauldron on the left shoulder" in sent
    assert "standing on cracked ice" in sent  # the free text is still there
    assert "{" not in sent.split("standing on cracked ice")[-1]


def test_a_template_missing_a_slot_is_refused_before_the_money(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The whole reason the vocabulary is closed and checked.

    Substituting nothing would send the literal text `{name}` to the model inside a prompt
    that is then billed, and the image that came back would be plausible enough that nobody
    looked. The refusal names every slot still empty, so one run fixes all of them.
    """
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "anchor",
        "--var",
        "name=Kael",
    )
    assert code == 2
    assert payload["error"]["code"] == "missing-variable"
    for slot in ("archetype", "costume", "prop", "silhouette"):
        assert slot in payload["error"]["message"]
    assert api.submitted == []


def test_a_slot_that_is_not_a_variable_is_refused(space: Path, api: FakeClient) -> None:
    """A closed vocabulary is the point: an open one drifts into a second prompt language
    nobody documents, and a typo would be silently substituted into nothing."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--var",
        "biome=a frozen fen",
        "--dry-run",
    )
    assert code == 2
    assert payload["error"]["code"] == "unknown-variable"
    assert "setting" in payload["error"]["fix"]


def test_a_brace_in_the_callers_own_prompt_is_not_a_variable(space: Path, api: FakeClient) -> None:
    """Substitution order, asserted. Somebody writing "a knight {holding a torch}" is
    describing a knight — checking the finished string for leftover braces would refuse them
    for punctuation."""
    _, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight {holding a torch}",
        "--dry-run",
    )
    assert "{holding a torch}" in payload["arguments"]["prompt"]


def test_a_template_that_names_no_slot_needs_no_var(space: Path, api: FakeClient) -> None:
    """Every asset template — icon, tile, ui, banner, map — names nothing, so none of this
    reaches a caller who was not asking for it."""
    CliRunner().invoke(main, ["asset", "new", "grass", "--kind", "tile"])
    code, payload = run("gen", "image", "--asset", "tile/grass", "--prompt", "moss", "--dry-run")
    assert code == 0
    assert "moss" in payload["arguments"]["prompt"]


def test_a_variable_the_template_does_not_use_is_not_an_error(space: Path, api: FakeClient) -> None:
    """The asymmetry is deliberate: a missing slot is a broken prompt and a spare one is not.

    One config driving several templates is the ordinary way to work — the same character
    generated as an anchor, then a direction, then box art — and refusing the spares would
    punish it for no gain.
    """
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "neutral-pose",
        "--var",
        "name=Kael",
        "--var",
        "remove=the fireball in the right hand",
        "--var",
        "setting=a frozen fen",
        "--dry-run",
    )
    assert code == 0
    assert "Kael" in payload["arguments"]["prompt"]


def test_one_slots_value_cannot_be_rewritten_by_another_slot(space: Path) -> None:
    """Substitution is one pass, and this is why.

    Slot-by-slot `str.replace` lets each replacement rewrite text an earlier one just
    inserted: with `prop` supplied after `name`, a `name` value of `{prop}` came out holding
    `prop`'s text. Order-dependent, undocumented, and reachable by ordinary use — both
    reviews found it independently, from different directions.
    """
    filled = pipeline.prompt_for(
        "anchor",
        "a knight",
        (64, 64),
        {
            "name": "Kael",
            "archetype": "frost warden",
            "costume": "rime-blue plate",
            "prop": "a rune-etched axe",
            "silhouette": "a heavy pauldron",
        },
    )
    assert "Kael" in filled and "a rune-etched axe" in filled
    assert "{" not in filled.replace("{prompt}", "")


def test_a_value_that_is_itself_a_slot_is_refused(space: Path, api: FakeClient) -> None:
    """The case the empty check could not see, and the expensive one.

    `--var prop="a sword engraved with {name}"` is plausible flavour text rather than an
    exotic payload, and it is not empty, so `missing-variable` passed it. One pass then
    inserts it verbatim and the literal `{name}` reaches the model inside a billed prompt —
    the exact outcome R2.8 exists to prevent, arriving by a different door.
    """
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "anchor",
        "--var",
        "name=Kael",
        "--var",
        "prop=a sword engraved with {name}",
        "--dry-run",
    )
    assert code == 2
    assert payload["error"]["code"] == "invalid-variable"
    assert "upstream" in payload["error"]["fix"]


def test_the_order_slots_are_given_in_does_not_change_the_prompt(space: Path) -> None:
    """The other face of the same non-atomicity: reversed, the old loop merged two slots
    instead of leaving one literal. One pass makes the argument order irrelevant."""
    values = {
        "name": "Kael",
        "archetype": "frost warden",
        "costume": "rime-blue plate",
        "prop": "a rune-etched axe",
        "silhouette": "a heavy pauldron",
    }
    forwards = pipeline.prompt_for("anchor", "a knight", (64, 64), values)
    backwards = pipeline.prompt_for("anchor", "a knight", (64, 64), dict(reversed(values.items())))
    assert forwards == backwards


def test_a_template_ssc_does_not_ship_is_refused_and_names_the_ones_it_does(
    space: Path, api: FakeClient
) -> None:
    """The override is a free-text flag, so a typo is the ordinary case rather than the odd
    one — and a typo that reached the model would be a billed call framed by nothing."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--template",
        "anchour",
        "--dry-run",
    )
    assert code == 2
    assert payload["error"]["code"] == "unknown-template"
    assert "anchor" in payload["error"]["fix"]


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


# --------------------------------------- named options  specs/model-options/ R3.2, R3.3, R3.4


def test_a_count_past_what_the_model_offers_is_refused_before_it_bills(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The TDD task of this leaf. `--count` multiplies what one call costs, so the ceiling has
    to be enforced where the schema states it and before anything is submitted: nine images at
    a model that makes four is a rejected call that was already paid for."""
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--count", "9"
    )

    assert code == 2
    assert payload["error"]["code"] == "invalid-option"
    assert "4" in payload["error"]["message"]
    assert api.submitted == []
    assert list((space / "jobs").glob("*.json")) == []


def test_a_count_the_model_offers_reaches_it_under_its_own_name(
    space: Path, api: FakeClient
) -> None:
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--count",
        "2",
        "--dry-run",
    )

    assert code == 0
    assert payload["arguments"]["num_images"] == 2


def test_a_format_reaches_the_model_s_own_field(space: Path, api: FakeClient) -> None:
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--format",
        "webp",
        "--dry-run",
    )

    assert code == 0
    assert payload["arguments"]["output_format"] == "webp"


def test_a_quality_at_a_model_that_has_none_is_refused_by_name(
    space: Path, api: FakeClient
) -> None:
    """Nano Banana 2 has no quality tier. Dropping the option silently is the failure
    `model-registry` R2.4 exists to prevent — a caller cannot tell it did not happen."""
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--quality",
        "medium",
        "--dry-run",
    )

    assert code == 2
    assert payload["error"]["code"] == "no-such-concept"
    assert "quality" in payload["error"]["message"]


def test_a_quality_reaches_a_model_that_has_one(space: Path, api: FakeClient) -> None:
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--model",
        "openai/gpt-image-2",
        "--quality",
        "medium",
        "--dry-run",
    )

    assert code == 0
    assert payload["arguments"]["quality"] == "medium"


def test_an_option_nobody_named_is_left_to_the_model(space: Path, api: FakeClient) -> None:
    """R3.5 — absent means the model's own default, not this project's opinion of one."""
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )

    assert code == 0
    assert "num_images" not in payload["arguments"]
    assert "output_format" not in payload["arguments"]


# -------------------------------------- more than one image  specs/model-options/ R5.1 to R5.4


def three_images(api: FakeClient) -> None:
    api.payload = {
        "images": [
            {"url": "https://v3.fal.media/files/a.png"},
            {"url": "https://v3.fal.media/files/b.png"},
            {"url": "https://v3.fal.media/files/c.png"},
        ]
    }


def test_every_image_a_call_produced_is_filed(space: Path, api: FakeClient, keyed: None) -> None:
    """The TDD task of this leaf, and the reason it is one: `--count 3` bills three times, and
    filing the first while dropping two is money spent on files nobody can find."""
    three_images(api)
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--count", "3"
    )

    assert code == 0
    assert [entry["stage"] for entry in payload["files"]] == ["gen-1", "gen-2", "gen-3"]
    assert [entry["file"] for entry in payload["files"]] == [
        "001_hero.gen-1.png",
        "002_hero.gen-2.png",
        "003_hero.gen-3.png",
    ]
    for entry in payload["files"]:
        assert (space / "assets" / "character" / "hero" / entry["file"]).read_bytes() == PNG

    recorded = asset_meta(space)
    assert [item.stage for item in recorded.files] == ["gen-1", "gen-2", "gen-3"]
    assert {item.file_class for item in recorded.files} == {"source"}


def test_one_image_keeps_the_stage_it_was_asked_for(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The suffix is for a set. A single result is the overwhelming case and `--from-stage gen`
    has to keep meaning what it meant."""
    code, payload = run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")

    assert code == 0
    assert payload["file"] == "001_hero.gen.png"
    assert [entry["stage"] for entry in payload["files"]] == ["gen"]


def test_a_second_identical_call_writes_the_whole_set_from_the_cache(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R5.3 — the cache has to hold the set, or the second call pays three times again."""
    three_images(api)
    argv = ("gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--count", "3")
    assert run(*argv)[0] == 0
    api.submitted.clear()

    CliRunner().invoke(main, ["asset", "new", "twin", "--kind", "character"])
    code, payload = run(
        "gen", "image", "--asset", "character/twin", "--prompt", "a knight", "--count", "3"
    )

    assert code == 0
    assert payload["cached"] is True
    assert api.submitted == []
    assert [entry["stage"] for entry in payload["files"]] == ["gen-1", "gen-2", "gen-3"]
    for entry in payload["files"]:
        assert (space / "assets" / "character" / "twin" / entry["file"]).read_bytes() == PNG


# ------------------------------------------- kind defaults  specs/model-options/ R4.1 to R4.3


def defaulting(space: Path, options: dict[str, Any], model: str = NANO) -> None:
    """Rewrite the workspace's config so `character` starts from these options."""
    (space / "ssc.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": 1,
                "models": {"image": model, "video": GROK},
                "kinds": {"character": {"options": options}},
            }
        ),
        encoding="utf-8",
    )


def test_a_kind_s_default_reaches_a_call_that_did_not_name_it(space: Path, api: FakeClient) -> None:
    defaulting(space, {"format": "webp", "count": 2})
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )

    assert code == 0
    assert payload["arguments"]["output_format"] == "webp"
    assert payload["arguments"]["num_images"] == 2
    assert payload["skipped_defaults"] == []


def test_the_command_line_beats_the_kind(space: Path, api: FakeClient) -> None:
    defaulting(space, {"format": "webp"})
    code, payload = run(
        "gen",
        "image",
        "--asset",
        "character/hero",
        "--prompt",
        "a knight",
        "--format",
        "png",
        "--dry-run",
    )

    assert code == 0
    assert payload["arguments"]["output_format"] == "png"


def test_a_default_the_model_does_not_have_is_skipped_and_said_to_be(
    space: Path, api: FakeClient
) -> None:
    """R4.2. Nano Banana 2 has no quality tier, and a kind that sets one is still a legitimate
    kind — it has to work at both models. So this is the one case that drops an option, and it
    is reported for exactly that reason."""
    defaulting(space, {"quality": "medium", "format": "webp"})
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )

    assert code == 0
    assert "quality" not in payload["arguments"]
    assert payload["arguments"]["output_format"] == "webp"
    assert payload["skipped_defaults"] == ["quality"]


def test_the_same_default_applies_at_a_model_that_has_it(space: Path, api: FakeClient) -> None:
    defaulting(space, {"quality": "medium"}, model="openai/gpt-image-2")
    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--dry-run"
    )

    assert code == 0
    assert payload["arguments"]["quality"] == "medium"
    assert payload["skipped_defaults"] == []


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

    # Two writers record before the call now rather than one: `budget.reserve` writes the job
    # as counted, so the ceiling is decided and published in a single step, and `jobs.submit`
    # writes it again immediately before calling. The assertion is therefore the boundary R1.1
    # actually protects — nothing reaches the provider until a record exists — rather than a
    # fixed index, which would break each time a writer is added ahead of it.
    assert "submit" in calls
    first_submit = calls.index("submit")
    assert first_submit > 0
    assert all(entry.startswith("save:") for entry in calls[:first_submit])
    assert calls[first_submit - 1] == "save:submitted:None"


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


# ------------------------------------------------------ the money guard  R1, R2, R3


def budgeted(space: Path, **limits: Any) -> None:
    """Put a `budget:` into the workspace's `ssc.yaml`, keeping what is already there."""
    document = yaml.safe_load((space / "ssc.yaml").read_text(encoding="utf-8"))
    document["budget"] = limits
    (space / "ssc.yaml").write_text(yaml.safe_dump(document), encoding="utf-8")


def test_a_paid_call_a_free_command_covers_is_refused(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """`specs/budget-guard/` R1.1, and it is first in `gen.run` on purpose: this workspace
    declares no ceiling at all, and it still must not pay for a `np.pad`."""
    code, payload = run(
        "gen", "expand", "--asset", "character/hero", "--prompt", "", "--in", str(png_at(space))
    )
    assert code == 2
    assert payload["error"]["code"] == "free-path"
    assert "tool expand" in payload["error"]["fix"]
    assert api.submitted == []


def test_the_free_path_is_checked_before_the_cache_and_the_ceiling(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """Order, asserted rather than assumed.

    Each refusal tested alone would pass with them in any order. This one pins the free path
    ahead of everything: the workspace is over its ceiling *and* the call is free, and the
    answer a caller can act on is the free command, not "you are out of money".
    """
    budgeted(space, max_usd=0.0)
    code, payload = run(
        "gen", "expand", "--asset", "character/hero", "--prompt", "", "--in", str(png_at(space))
    )
    assert code == 2
    assert payload["error"]["code"] == "free-path"


def test_a_cached_result_is_not_refused_for_being_over_budget(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R2.2 sits *after* the cache, and this is why: a hit submits nothing, so refusing one
    for being over budget would be refusing to spend nothing."""
    run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    budgeted(space, max_usd=0.0)

    code, payload = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--stage", "again"
    )
    assert code == 0
    assert payload["cached"] is True and payload["submitted"] is False
    assert len(api.submitted) == 1


def test_a_workspace_at_its_ceiling_refuses_the_next_call(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R2.2 end to end. No provider publishes a price, so this — the money already spent —
    is the check that actually stops a run."""
    budgeted(space, max_usd=1.0)
    budget.record(ws.require(space), 1.0)

    code, payload = run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    assert code == 2
    assert payload["error"]["code"] == "over-budget"
    assert api.submitted == []


def test_a_collected_call_is_added_to_the_total(space: Path, api: FakeClient, keyed: None) -> None:
    """R3.2, R3.3 — the fake provider reports no cost, which is the ordinary case and must
    be counted as unpriced rather than as free."""
    _, payload = run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")
    assert payload["budget"]["calls"] == 1
    assert payload["budget"]["unpriced"] == 1
    assert payload["budget"]["spent_usd"] == 0.0


def test_dry_run_reports_the_free_command_and_spends_nothing(space: Path, api: FakeClient) -> None:
    """R1.4 — this is the agent's interface: seeing that a call is unnecessary before it is
    made is the whole value, and `--dry-run` needs no credential to say so."""
    _, payload = run(
        "gen",
        "expand",
        "--asset",
        "character/hero",
        "--prompt",
        "",
        "--in",
        str(png_at(space)),
        "--dry-run",
    )
    assert payload["dry_run"] is True
    assert "tool expand" in payload["free_path"]
    assert api.submitted == []


def test_ssc_budget_reports_the_total_and_what_it_does_not_know(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """R3.1, R3.3."""
    budgeted(space, max_usd=5.0, warn_at=4.0)
    run("gen", "image", "--asset", "character/hero", "--prompt", "a knight")

    code, payload = run("budget")
    assert code == 0
    assert payload["calls"] == 1 and payload["unpriced"] == 1
    assert payload["max_usd"] == 5.0 and payload["warn_at"] == 4.0
    assert payload["remaining_usd"] == 5.0


def test_a_no_wait_call_is_counted_when_it_is_submitted(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The critical the second security round returned, and the reason counting moved.

    Counting on collection closed the "invisible for ever" hole and left "invisible until
    collected" — so a caller looping `--no-wait` billed the provider indefinitely while the
    ceiling compared against a total that never moved. The money is committed when `submit`
    returns, so that is when the call is counted.
    """
    _, submitted = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait"
    )
    assert submitted["budget"]["calls"] == 1
    assert budget.load(ws.require(space)).calls == 1


def test_a_ceiling_sees_calls_nobody_ever_collected(
    space: Path, api: FakeClient, keyed: None
) -> None:
    """The loop the finding described, run: submit without ever collecting, and the total
    still grows. Before the fix this stayed at zero however many calls were billed."""
    for _ in range(3):
        run("gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait")

    total = budget.load(ws.require(space))
    assert total.calls == 3 and total.unpriced == 3
    assert len(api.submitted) == 3


def test_a_result_collected_twice_is_billed_once(space: Path, api: FakeClient, keyed: None) -> None:
    """The other half of the same fix. Closing the `--no-wait` hole by counting on every
    collecting route would count one call twice — `gen collect` and then `job resume` — so
    the job carries whether it has been counted."""
    _, submitted = run(
        "gen", "image", "--asset", "character/hero", "--prompt", "a knight", "--no-wait"
    )
    job_id = submitted["job"]["id"]
    run("gen", "collect", job_id, "--asset", "character/hero", "--stage", "gen")
    resumed_code, _ = run("job", "resume", job_id)

    assert resumed_code == 0  # the route was actually reached, not erroring out early
    assert budget.load(ws.require(space)).calls == 1
