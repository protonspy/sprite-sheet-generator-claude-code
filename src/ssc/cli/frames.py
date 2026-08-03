"""Reading `--in` and writing `--out`, for the commands that need no workspace.

`snap`, `pixelart` and `board` are usable against a directory of loose PNGs by somebody who
has never run `ssc init` (R1.1), so this is the whole of their IO: one image or an ordered
set in, one file or a matching set out.

The decode ceiling lives here because there is one image reader in this project and it is
this one. `doctor` reads art a model produced or somebody downloaded, and so do these three;
two readers would mean two ceilings, and the second one to be written is the one nobody
remembers to bound.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ssc.cli.atomic import write_new
from ssc.cli.errors import SscError

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

#: A ceiling on what will be decoded. The input is attacker-influenced: a fine
#: checkerboard that is tiny on disk decodes to hundreds of megabytes. Pillow's own bomb
#: threshold is both higher and raised as an exception type this project does not otherwise
#: handle, so the limit is stated here.
MAX_PIXELS = 64_000_000


@dataclass(frozen=True)
class Frame:
    """One image, and the filename it arrived under.

    The name is carried because R1.3 writes it back out: a frame set that comes back under
    invented names cannot be matched to what went in, and the order of an animation is the
    order of its filenames.
    """

    name: str
    image: np.ndarray


def load_image(path: Path) -> np.ndarray:
    try:
        with Image.open(path) as handle:
            width, height = handle.size
            if width * height > MAX_PIXELS:
                raise SscError(
                    "image-too-large",
                    f"{path} is {width}x{height}, over the {MAX_PIXELS:,}-pixel ceiling",
                    fix="scale it down first, or measure a smaller region",
                )
            return np.array(handle.convert("RGBA"))
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as unreadable:
        # DecompressionBombError is a bare Exception, not an OSError, so it would otherwise
        # leave the command as a traceback rather than as this project's error contract.
        raise SscError(
            "unreadable-image",
            f"{path} could not be read as an image: {unreadable}",
            fix="check the file, or point --in at a PNG",
        ) from unreadable


def read_frames(path: Path) -> list[Frame]:
    """One image, or a directory read as a frame set ordered by filename (R1.2).

    Ordered by filename because that is the order the frames were written in and the only
    ordering that survives being copied around.
    """
    if path.is_file():
        return [Frame(path.name, load_image(path))]
    if path.is_dir():
        found = sorted(child for child in path.iterdir() if child.suffix.lower() in IMAGE_SUFFIXES)
        if not found:
            raise SscError(
                "no-images",
                f"{path} holds no images",
                fix="point --in at a file, or at a directory of frames",
            )
        return [Frame(child.name, load_image(child)) for child in found]
    raise SscError(
        "no-input",
        f"{path} is neither a file nor a directory",
        fix="point --in at an image or at a directory of frames",
    )


def load_input(path: Path) -> list[np.ndarray]:
    """`read_frames` for a caller that does not need the names."""
    return [frame.image for frame in read_frames(path)]


def encode(image: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(image.astype(np.uint8), mode="RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def targets(source: Path, out: Path, frames: list[Frame]) -> list[Path]:
    """Where each frame will be written.

    A single image in gives a single file out; a directory in gives a directory out, each
    frame keeping its name (R1.3). The shape of `--out` follows the shape of `--in` rather
    than being a second thing to get right.
    """
    if source.is_file() and len(frames) == 1:
        return [out if out.suffix else out / frames[0].name]
    return [out / frame.name for frame in frames]


def write_frames(
    source: Path, out: Path, frames: list[Frame], *, dry_run: bool = False
) -> list[Path]:
    """Write every frame, or none of them (R1.4).

    Every target is checked before the first is written. Refusing part-way would leave a
    half-converted set on disk, and the caller who reran the command would then be refused
    by the frames that did land — the failure compounding rather than being recoverable.
    `write_new` still does the real refusing, because a check is not a lock.
    """
    where = targets(source, out, frames)
    existing = [path for path in where if path.exists()]
    if existing:
        raise SscError(
            "file-exists",
            f"{existing[0]} already exists, and nothing in ssc overwrites a file"
            + (f" ({len(existing)} of {len(where)} targets do)" if len(existing) > 1 else ""),
            fix=f"delete them, or write to another path: rm -r {out}",
        )
    if dry_run:
        return where
    for frame, path in zip(frames, where, strict=True):
        write_new(path, encode(frame.image))
    return where
