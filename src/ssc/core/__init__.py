"""The pure layer: `ndarray` in, `ndarray` out.

Nothing here opens a file, reads `meta.json`, or knows what a workspace is. That is what
lets every function in here be tested against an 8x8 array.
"""

from ssc.core.resize import ResizeParams, resize

__all__ = ["ResizeParams", "resize"]
