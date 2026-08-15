"""A pipeline step that bills — specs/generation-gates R1, R2, R3.

Every test runs against the fake provider in `conftest.py`. Nothing here reaches the network
and nothing reads a real credential; what is asserted is mostly the *absence* of a call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from click.testing import CliRunner
from conftest import FakeClient
from PIL import Image

from ssc.cli import steps
from ssc.cli.app import main
from ssc.cli.errors import UsageError
from ssc.core.bgremove import PRESETS

NANO = "fal-ai/nano-banana-2"
GROK = "xai/grok-imagine-video/image-to-video"


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def declare(root: Path, *pipeline: dict[str, Any]) -> None:
    document = yaml.safe_load((root / "ssc.yaml").read_text(encoding="utf-8")) or {}
    document["pipeline"] = list(pipeline)
    document["models"] = {"image": NANO, "video": GROK}
    (root / "ssc.yaml").write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")


@pytest.fixture
def hero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A workspace with one character asset holding two cut frames."""
    monkeypatch.chdir(tmp_path)
    assert run("init")[0] == 0
    assert run("asset", "new", "hero", "--kind", "character")[0] == 0

    sheet = tmp_path / "sheet.png"
    frame = np.zeros((12, 24, 4), dtype=np.uint8)
    frame[..., :3] = PRESETS["green"]
    frame[..., 3] = 255
    frame[4:8, 4:8, :3] = (200, 30, 30)
    Image.fromarray(frame, mode="RGBA").save(sheet)
    assert (
        run("tool", "cut", "--in", str(sheet), "--grid", "2x1", "--asset", "character/hero")[0] == 0
    )
    return tmp_path


ANCHOR = {
    "stage": "anchor",
    "command": "gen image",
    "gate": "does this read as the character?",
    "params": {"prompt": "a frost warden in rime-blue plate", "board": True},
}


# R2.1, R2.3 — what a paid step may declare.


def test_the_paid_registry_holds_the_verbs_a_step_may_name() -> None:
    """`gen expand` and `gen bgremove` are deliberately absent: both transform a subject
    image rather than generating from a description."""
    assert sorted(steps.PAID_REGISTRY) == ["gen boxart", "gen image", "gen video"]


def test_a_parameter_the_verb_does_not_take_is_refused(hero: Path) -> None:
    declare(hero, {**ANCHOR, "params": {"prompt": "a knight", "seconds": 4}})

    code, payload = run("run", "character/hero")

    assert code == 2
    assert payload["error"]["code"] == "unknown-parameter"
    assert "var." in payload["error"]["fix"]


def test_box_art_takes_no_reference_and_no_style() -> None:
    """The two things `specs/box-art/` says it must not have, absent from the table rather
    than checked at the call."""
    parameters = steps.PAID_REGISTRY["gen boxart"].parameters

    assert "from_stage" not in parameters
    assert "style" not in parameters


def test_a_template_variable_travels_under_a_prefix(hero: Path) -> None:
    declare(
        hero,
        {
            "stage": "concept",
            "command": "gen boxart",
            "gate": "is this the character?",
            "params": {
                "prompt": "a knight",
                "var.name": "Kael",
                "var.archetype": "frost warden",
                "var.costume": "rime-blue plate",
                "var.prop": "a rune-etched axe",
                "var.setting": "a frozen fen",
            },
        },
    )

    code, payload = run("run", "character/hero", "--dry-run")

    assert code == 0, payload
    assert payload["would_gate"] == "concept"


def test_a_variable_nobody_defined_is_refused_before_the_money(hero: Path, api: FakeClient) -> None:
    declare(hero, {**ANCHOR, "params": {"prompt": "a knight", "var.nickname": "Kael"}})

    code, payload = run("run", "character/hero")

    assert code == 2
    assert payload["error"]["code"] == "unknown-variable"
    assert api.submitted == []


# R1.2 — a paid step with no gate is refused, exactly as every paid step used to be.


def test_a_paid_step_with_no_gate_is_refused(hero: Path) -> None:
    declare(hero, {"stage": "anchor", "command": "gen image", "params": {"prompt": "a knight"}})

    code, payload = run("run", "character/hero")

    assert code == 2
    assert payload["error"]["code"] == "paid-step"
    assert "gate" in payload["error"]["fix"]


def test_a_paid_command_no_step_may_name_is_refused(hero: Path) -> None:
    declare(
        hero,
        {"stage": "nobg", "command": "gen bgremove", "gate": "clean?", "params": {}},
    )

    code, payload = run("run", "character/hero")

    assert code == 2
    assert payload["error"]["code"] == "paid-step"
    assert "gen image" in payload["error"]["fix"]


# R1.3, R1.4 — the gate opens before the call, and says what the call would cost.


