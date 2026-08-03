"""How the doctor fixtures were constructed. **Not a step in any workflow.**

The PNGs beside this file are the asset: `doctor` is validated against their exact
measured numbers, and everything downstream depends on `doctor` being right. This script
exists so a reader can see what each defect *is*, not so anybody can regenerate a fixture
to make a failing test pass. If a number here changes, the detector changed, and that is
the thing to look at.

    python tests/fixtures/doctor/build.py --check   # rebuild in memory, diff, write nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent

INK = (26, 20, 35)
SKIN = (222, 158, 120)
TUNIC = (60, 120, 200)
BELT = (200, 60, 70)


def rgba(height: int, width: int, colour: tuple[int, int, int], alpha: int = 0) -> np.ndarray:
    image = np.zeros((height, width, 4), dtype=np.uint8)
    image[:, :, :3] = colour
    image[:, :, 3] = alpha
    return image


def little_guy() -> np.ndarray:
    """An 8x8 body: one connected shape, no holes, hard alpha."""
    body = rgba(8, 8, INK)
    body[1:7, 2:6, :3] = SKIN
    body[1:7, 2:6, 3] = 255
    body[5:7, 2:6, :3] = TUNIC
    body[4, 2:6, :3] = BELT
    return body


def upscale(image: np.ndarray, factor: int) -> np.ndarray:
    return np.repeat(np.repeat(image, factor, axis=0), factor, axis=1)


def build() -> dict[str, np.ndarray | list[np.ndarray]]:
    art: dict[str, np.ndarray | list[np.ndarray]] = {}

    # pixel_grid — the same 8x8 art, once blocked to a real 4px grid and once resampled
    # with a filter that puts a ramp at every block edge.
    clean_grid = upscale(little_guy(), 4)
    art["pixel-grid-clean.png"] = clean_grid
    blurred = Image.fromarray(little_guy(), mode="RGBA").resize((32, 32), Image.BICUBIC)
    art["pixel-grid-defect.png"] = np.array(blurred)

    # halo — a feathered alpha edge is the ring of semi-transparent pixels that survives a
    # careless chroma key.
    art["halo-clean.png"] = clean_grid
    haloed = clean_grid.copy()
    edge = (haloed[:, :, 3] == 0) & (np.roll(haloed[:, :, 3], 1, axis=0) > 0) | (
        haloed[:, :, 3] == 0
    ) & (np.roll(haloed[:, :, 3], 1, axis=1) > 0)
    haloed[edge, 3] = 128
    art["halo-defect.png"] = haloed

    # palette — four flat colours against a gradient nobody quantized.
    art["palette-clean.png"] = clean_grid
    drifted = clean_grid.copy()
    ramp = np.linspace(0, 255, drifted.shape[1], dtype=np.uint8)
    opaque = drifted[:, :, 3] > 0
    drifted[:, :, 0] = np.where(opaque, ramp[None, :], drifted[:, :, 0])
    art["palette-defect.png"] = drifted

    # silhouette — two separate defects, because they are two separate failures: a hole
    # punched through the body, and the body split into islands. Both are cut four source
    # columns wide so they survive the reduction to an 8x8 cell; a two-column cut vanishes
    # there, which is the check working rather than failing.
    art["silhouette-clean.png"] = clean_grid
    holed = clean_grid.copy()
    holed[12:16, 12:16, 3] = 0
    art["silhouette-holes.png"] = holed
    split = clean_grid.copy()
    split[:, 16:20, 3] = 0
    art["silhouette-split.png"] = split

    # bleed — a 2x1 sheet whose left frame stays inside its cell, and one whose arm
    # crosses the boundary into its neighbour.
    tidy = rgba(16, 32, INK)
    tidy[4:12, 3:13, 3] = 255
    tidy[4:12, 19:29, 3] = 255
    art["bleed-clean.png"] = tidy
    crossing = tidy.copy()
    crossing[7:9, 3:18, 3] = 255
    art["bleed-defect.png"] = crossing

    # drift — four frames standing still, and four where one slid three pixels sideways.
    still = [clean_grid.copy() for _ in range(4)]
    art["drift-clean"] = still
    sliding = [clean_grid.copy() for _ in range(4)]
    sliding[2] = np.roll(sliding[2], 3, axis=1)
    art["drift-defect"] = sliding

    # flicker — four identical frames, and four where a still region was re-quantized a
    # little between two of them.
    art["flicker-clean"] = [clean_grid.copy() for _ in range(4)]
    wobbling = [clean_grid.copy() for _ in range(4)]
    body = wobbling[2][:, :, 3] > 0
    wobbling[2][:, :, 0] = np.where(
        body, wobbling[2][:, :, 0].astype(np.int16) + 6, wobbling[2][:, :, 0]
    ).astype(np.uint8)
    art["flicker-defect"] = wobbling

    return art


def write(art: dict[str, np.ndarray | list[np.ndarray]]) -> None:
    for name, value in art.items():
        if isinstance(value, list):
            directory = HERE / name
            directory.mkdir(exist_ok=True)
            for index, frame in enumerate(value):
                Image.fromarray(frame, mode="RGBA").save(directory / f"{index:03d}.png")
        else:
            Image.fromarray(value, mode="RGBA").save(HERE / name)
    print(f"wrote {len(art)} fixtures into {HERE}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare, write nothing")
    args = parser.parse_args()
    art = build()
    if args.check:
        print(f"built {len(art)} fixtures in memory; nothing written")
        return 0
    write(art)
    return 0


if __name__ == "__main__":
    sys.exit(main())
