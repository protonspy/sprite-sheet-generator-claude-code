"""The style axis — specs/generation-style R1, R2."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ssc.cli import gen, kinds
from ssc.cli import workspace as ws
from ssc.cli.errors import UsageError

SHIPPED = ("pixel-art", "vector", "hand-painted", "3d-render", "flat")


# R1.2 — the five the package ships, each carrying words a model is sent.


def test_every_shipped_style_carries_words() -> None:
    available = gen.styles()

    assert sorted(available) == sorted(SHIPPED)
    assert all(available[name].get("words", "").strip() for name in SHIPPED)


@pytest.mark.parametrize("name", SHIPPED)
def test_a_shipped_name_resolves_to_its_own_words(name: str) -> None:
    style = gen.style_for(name)

    assert style.name == name
    assert style.shipped is True
    assert style.words == gen.styles()[name]["words"]


def test_only_pixel_art_names_a_board() -> None:
    """Words alone do not impose block discipline — docs/wiki/reference-boards.md. No other
    look needs a reference to be itself."""
    assert gen.style_for("pixel-art").board == "checker"
    assert [name for name in SHIPPED if gen.style_for(name).board is not None] == ["pixel-art"]


def test_a_style_says_nothing_about_the_things_a_template_owns() -> None:
    """A style is how the art is drawn. The cell, the chroma field and the watermark rule are
    true whatever it looks like, so a style naming one of them would be two answers to one
    question the next time a template changes."""
    for name in SHIPPED:
        words = gen.style_for(name).words.lower()
        for owned in ("chroma", "watermark", "background", "centred"):
            assert owned not in words, f"{name} names {owned}, which belongs to the template"


# R1.3 — free text is the escape hatch, so the shipped set is a starting point.


def test_a_name_nobody_ships_is_carried_verbatim() -> None:
    style = gen.style_for("chunky claymation, thumbprints visible")

    assert style.shipped is False
    assert style.words == "chunky claymation, thumbprints visible"
    assert style.board is None


def test_free_text_is_stripped_but_not_otherwise_touched() -> None:
    assert gen.style_for("  woodcut print  ").words == "woodcut print"


def test_a_typo_of_a_shipped_name_is_free_text_and_says_so() -> None:
    """The cost of the escape hatch, and the reason `shipped` is reported at all."""
    assert gen.style_for("pixelart").shipped is False


# R1.4 — nothing to apply.


@pytest.mark.parametrize("blank", ["", "   ", "\t"])
def test_a_blank_style_is_refused(blank: str) -> None:
    with pytest.raises(UsageError) as refused:
        gen.style_for(blank)

    assert refused.value.code == "invalid-style"
    assert "pixel-art" in refused.value.fix


# R1.7 — a style is a phrase, and it can arrive from a file nobody in the room wrote.


def test_a_style_past_the_ceiling_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        gen.style_for("woodcut " * gen.MAX_STYLE)

    assert refused.value.code == "invalid-style"
    assert str(gen.MAX_STYLE) in refused.value.message


def test_a_style_declared_in_a_config_is_held_to_the_same_ceiling(tmp_path: Path) -> None:
    """The route that matters: an `ssc.yaml` arrives with a cloned repository as often as it
    is written by whoever is running the command, and a paragraph declared there would ride
    every paid call the kind ever makes without anybody typing it."""
    space = ws.create(tmp_path)
    space.config_path.write_text(
        yaml.safe_dump({"schema": 1, "kinds": {"character": {"style": "x" * 4000}}}),
        encoding="utf-8",
    )

    with pytest.raises(UsageError) as refused:
        gen.style_for(kinds.resolve("character", space).profile.style)

    assert refused.value.code == "invalid-style"


@pytest.mark.parametrize("name", SHIPPED)
def test_every_shipped_style_is_inside_the_ceiling(name: str) -> None:
    assert len(gen.styles()[name]["words"]) <= gen.MAX_STYLE


# R1.5, R1.6 — what a caller is told about the look that was applied.


def call_with(style: gen.Style | None) -> gen.Call:
    return gen.Call(endpoint="fal-ai/x", checked={}, recorded={}, inputs=(), style=style)


def test_the_report_names_the_style_and_says_it_is_one_ssc_ships() -> None:
    reported = call_with(gen.style_for("pixel-art")).report()["style"]

    assert reported == {"name": "pixel-art", "shipped": True, "board": "checker"}


def test_the_report_says_when_the_style_is_free_text() -> None:
    reported = call_with(gen.style_for("woodcut print")).report()["style"]

    assert reported == {"name": "woodcut print", "shipped": False, "board": None}


def test_a_style_that_names_no_board_reports_none() -> None:
    """The seam specs/reference-images/ reads: nothing here sends the board, and a caller
    that will has to be able to see which one without resolving the style again."""
    assert call_with(gen.style_for("vector")).report()["style"]["board"] is None


def test_a_call_with_no_prompt_reports_no_style() -> None:
    """`gen bgremove` carries no prompt, so there is no template and nothing to style."""
    assert call_with(None).report()["style"] is None


# R2.1, R2.2 — the templates stop saying how the art is drawn.

#: `box-art` says its look outright and takes no style: the brief is not drawn in the
#: deliverable's style, which is the point of it. `video` and `walk` animate an image whose
#: look was decided when it was generated.
NO_STYLE_SLOT = ("box-art", "video", "walk")


def image_templates() -> dict[str, str]:
    return {name: body for name, body in gen.templates().items() if name not in NO_STYLE_SLOT}


@pytest.mark.parametrize("name", sorted(image_templates()))
def test_every_image_template_names_a_style_slot(name: str) -> None:
    assert gen.STYLE_SLOT in image_templates()[name]


@pytest.mark.parametrize("name", sorted(image_templates()))
def test_no_image_template_says_how_the_art_is_drawn(name: str) -> None:
    """The failure this catches is silent: a `vector` generation still asking for hard pixel
    edges comes back looking almost right."""
    body = image_templates()[name].lower()

    for baked in ("pixel art", "16-bit", "cel shading", "anti-alias", "painterly", "brushwork"):
        assert baked not in body, f"{name} still names {baked}, which is a style's to say"


def test_the_style_reaches_the_prompt_where_the_template_asks_for_it() -> None:
    filled = gen.prompt_for("character", "a knight", (64, 64), None, gen.style_for("vector"))

    assert "flat vector art" in filled
    assert gen.STYLE_SLOT not in filled


def test_a_style_holding_a_brace_cannot_rewrite_a_slot_filled_before_it() -> None:
    """One pass, the same property `--var` depends on: `re.sub` never revisits what it wrote,
    so free text naming a slot lands as text rather than as a substitution."""
    filled = gen.prompt_for(
        "character", "a knight", (64, 64), None, gen.style_for("as drawn by {name}")
    )

    assert "as drawn by {name}" in filled


def test_a_template_that_takes_no_style_is_left_alone() -> None:
    """Box art states the look it needs, and nothing substitutes over it."""
    body = gen.templates()["box-art"]

    assert gen.STYLE_SLOT not in body
    assert "not pixel art" in body


# R2.1 — and the two that animate rather than draw.


# R3.1, R3.2, R3.3 — the look is a project decision before it is a call decision.


def test_every_built_in_kind_is_pixel_art_until_somebody_says_otherwise() -> None:
    """What every template asserted before this existed, so a workspace that says nothing
    generates exactly what it generated before."""
    assert {profile.style for profile in kinds.BUILT_INS.values()} == {"pixel-art"}


def test_a_project_declares_the_style_of_a_kind(tmp_path: Path) -> None:
    space = ws.create(tmp_path)
    space.config_path.write_text(
        yaml.safe_dump({"schema": 1, "kinds": {"character": {"style": "hand-painted"}}}),
        encoding="utf-8",
    )

    resolved = kinds.resolve("character", space)

    assert resolved.profile.style == "hand-painted"
    assert resolved.source["style"] == kinds.DECLARED
    # field by field: declaring the style keeps the cell, the anchor and the template
    assert resolved.profile.template == "character"
    assert resolved.profile.anchor == "feet"


def test_a_kind_that_declares_nothing_says_where_its_style_came_from(tmp_path: Path) -> None:
    resolved = kinds.resolve("character", ws.create(tmp_path))

    assert resolved.profile.style == "pixel-art"
    assert resolved.source["style"] == kinds.BUILT_IN


def test_a_declared_style_may_be_free_text(tmp_path: Path) -> None:
    """A project's look is not limited to the five names either — `style_for` is one
    function for both routes precisely so the two cannot disagree about that."""
    space = ws.create(tmp_path)
    space.config_path.write_text(
        yaml.safe_dump({"schema": 1, "kinds": {"icon": {"style": "woodcut print"}}}),
        encoding="utf-8",
    )

    assert gen.style_for(kinds.resolve("icon", space).profile.style).shipped is False


@pytest.mark.parametrize("name", ["video", "walk"])
def test_the_video_templates_assert_no_look_of_their_own(name: str) -> None:
    """A clip preserves what the input image is. Saying `the same pixelated sprite look`
    told a hand-painted asset to become something else on its way to being animated."""
    body = gen.templates()[name].lower()

    assert "pixelated" not in body
    assert "the same look" in body
