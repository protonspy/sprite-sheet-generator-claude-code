"""Reconciling a layout's size against a model's: `specs/gen-fal/` R3.1, R3.2.

The TDD task of this leaf, and the argument for it is in `specs/gen-fal/tasks.md`: pick the
wrong member of GPT Image 1.5's three-value enum and the model returns a plausible image with
the sprites squashed, the job is billed, and nothing in the output says the aspect changed.

The registry is the shipped one with the fetch stubbed out, so these are the real schemas and
no test reaches the network.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ssc.cli import gen, kinds, models
from ssc.cli.errors import SscError, UsageError
from ssc.cli.gen import reconcile_size

GPT = "fal-ai/gpt-image-1.5"
NANO = "fal-ai/nano-banana-2"
GROK = "xai/grok-imagine-video/image-to-video"
BIREFNET = "fal-ai/birefnet/v2"


@pytest.fixture
def registry() -> models.Registry:
    return models.load(fetch=lambda _: None)


def resolve(registry: models.Registry, endpoint: str, requested: tuple[int, int] | None):
    return reconcile_size(registry, endpoint, requested)


def test_a_size_nobody_asked_for_sets_nothing(registry: models.Registry) -> None:
    """A caller who did not ask for a size gets the model's own default, not this project's
    opinion of one."""
    assert resolve(registry, GPT, None) is None


def test_an_exact_member_of_the_enum_is_chosen_unchanged(registry: models.Registry) -> None:
    chosen = resolve(registry, GPT, (1024, 1024))
    assert chosen is not None
    assert chosen.fields == {"image_size": "1024x1024"}
    assert chosen.report["aspect_error"] == pytest.approx(0.0)


def test_the_enum_is_matched_by_shape_and_not_by_pixels(registry: models.Registry) -> None:
    """1200x800 is 3:2 and is not a size GPT Image 1.5 offers; 1536x1024 is the same shape,
    and the shape is what a pose board's layout actually needs."""
    chosen = resolve(registry, GPT, (1200, 800))
    assert chosen is not None
    assert chosen.fields == {"image_size": "1536x1024"}
    assert chosen.report["aspect_error"] == pytest.approx(0.0)


def test_a_portrait_request_does_not_come_back_landscape(registry: models.Registry) -> None:
    chosen = resolve(registry, GPT, (800, 1200))
    assert chosen is not None
    assert chosen.fields == {"image_size": "1024x1536"}


def test_a_near_miss_is_taken_and_the_distance_is_reported(registry: models.Registry) -> None:
    """1100x1000 is 1.1:1. Square is the nearest thing offered, and a caller has to be able
    to see that 10% of stretch was accepted on their behalf."""
    chosen = resolve(registry, GPT, (1100, 1000))
    assert chosen is not None
    assert chosen.fields == {"image_size": "1024x1024"}
    assert chosen.report["aspect_error"] == pytest.approx(0.1, abs=0.01)
    assert chosen.report["requested"] == "1100x1000"
    assert chosen.report["chosen"] == "1024x1024"


def test_a_six_by_one_board_is_refused_rather_than_squashed(registry: models.Registry) -> None:
    """The finding `docs/wiki/model-parameters.md` records: six cells in a row is 6:1, the
    widest thing GPT Image 1.5 offers is 3:2, and there is no honest answer but a refusal
    naming what it does offer."""
    with pytest.raises(UsageError) as refused:
        resolve(registry, GPT, (1536, 256))
    assert refused.value.code == "size-unrepresentable"
    assert "1536x1024" in (refused.value.fix or "")


def test_a_ratio_model_is_asked_in_ratios(registry: models.Registry) -> None:
    chosen = resolve(registry, NANO, (768, 512))
    assert chosen is not None
    assert chosen.fields["aspect_ratio"] == "3:2"
    assert chosen.report["aspect_error"] == pytest.approx(0.0)


def test_the_resolution_tier_is_the_smallest_that_covers_the_request(
    registry: models.Registry,
) -> None:
    assert resolve(registry, NANO, (768, 512)).fields["resolution"] == "1K"  # type: ignore[union-attr]
    assert resolve(registry, NANO, (1600, 1600)).fields["resolution"] == "2K"  # type: ignore[union-attr]
    assert resolve(registry, NANO, (400, 400)).fields["resolution"] == "0.5K"  # type: ignore[union-attr]


def test_a_request_above_every_tier_takes_the_largest_and_says_so(
    registry: models.Registry,
) -> None:
    """Scale is the part that can be fixed afterwards — nearest neighbour is in this project
    already — so this is a report rather than a refusal. Aspect is the part that cannot."""
    chosen = resolve(registry, NANO, (8000, 8000))
    assert chosen is not None
    assert chosen.fields["resolution"] == "4K"
    assert chosen.report["below_request"] is True


