"""The index model — specs/engine-index R1, R2, R3."""

from __future__ import annotations

import pytest

from ssc.cli import index
from ssc.cli.errors import SscError
from ssc.cli.sidecar import Section

WHERE = "character/hero-attack"


# R2.4, R2.5 — a section is a pair of inclusive frame numbers, and the set decides whether
# it is a real one. Written before `resolve_sections` existed, and watched fail.


def test_sections_of_a_set_that_has_them() -> None:
    sections = (Section("hit", 3, 4), Section("windup", 0, 2))
    assert index.resolve_sections(sections, frames=8, where=WHERE) == sections


def test_a_section_may_cover_the_whole_set() -> None:
    # Inclusive at both ends: over eight frames the last one is 7, not 8. This is the
    # off-by-one the requirement exists to pin down.
    sections = (Section("all", 0, 7),)
    assert index.resolve_sections(sections, frames=8, where=WHERE) == sections


def test_a_set_with_no_sections() -> None:
    assert index.resolve_sections((), frames=8, where=WHERE) == ()


def test_a_single_frame_section() -> None:
    sections = (Section("impact", 4, 4),)
    assert index.resolve_sections(sections, frames=8, where=WHERE) == sections


def refusal(section: Section, frames: int) -> SscError:
    with pytest.raises(SscError) as raised:
        index.resolve_sections((section,), frames=frames, where=WHERE)
    assert raised.value.code == "section-out-of-range"
    # R2.5 — the section and the count, because "out of range" without both is a message
    # that sends the author back to count the frames themselves.
    assert section.name in raised.value.message
    assert str(frames) in raised.value.message
    assert WHERE in raised.value.message
    return raised.value


def test_a_last_frame_one_past_the_end() -> None:
    refusal(Section("hit", 3, 8), frames=8)


def test_a_first_frame_past_the_end() -> None:
    refusal(Section("hit", 9, 9), frames=8)


def test_any_section_at_all_over_an_empty_set() -> None:
    refusal(Section("hit", 0, 0), frames=0)


def test_the_refusal_names_the_first_section_that_is_wrong() -> None:
    with pytest.raises(SscError) as raised:
        index.resolve_sections(
            (Section("early", 0, 2), Section("late", 6, 9)), frames=8, where=WHERE
        )
    assert "late" in raised.value.message
    assert "early" not in raised.value.message
