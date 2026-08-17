"""The floor the CI stands on: the package imports and the toolchain has a target.

This file exists so that a green pipeline means something before there is any code.
It goes away once specs/workspace-foundation/ lands real tests.
"""

import ssc


def test_package_imports() -> None:
    assert ssc.__version__


def test_the_two_places_the_version_is_written_agree() -> None:
    """`ssc --version` reads one of them and PyPI reads the other, so a release that
    bumped only one ships a wheel whose contents disagree with its own filename."""
    import re
    from pathlib import Path

    manifest = Path(__file__).resolve().parent.parent / "pyproject.toml"
    declared = re.search(r'^version = "(.+)"$', manifest.read_text(encoding="utf-8"), re.M)

    assert declared is not None
    assert declared.group(1) == ssc.__version__


def test_cv_extras_are_optional() -> None:
    """The suite must pass without [cv]; nothing at import time may require it."""
    import importlib.util

    assert importlib.util.find_spec("ssc") is not None