def test_the_video_model_uses_its_own_tiers(registry: models.Registry) -> None:
    chosen = resolve(registry, GROK, (1280, 720))
    assert chosen is not None
    assert chosen.fields["aspect_ratio"] == "16:9"
    assert chosen.fields["resolution"] == "720p"


def test_a_model_with_no_size_refuses_a_size(registry: models.Registry) -> None:
    """BiRefNet takes an image and gives one back; a `--size` at it is a caller believing
    something about the call that is not true."""
    with pytest.raises(UsageError) as refused:
        resolve(registry, BIREFNET, (512, 512))
    assert refused.value.code == "no-size"


# R2.5, R2.6 — the refusals that stop a call being built at all. Each guards money in the
# same quiet way: a wrongly-permitted call is submitted, billed, and comes back plausible.


def profile_named(template: str = "character") -> kinds.Profile:
    return kinds.Profile(name="character", template=template)


def without(registry: models.Registry, *endpoints: str) -> models.Registry:
    """The registry minus some models, for the refusals the shipped four cannot reach.

    Every model this project ships that takes an image has an `/edit` beside it, which is
    why `no-edit-endpoint` had no test: it is unreachable with the real registry and very
    reachable with a project that configures its own model. Removing one is how the branch
    gets exercised without asserting something untrue about the shipped set.
    """
    keep = [model for model in registry.models if model.endpoint not in endpoints]
    return replace(registry, models=keep)


def test_an_image_at_a_model_with_no_editing_endpoint_is_refused(
    registry: models.Registry,
) -> None:
    """R2.6's negative half — "shall refuse when that model has none".

    The alternative is worse than an error: the image is quietly dropped, the call is
    submitted against a text-only endpoint, the job is billed, and what comes back ignored
    the reference the caller passed.
    """
    ask = gen.Ask(
        verb="gen image",
        media="image",
        stage="gen",
        prompt="a knight",
        model=GPT,
        image=gen.Image(path=Path("a.png"), data=b"bytes", content_type="image/png"),
    )
    with pytest.raises(UsageError) as refused:
        gen.build(without(registry, f"{GPT}/edit"), ask, profile_named(), {})
    assert refused.value.code == "no-edit-endpoint"
    assert f"{GPT}/edit" in refused.value.message


def test_an_image_reaches_the_editing_endpoint_when_there_is_one(
    registry: models.Registry,
) -> None:
    """The positive half, stated beside the negative one so the pair reads as one decision:
    passing a reference image is a different endpoint, not a different parameter."""
    ask = gen.Ask(
        verb="gen image",
        media="image",
        stage="gen",
        prompt="a knight",
        model=GPT,
        image=gen.Image(path=Path("a.png"), data=b"bytes", content_type="image/png"),
    )
    assert gen.build(registry, ask, profile_named(), {}).endpoint == f"{GPT}/edit"


def test_an_option_colliding_with_the_chosen_size_is_refused(
    registry: models.Registry,
) -> None:
    """Two answers to one question. Letting `--opt` win silently would mean the reported
    size and the submitted size disagree, which is the one thing `--dry-run` exists to
    prevent."""
    ask = gen.Ask(
        verb="gen image",
        media="image",
        stage="gen",
        prompt="a knight",
        model=GPT,
        size=(1024, 1024),
        options={"image_size": "1536x1024"},
    )
    with pytest.raises(UsageError) as refused:
        gen.build(registry, ask, profile_named(), {})
    assert refused.value.code == "size-conflict"
    assert "image_size" in refused.value.message


def test_one_model_in_a_role_is_chosen_without_being_named(
    registry: models.Registry,
) -> None:
    """`gen bgremove` picks by role rather than by media: BiRefNet is an image model that
    returns an image, so asking for "the image model" would send it to a generator."""
    assert gen.by_role(registry, "background-removal") == BIREFNET


def test_a_role_no_model_fills_is_refused_rather_than_guessed(
    registry: models.Registry,
) -> None:
    with pytest.raises(SscError) as refused:
        gen.by_role(registry, "upscaling")
    assert refused.value.code == "no-model-configured"


def test_a_role_more_than_one_model_fills_makes_the_caller_pick(
    registry: models.Registry,
) -> None:
    """Guessing between two models a caller has both configured is guessing with their
    money, so the refusal names them and asks for `--model`."""
    contested = [
        replace(model, role="background-removal") if model.endpoint in {BIREFNET, NANO} else model
        for model in registry.models
    ]
    with pytest.raises(UsageError) as refused:
        gen.by_role(replace(registry, models=contested), "background-removal")
    assert refused.value.code == "ambiguous-model"
    assert BIREFNET in refused.value.message and NANO in refused.value.message
