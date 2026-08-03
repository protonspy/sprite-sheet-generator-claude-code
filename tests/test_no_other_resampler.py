"""R4.4 — nearest neighbour is an invariant, so a second resampler fails the suite.

The plan is blunt about why this is a test and not a review convention: one careless
bilinear resize undoes the whole of M1, and the damage is invisible until 4x zoom. Nobody
catches that by reading a diff a year from now.

The detector walks the AST rather than grepping, so `# resize` in a comment and a variable
named `resize` are not findings, and `Image.resize(...)` split across lines is.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
ALLOWED = {SRC / "ssc/core/resize.py", SRC / "ssc/core/__init__.py"}

# A bare `resize(` is ours. Anything qualified by an object is somebody else's resampler:
# PIL's `Image.resize`, OpenCV's `cv2.resize`, a numpy view's — all of them take a filter.
FORBIDDEN_ATTRIBUTES = {"resize", "thumbnail", "rescale"}


def offending_calls(source: str, label: str) -> list[str]:
    """Every call in `source` that resamples through something other than `core.resize`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Attribute) and target.attr in FORBIDDEN_ATTRIBUTES:
            found.append(f"{label}:{target.lineno} .{target.attr}(")
    return found


def python_files() -> Iterator[Path]:
    yield from (path for path in SRC.rglob("*.py") if path not in ALLOWED)


def test_the_detector_finds_a_foreign_resampler() -> None:
    """The positive control. Without it, a detector that finds nothing looks the same as
    a codebase that is clean, and there would be no way to tell them apart."""
    assert offending_calls("out = Image.resize(img, (8, 8), Image.BILINEAR)", "sample")
    assert offending_calls("out = cv2.resize(\n  img,\n  (8, 8),\n)", "sample")
    assert offending_calls("img.thumbnail((8, 8))", "sample")


def test_the_detector_does_not_fire_on_the_word_alone() -> None:
    assert not offending_calls("# resize the frame to its cell", "sample")
    assert not offending_calls("resize(image, params)", "sample")
    assert not offending_calls("resize = 3", "sample")


def test_nothing_under_src_resamples_except_core_resize() -> None:
    findings = [
        finding
        for path in python_files()
        for finding in offending_calls(path.read_text(encoding="utf-8"), str(path.relative_to(SRC)))
    ]
    assert findings == [], (
        "found a resampler outside ssc.core.resize — every resize in this pipeline is "
        f"nearest neighbour and goes through that one function: {findings}"
    )
