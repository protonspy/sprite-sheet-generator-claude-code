"""`ssc asset new --extends` — derivation and the recipe it carries (plan 6.1, 6.3).

A derived asset carries no pixels of its parent: it carries a `recipe.yaml`
inheriting the parent's recipe, measured from the parent's published stage. These
cover measurement, inheritance from a parent that is itself derived, the `--kind`
checks, and the refusals — including a chain that is broken or cyclic, which is
refused with the chain walked so far rather than resolved as a partial recipe.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
from click.testing import CliRunner
from conftest import save_meta

from ssc.cli import meta, palettes, recipe
from ssc.cli.app import main
from ssc.cli.atomic import Directory
from ssc.cli.frames import encode
from ssc.core.doctor.checks import detect_pixel_size


def run(*argv: str) -> tuple[int, dict[str, Any]]:
    result = CliRunner().invoke(main, [*argv, "--json"], catch_exceptions=False)
    return result.exit_code, json.loads(result.output)


def grid_frame() -> np.ndarray:
    """A 64x64 frame of 4x4 blocks, so `detect_pixel_size` reads 4."""
    img = np.zeros((64, 64, 4), dtype=np.uint8)
    for by in range(0, 64, 4):
        for bx in range(0, 64, 4):
            shade = 40 if ((bx // 4) + (by // 4)) % 2 else 200
            img[by : by + 4, bx : bx + 4, :3] = shade
            img[by : by + 4, bx : bx + 4, 3] = 255
    return img


def make_parent(space: Path, *, key: str = "hero", kind: str = "character") -> Path:
    """A source parent: two styled frames at its published stage, a sidecar fps, a
    locked palette. Built by hand so the test does not pay for a generation."""
    asset_dir = space / "assets" / kind / key
    (asset_dir / "frames" / "style").mkdir(parents=True)
    frame = grid_frame()
    data = encode(frame)
    (asset_dir / "frames" / "style" / "001.png").write_bytes(data)
    (asset_dir / "frames" / "style" / "002.png").write_bytes(data)

    record = meta.AssetMeta(key=key, kind=kind)
    meta.record(
        record,
        path="frames/style",
        stage="style",
        file_class="source",
        data=data,
        produced_by=meta.Provenance(command="tool style"),
    )
    save_meta(asset_dir, record)
    (asset_dir / "asset.yaml").write_text("playback:\n  fps: 8\n", encoding="utf-8")
    palettes.lock(space / palettes.PALETTE_FILE, "pico8")
    return asset_dir


def init_space(tmp_path: Path, monkeypatch: Any) -> Path:
    monkeypatch.chdir(tmp_path)
    assert run("init")[0] == 0
    return tmp_path


def test_a_derived_asset_inherits_a_measured_recipe(tmp_path: Path, monkeypatch: Any) -> None:
    space = init_space(tmp_path, monkeypatch)
    make_parent(space)
    code, payload = run("asset", "new", "knight", "--extends", "character/hero")
    assert code == 0, payload

    child = space / "assets" / "character" / "knight"
    with Directory.open(child) as held:
        inherited = recipe.load(held)
        record = meta.load(held)
    assert inherited is not None
    assert inherited.extends == "character/hero"
    assert inherited.anchor == recipe.AnchorRef(asset="character/hero", stage="style")
    assert inherited.kind == "character"
    assert inherited.cell == (64, 64)
    assert inherited.frames == 2
    assert inherited.fps == 8
    assert inherited.palette == "pico8"
    assert inherited.pixel_size == detect_pixel_size(grid_frame())
    # the parent in the child's provenance — asset-level, not per-file, since the
    # child carries no files to hang a file lineage on.
    assert record.derived_from == "character/hero"
    # never the pixels: the child carries a recipe and a record, nothing else.
    assert not (child / "frames").exists()
    assert sorted(p.name for p in child.iterdir()) == ["meta.json", "recipe.yaml"]


def test_a_derived_asset_inherits_a_derived_parents_recipe_verbatim(
    tmp_path: Path, monkeypatch: Any
) -> None:
    space = init_space(tmp_path, monkeypatch)
    make_parent(space)
    run("asset", "new", "knight", "--extends", "character/hero")
    # A grandchild extends the child; the child has a recipe of its own, so the
    # grandchild inherits it verbatim and re-anchors `extends` to the child.
    code, payload = run("asset", "new", "squire", "--extends", "character/knight")
    assert code == 0, payload

    with Directory.open(space / "assets" / "character" / "knight") as held:
        parent_recipe = recipe.load(held)
    with Directory.open(space / "assets" / "character" / "squire") as held:
        child_recipe = recipe.load(held)
        squire_record = meta.load(held)
    assert parent_recipe is not None and child_recipe is not None
    assert child_recipe.extends == "character/knight"
    # the anchor is inherited verbatim — still the root's anchor image, not the
    # immediate parent's, so a grandchild generates from the same anchor its parent did.
    assert child_recipe.anchor == parent_recipe.anchor
    assert child_recipe.anchor == recipe.AnchorRef(asset="character/hero", stage="style")
    assert child_recipe.cell == parent_recipe.cell
    assert child_recipe.frames == parent_recipe.frames
    assert child_recipe.pixel_size == parent_recipe.pixel_size
    # provenance walks one hop: the grandchild's parent is the child, not the root.
    assert squire_record.derived_from == "character/knight"


def test_a_kind_that_disagrees_with_the_parent_is_refused(tmp_path: Path, monkeypatch: Any) -> None:
    space = init_space(tmp_path, monkeypatch)
    make_parent(space)
    code, payload = run("asset", "new", "knight", "--extends", "character/hero", "--kind", "tile")
    assert code != 0
    assert payload["error"]["code"] == "kind-mismatch"


def test_neither_kind_nor_extends_is_refused(tmp_path: Path, monkeypatch: Any) -> None:
    init_space(tmp_path, monkeypatch)
    code, payload = run("asset", "new", "lonely")
    assert code != 0
    assert payload["error"]["code"] == "no-kind"


def test_a_missing_parent_is_refused(tmp_path: Path, monkeypatch: Any) -> None:
    init_space(tmp_path, monkeypatch)
    code, payload = run("asset", "new", "knight", "--extends", "character/ghost")
    assert code != 0
    assert payload["error"]["code"] == "no-asset"


def test_a_dry_run_writes_nothing(tmp_path: Path, monkeypatch: Any) -> None:
    space = init_space(tmp_path, monkeypatch)
    make_parent(space)
    code, payload = run("asset", "new", "knight", "--extends", "character/hero", "--dry-run")
    assert code == 0, payload
    assert payload["dry_run"] is True
    assert payload["extends"] == "character/hero"
    assert not (space / "assets" / "character" / "knight").exists()


# the chain above the parent — refused whole, not resolved as a partial recipe


def _recipe_at(space: Path, key: str, *, extends: str, anchor: str = "character/hero") -> None:
    """Hand-write a recipe into an existing asset, the way a hand-edit would."""
    with Directory.open(space / "assets" / "character" / key) as held:
        recipe.write(
            held,
            recipe.Recipe(
                extends=extends,
                anchor=recipe.AnchorRef(asset=anchor, stage="style"),
                kind="character",
                pixel_size=4,
                palette="pico8",
                cell=(64, 64),
                frames=2,
                fps=8,
            ),
        )


def test_a_chain_with_a_missing_link_is_refused(tmp_path: Path, monkeypatch: Any) -> None:
    space = init_space(tmp_path, monkeypatch)
    make_parent(space)
    run("asset", "new", "knight", "--extends", "character/hero")  # knight -> hero
    # hero is the root of knight's chain; remove it, and the chain is broken.
    shutil.rmtree(space / "assets" / "character" / "hero")
    code, payload = run("asset", "new", "squire", "--extends", "character/knight")
    assert code != 0
    assert payload["error"]["code"] == "chain-missing"
    # the chain walked so far names the parent the caller asked for and the link
    # that is missing — not just the missing link, and not nothing.
    message = payload["error"]["message"]
    assert "character/knight" in message
    assert "character/hero" in message


def test_a_cyclic_chain_is_refused(tmp_path: Path, monkeypatch: Any) -> None:
    space = init_space(tmp_path, monkeypatch)
    make_parent(space)
    run("asset", "new", "knight", "--extends", "character/hero")  # knight -> hero
    # Hand-edit hero into a derivation of knight, closing a cycle a `new` could
    # never have built (the asset-exists guard and the write-new guard both stop it).
    _recipe_at(space, "hero", extends="character/knight")
    code, payload = run("asset", "new", "squire", "--extends", "character/knight")
    assert code != 0
    assert payload["error"]["code"] == "chain-cyclic"
    message = payload["error"]["message"]
    assert "character/knight" in message
    assert "character/hero" in message
