"""`ssc tool layers` and the `background` kind — specs/parallax-layers R1, R2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from ssc.cli.app import main


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.stdout)


def save(path: Path, width: int = 32, height: int = 16) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, 3] = 255
    Image.fromarray(image, mode="RGBA").save(path)
    return path


@pytest.fixture
def stack(tmp_path: Path) -> Path:
    directory = tmp_path / "bg"
    save(directory / "01-sky.png")
    save(directory / "02-hills.png")
    save(directory / "03-trees.png")
    return directory


# R1.1, R1.2 — the kind, and the field a project can set on one of its own.


def test_background_ships_as_a_layered_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    code, payload = run("kind", "show", "background")

    assert code == 0
    assert payload["layered"] is True
    assert payload["source"]["layered"] == "built-in"


def test_no_other_built_in_is_layered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The field is a claim about a kind, not a default that would make every asset a stack."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)

    for kind in ("character", "icon", "tile", "ui", "banner", "map"):
        _, payload = run("kind", "show", kind)
        assert payload["layered"] is False


def test_a_project_can_declare_a_layered_kind_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1.2 — asset-kinds' whole argument is that a kind is a profile, so a new field is
    that mechanism working rather than a hole in it."""
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(main, ["init"], catch_exceptions=False)
    config = tmp_path / "ssc.yaml"
    config.write_text(
        config.read_text(encoding="utf-8") + "\nkinds:\n  skybox:\n    layered: true\n",
        encoding="utf-8",
    )

    code, payload = run("kind", "show", "skybox")

    assert code == 0
    assert payload["layered"] is True
    assert payload["source"]["layered"] == "ssc.yaml"


# R2.1, R2.2, R2.3 — the stack and its numbers.


def test_the_layers_come_back_in_the_order_they_are_named(stack: Path) -> None:
    code, payload = run("tool", "layers", "--in", str(stack))

    assert code == 0
    assert [layer["file"] for layer in payload["layers"]] == [
        "01-sky.png",
        "02-hills.png",
        "03-trees.png",
    ]
    assert [layer["index"] for layer in payload["layers"]] == [0, 1, 2]


def test_given_factors_are_used_in_the_order_the_layers_are_in(stack: Path) -> None:
    _, payload = run("tool", "layers", "--scroll", "0.2,0.5,1.0", "--in", str(stack))

    assert [layer["scroll"] for layer in payload["layers"]] == [0.2, 0.5, 1.0]
    assert payload["derived"] is False


def test_a_stack_with_no_factors_gets_a_usable_ladder(stack: Path) -> None:
    """R2.3 — a three-layer stack is usable before anybody has an opinion about the numbers."""
    _, payload = run("tool", "layers", "--in", str(stack))

    factors = [layer["scroll"] for layer in payload["layers"]]
    assert factors == pytest.approx([1 / 3, 2 / 3, 1.0])
    assert payload["derived"] is True


def test_the_size_every_layer_shares_is_reported(stack: Path) -> None:
    _, payload = run("tool", "layers", "--in", str(stack))

    assert payload["size"] == {"width": 32, "height": 16}


# R2.4, R2.5, R2.6 — the three refusals, all about the set.


@pytest.mark.parametrize("scroll", ["0.2,1.5,1.0", "-0.1,0.5,1.0"])
def test_a_factor_outside_the_range_is_refused(scroll: str, stack: Path) -> None:
    code, payload = run("tool", "layers", "--scroll", scroll, "--in", str(stack))

    assert code == 2
    assert payload["error"]["code"] == "invalid-scroll"


@pytest.mark.parametrize("scroll", ["0.5", "0.1,0.2,0.3,0.4"])
def test_a_count_that_does_not_match_the_layers_is_refused(scroll: str, stack: Path) -> None:
    code, payload = run("tool", "layers", "--scroll", scroll, "--in", str(stack))

    assert code == 2
    assert payload["error"]["code"] == "scroll-count"
    assert "3" in payload["error"]["fix"]


def test_layers_of_different_sizes_are_refused_with_the_sizes_found(tmp_path: Path) -> None:
    """An engine scrolls every layer across one viewport, so a stack of mixed sizes tears at
    whichever edge runs out first."""
    directory = tmp_path / "mixed"
    save(directory / "01-sky.png", 32, 16)
    save(directory / "02-hills.png", 48, 16)

    code, payload = run("tool", "layers", "--in", str(directory))

    assert code == 2
    assert payload["error"]["code"] == "layers-differ"
    assert "32x16" in payload["error"]["message"]
    assert "48x16" in payload["error"]["message"]


def test_zero_is_a_legal_factor_and_means_a_sky_that_never_moves(stack: Path) -> None:
    code, payload = run("tool", "layers", "--scroll", "0,0.5,1", "--in", str(stack))

    assert code == 0
    assert payload["layers"][0]["scroll"] == 0.0


def test_the_layers_are_not_touched(stack: Path) -> None:
    """No `--out`: nothing here transforms a pixel, and the stack is a fact about the set."""
    before = {path.name: path.read_bytes() for path in stack.iterdir()}

    run("tool", "layers", "--in", str(stack))

    assert {path.name: path.read_bytes() for path in stack.iterdir()} == before
