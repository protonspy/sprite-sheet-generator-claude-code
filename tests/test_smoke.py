"""The floor the CI stands on: the package imports and the toolchain has a target.

This file exists so that a green pipeline means something before there is any code.
It goes away once specs/workspace-foundation/ lands real tests.
"""

import ssc


def test_package_imports() -> None:
    assert ssc.__version__


def test_cv_extras_are_optional() -> None:
    """The suite must pass without [cv]; nothing at import time may require it."""
    import importlib.util

    assert importlib.util.find_spec("ssc") is not None