def test_the_gate_opens_before_anything_is_submitted(hero: Path, api: FakeClient) -> None:
    declare(hero, ANCHOR)

    code, payload = run("run", "character/hero")

    assert code == 3
    assert payload["stopped_at"] == "anchor"
    assert payload["gate"]["state"] == "pending"
    # the whole point: the money has not been spent when the question is asked
    assert api.submitted == []
    assert (hero / "gates" / "hero.anchor.json").is_file()


def test_the_gate_names_the_model_and_the_estimate(hero: Path, api: FakeClient) -> None:
    declare(hero, ANCHOR)

    _, payload = run("run", "character/hero")

    question = payload["gate"]["question"]
    assert "does this read as the character?" in question
    assert NANO in question
    assert "$" in question or "price unknown" in question


def test_a_second_run_while_it_is_pending_submits_nothing(hero: Path, api: FakeClient) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3

    code, payload = run("run", "character/hero")

    assert code == 3
    assert payload["stopped_at"] == "anchor"
    assert api.submitted == []


# R1.1, R1.5 — approved, it submits.


def test_an_approved_gate_lets_the_call_through(hero: Path, api: FakeClient, keyed: None) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0

    code, payload = run("run", "character/hero")

    assert code == 0, payload
    assert payload["complete"] is True
    assert payload["ran"] == ["anchor"]
    assert len(api.submitted) == 1
    application, arguments = api.submitted[0]
    assert application.startswith(NANO)
    assert "a frost warden" in arguments["prompt"]


def test_what_came_back_is_recorded_as_the_steps_stage(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0
    assert run("run", "character/hero")[0] == 0

    code, payload = run("status", "character/hero")

    assert code == 0
    assert payload["done"] == 1
    # and it does not run twice: the stage is recorded, so the step is done
    assert run("run", "character/hero")[1]["ran"] == []


# R1.6, R3.1, R3.2 — the two ways it stops with nothing submitted.


def test_a_rejected_gate_stops_the_run(hero: Path, api: FakeClient) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "reject", "hero.anchor", "--why", "wrong silhouette")[0] == 0

    code, payload = run("run", "character/hero")

    assert code == 1
    assert payload["error"]["code"] == "gate-rejected"
    assert api.submitted == []


