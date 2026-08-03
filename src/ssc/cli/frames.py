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

#: And a ceiling on a whole *set*, because `MAX_PIXELS` bounds one frame and a directory
#: holds as many as somebody put there: two hundred frames each just under the per-image
#: limit is several gigabytes, and every one of them is decoded before anything is
#: converted. At four bytes a pixel this is a gigabyte of decoded frames, which is
#: generous for any real animation and far below what would take a machine down.
#:
#: The honest fix is to stream a set one frame at a time rather than hold it — but the
#: palette is computed across every frame, so that is two passes and a different shape for
#: `read_frames`. A ceiling is what this leaf can promise; streaming is what a later one
#: can build.
MAX_SET_PIXELS = 256_000_000

#: And a ceiling on the *bytes* of a single file, for the one reader that cannot be lazy.
#: `Image.open` on a path reads a header and defers the rest, so `MAX_PIXELS` can refuse an
#: oversized image without decoding it; a file read through a `Directory` binding is in
#: memory before anything can look at it, which is the price of binding the read.
#:
#: Set above what a `MAX_PIXELS` image occupies uncompressed — 64M pixels of RGBA is 256MB,
#: and an uncompressed BMP of exactly that size is a legitimate input — so that no file the
#: pixel ceiling would have accepted is refused by this one. It bounds the peak at the same
#: order as the decoded array `MAX_PIXELS` already allows, rather than at a smaller number
#: that would make the two ceilings disagree about the same file.
MAX_FILE_BYTES = 320_000_000


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
    """Decode the image at `path`, for every caller that holds a path and nothing else."""
    try:
        with Image.open(path) as handle:
            return _to_rgba(handle, str(path))
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as unreadable:
        # DecompressionBombError is a bare Exception, not an OSError, so it would otherwise
        # leave the command as a traceback rather than as this project's error contract.
        raise SscError(
            "unreadable-image",
            f"{path} could not be read as an image: {unreadable}",
            fix="check the file, or point --in at a PNG",
        ) from unreadable


def decode_image(data: bytes, label: str) -> np.ndarray:
    """Decode bytes a caller already read, and name the errors after `label`.

    The reader for a file inside an asset, which `Directory.read` hands over as bytes so
    that what is decoded is what was read through the binding rather than whatever the path
    resolves to a statement later (workspace-foundation R3.7). Bytes have no path to report,
    so the recorded path travels as `label` — an error naming the temporary nothing or the
    buffer would be useless to the caller who has to act on it.

    One difference from `load_image` worth stating rather than discovering: `Image.open` is
    lazy on a path, so the ceiling below refuses an oversized image before it is decoded,
    while here the bytes are already in memory by construction. That is the price of binding
    the read and it is bounded by the file on disk; the ceiling still does its real job,
    which is refusing the *decode* that turns a small file into hundreds of megabytes.
    """
    try:
        with Image.open(io.BytesIO(data)) as handle:
            return _to_rgba(handle, label)
    except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as unreadable:
        raise SscError(
            "unreadable-image",
            f"{label} could not be read as an image: {unreadable}",
            fix="check the file, or remove that record from meta.json",
        ) from unreadable


def _to_rgba(handle: Image.Image, label: str) -> np.ndarray:
    """The ceiling and the conversion, shared so there is one of each rather than two."""
    width, height = handle.size
    if width * height > MAX_PIXELS:
        raise SscError(
            "image-too-large",
            f"{label} is {width}x{height}, over the {MAX_PIXELS:,}-pixel ceiling",
            fix="scale it down first, or measure a smaller region",
        )
    return np.array(handle.convert("RGBA"))


def check_set_size(paths: list[Path]) -> int:
    """Refuse a set past `MAX_SET_PIXELS` before decoding any of it (R1.5).

    The sizes are read from the headers — `Image.open` is lazy, so `.size` costs a header
    and not a decode — which is what lets the whole set be refused rather than refused
    half way through, with the first half already resident.
    """
    total = 0
    for path in paths:
        try:
            with Image.open(path) as handle:
                width, height = handle.size
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            # Not this function's refusal to make: `load_image` reports an unreadable file
            # with the code and the fix that belong to it.
            continue
        total += width * height
        if total > MAX_SET_PIXELS:
            raise SscError(
                "set-too-large",
                f"{len(paths)} frames come to over {MAX_SET_PIXELS:,} pixels decoded",
                fix="convert the set in smaller batches, or scale the frames down first",
            )
    return total


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
        check_set_size(found)
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


def write_one(path: Path, image: np.ndarray, *, dry_run: bool = False) -> list[Path]:
    """Write one generated image at exactly `path`.

    Separate from `write_frames` because that one takes the shape of its output from the
    shape of its input — a file in, a file out; a directory in, a directory out — and a
    generated image has no input to take a shape from. Passing the destination as both
    made `--out board.png` a *directory* called `board.png`, which is the kind of thing
    that only shows up when something later tries to open it.
    """
    if path.exists():
        raise SscError(
            "file-exists",
            f"{path} already exists, and nothing in ssc overwrites a file",
            fix=f"delete it, or write to another path: rm {path}",
        )
    if dry_run:
        return [path]
    write_new(path, encode(image))
    return [path]


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
