"""The registry of runnable commands — specs/sweep-and-review R1.1, R1.5, R1.6, R1.7."""

from __future__ import annotations

import numpy as np
import pytest

from ssc.cli import steps
from ssc.cli.errors import UsageError


def green_frame(width: int = 8, height: int = 8) -> np.ndarray:
    frame = np.zeros((height, width, 4), dtype=np.uint8)
    frame[..., :3] = steps.PRESETS["green"]
    frame[..., 3] = 255
    # A subject in the middle, so there is something for the key to leave behind.
    frame[3:5, 3:5, :3] = (200, 30, 30)
    return frame


# R1.5 — only what the registry holds.
def test_a_command_in_the_registry_resolves() -> None:
    assert steps.runnable("bgremove").name == "bgremove"


def test_a_command_that_is_not_there_is_refused_by_name() -> None:
    with pytest.raises(UsageError) as refused:
        steps.runnable("bgremoove")
    assert refused.value.code == "unknown-command"
    assert "bgremove" in (refused.value.fix or "")


def test_a_paid_verb_is_simply_not_in_the_registry() -> None:
    """gates-and-resume R4.9 is a property of this table, not a check somewhere else."""
    assert "gen" not in steps.REGISTRY
    for name in steps.REGISTRY:
        assert not name.startswith("gen")


# R1.6 — a parameter the command does not take.
def test_an_unknown_parameter_is_refused_naming_what_the_command_takes() -> None:
    with pytest.raises(UsageError) as refused:
        steps.runnable("bgremove").read({"tolerance": "60"})
    assert refused.value.code == "unknown-parameter"
    assert "tol" in (refused.value.fix or "")


def test_a_known_parameter_parses_to_its_type() -> None:
    assert steps.runnable("bgremove").read({"tol": "60"}) == {"tol": 60}


def test_a_choice_parameter_keeps_its_name() -> None:
    assert steps.runnable("bgremove").read({"mode": "global"}) == {"mode": "global"}


def test_a_colour_parameter_becomes_a_colour() -> None:
    assert steps.runnable("bgremove").read({"chroma": "green"})["chroma"] == steps.PRESETS["green"]


# R1.7 — the bound is checked when the value is read, before anything runs.
def test_a_value_over_the_bound_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        steps.runnable("bgremove").read({"tol": str(steps.MAX_TOLERANCE + 1)})
    assert refused.value.code == "invalid-value"


def test_a_value_under_the_bound_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        steps.runnable("pixelart").read({"colors": "1"})
    assert refused.value.code == "invalid-value"


def test_a_value_at_the_bound_is_allowed() -> None:
    assert steps.runnable("pixelart").read({"colors": str(steps.MAX_COLORS)})["colors"] == (
        steps.MAX_COLORS
    )


def test_a_value_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        steps.runnable("bgremove").read({"tol": "loose"})
    assert refused.value.code == "invalid-value"


def test_a_choice_outside_the_set_is_refused() -> None:
    with pytest.raises(UsageError) as refused:
        steps.runnable("bgremove").read({"mode": "sideways"})
    assert refused.value.code == "invalid-value"


def test_a_flag_takes_true_or_false_and_nothing_else() -> None:
    assert steps.runnable("bgremove").read({"edge_pass": "true"}) == {"edge_pass": True}
    with pytest.raises(UsageError):
        steps.runnable("bgremove").read({"edge_pass": "yes"})


# R1.1 — running a step produces frames and a measurement.
def test_bgremove_keys_the_background_and_reports_what_it_did() -> None:
    outcome = steps.runnable("bgremove").run([green_frame()], {"tol": 60, "mode": "global"})
    assert len(outcome.frames) == 1
    assert outcome.measurement["transparent_px"] > 0
    assert outcome.measurement["opaque_px"] > 0
    # The subject survived; the surround did not.
    assert outcome.frames[0][0, 0, 3] == 0
    assert outcome.frames[0][3, 3, 3] == 255


def test_pixelart_computes_one_palette_across_the_whole_set() -> None:
    outcome = steps.runnable("pixelart").run([green_frame(), green_frame()], {"colors": 4})
    assert len(outcome.frames) == 2
    assert 0 < len(outcome.measurement["palette"]) <= 4


def test_a_step_run_with_no_parameters_uses_the_command_defaults() -> None:
    outcome = steps.runnable("bgremove").run([green_frame()], {})
    assert outcome.measurement["mode"] == "flood"


def test_running_a_step_does_not_touch_the_frames_it_was_given() -> None:
    given = green_frame()
    before = given.copy()
    steps.runnable("bgremove").run([given], {"tol": 60})
    assert np.array_equal(given, before)