def test_the_reservation_is_taken_exactly_as_for_a_hand_typed_call(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    """R3.1 — a paid step goes through `gen.run`, so the reservation, the job record and the
    cache are `budget-guard`'s and `job-store`'s rather than anything this leaf re-implements.
    The refusal R3.2 states is theirs too, and is asserted where it lives; what is asserted
    here is that a step's call is counted at all.
    """
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0
    assert run("run", "character/hero")[0] == 0

    code, payload = run("budget")

    assert code == 0, payload
    assert payload["calls"] >= 1
    assert list((hero / "jobs").glob("*.json"))


# R2.4 — the dry run.


def test_a_dry_run_reports_the_resolved_call_and_submits_nothing(
    hero: Path, api: FakeClient
) -> None:
    declare(hero, ANCHOR)

    code, payload = run("run", "character/hero", "--dry-run")

    assert code == 0, payload
    assert payload["would_gate"] == "anchor"
    # `board: true` carries an image, so the call routes to the editing endpoint
    assert payload["model"].startswith(NANO)
    assert "estimate_usd" in payload
    assert api.submitted == []
    assert not (hero / "gates").exists()


def test_a_dry_run_past_an_approved_gate_still_submits_nothing(hero: Path, api: FakeClient) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0

    code, payload = run("run", "character/hero", "--dry-run")

    assert code == 0, payload
    assert payload["would_run"] == "anchor"
    assert payload["arguments"]["prompt"]
    assert api.submitted == []


# R2.2 — the stage a step points at.


def test_a_step_sends_the_stage_it_names_as_a_reference(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    declare(
        hero,
        ANCHOR,
        {
            "stage": "west",
            "command": "gen image",
            "gate": "is this the same character?",
            "params": {
                "prompt": "the anchor, turned West",
                "from_stage": "anchor",
                "role": "identity",
            },
        },
    )
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.west")[0] == 0

    code, payload = run("run", "character/hero")

    assert code == 0, payload
    assert payload["ran"] == ["west"]
    _, arguments = api.submitted[-1]
    assert arguments["image_urls"]
    # the role reached the prompt, so the model is told what the image is for
    assert "the character to stay faithful to" in arguments["prompt"]


def test_a_role_nobody_defined_is_refused_in_a_step(hero: Path) -> None:
    declare(hero, {**ANCHOR, "params": {"prompt": "a knight", "role": "vibes"}})

    code, payload = run("run", "character/hero")

    assert code == 2
    assert payload["error"]["code"] == "invalid-value"


# R1.7, R1.8 — the approval is bound to the call it was shown.


def test_the_gate_records_which_call_it_authorises(hero: Path, api: FakeClient) -> None:
    declare(hero, ANCHOR)

    _, payload = run("run", "character/hero")

    assert payload["gate"]["authorises"]


@pytest.mark.parametrize(
    "changed",
    [
        {"prompt": "something else entirely", "board": True},
        {"prompt": "a frost warden in rime-blue plate", "board": True, "count": 4},
        {"prompt": "a frost warden in rime-blue plate", "board": True, "size": "512x512"},
    ],
)
def test_a_call_that_changed_after_approval_asks_again(
    hero: Path, api: FakeClient, keyed: None, changed: dict[str, Any]
) -> None:
    """`ssc.yaml` is re-read every run and arrives with a cloned repository as often as it is
    written by whoever runs the command. Between the approval and the next run the model, the
    prompt or the count can change — and an approval bound only to the asset and the stage
    would be a signature given for something else."""
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0

    declare(hero, {**ANCHOR, "params": changed})
    code, payload = run("run", "character/hero")

    assert code == 3
    assert payload["stopped_at"] == "anchor"
    assert api.submitted == []


def test_the_same_call_still_goes_through(hero: Path, api: FakeClient, keyed: None) -> None:
    """The other half: re-reading the same pipeline resolves the same call, so an approval
    that has not been outrun still authorises it."""
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor")[0] == 0

    declare(hero, ANCHOR)
    code, payload = run("run", "character/hero")

    assert code == 0, payload
    assert len(api.submitted) == 1


# R4.1, R4.2, R4.3 — a standing approval is a standing authorisation to spend.


def test_gate_list_names_the_topics_with_a_standing_approval(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor", "--default")[0] == 0

    code, payload = run("gate", "list")

    assert code == 0, payload
    assert payload["defaults"]["anchor"]["from"] == "hero.anchor"
    # in the line a person reads, not only in the JSON
    assert "standing approval for anchor" in payload["summary"]


def test_a_gate_that_inherited_one_says_where_it_came_from(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    """The second asset does not stop the run again — and the record says which decision
    stood in for the question nobody was asked."""
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor", "--default")[0] == 0
    assert run("run", "character/hero")[0] == 0
    assert run("asset", "new", "mage", "--kind", "character")[0] == 0

    code, payload = run("run", "character/mage")

    assert code == 0, payload
    _, listed = run("gate", "list")
    inherited = [one for one in listed["gates"] if one["subject"] == "mage"]
    assert inherited and inherited[0]["inherited_from"] == "hero.anchor"
    assert inherited[0]["state"] == "approved"


def test_a_standing_approval_nobody_here_gave_is_not_honoured(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    """`defaults.json` is a file in the workspace like any other, so one that arrived with a
    cloned repository would otherwise authorise spending that nobody here ever approved."""
    (hero / "gates").mkdir(exist_ok=True)
    (hero / "gates" / "defaults.json").write_text(
        json.dumps(
            {
                "schema": 2,
                "topics": {"anchor": {"choice": None, "from": "someone-elses.anchor", "at": ""}},
            }
        ),
        encoding="utf-8",
    )
    declare(hero, ANCHOR)

    code, payload = run("run", "character/hero")

    assert code == 3
    assert payload["gate"]["state"] == "pending"
    assert api.submitted == []


def test_a_standing_approval_whose_gate_was_rejected_is_not_honoured(
    hero: Path, api: FakeClient, keyed: None
) -> None:
    declare(hero, ANCHOR)
    assert run("run", "character/hero")[0] == 3
    assert run("gate", "approve", "hero.anchor", "--default")[0] == 0
    # the decision that established the default is then reversed by hand on disk
    path = hero / "gates" / "hero.anchor.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    record["state"] = "rejected"
    path.write_text(json.dumps(record), encoding="utf-8")
    assert run("asset", "new", "mage", "--kind", "character")[0] == 0

    code, payload = run("run", "character/mage")

    assert code == 3
    assert payload["gate"]["state"] == "pending"
    assert api.submitted == []


def test_ask_for_carries_the_box_art_cell(hero: Path) -> None:
    """The one verb whose size is not the asset's: box art is a portrait at a size no cell
    ever is, and the number is the `box-art` kind's."""
    from ssc.cli import kinds
    from ssc.cli import workspace as ws

    step = steps.Step(
        stage="concept", command="gen boxart", params={"prompt": "a knight"}, gate="ok?"
    )
    profile = kinds.resolve("box-art", ws.require()).profile

    ask = steps.ask_for(step, profile=profile)

    assert ask.cell == (1024, 1536)
    assert ask.size == (1024, 1536)
    assert ask.template == "box-art"


def test_a_size_that_is_not_a_size_is_refused(hero: Path) -> None:
    from ssc.cli import kinds
    from ssc.cli import workspace as ws

    step = steps.Step(stage="anchor", command="gen image", params={"size": "wide"}, gate="ok?")

    with pytest.raises(UsageError) as refused:
        steps.ask_for(step, profile=kinds.resolve("box-art", ws.require()).profile)

    assert refused.value.code == "invalid-size"
