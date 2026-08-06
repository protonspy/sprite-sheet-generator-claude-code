"""The scale decision — one visible-height factor per frame set.

The instability that survives everything else `ssc` builds is *between* the animations of
one asset: the sprite that grows two pixels when it starts walking. The fix is one resample
factor per set, bringing every set's visible height onto one target through the project's
single nearest-neighbour resampler (`ssc.core.resize.resize`). The arithmetic is pure here;
the command that applies it is `ssc tool normalise`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ssc.core.assemble import MAX_CANVAS, Layout, Place, pack, plan_alignment
from ssc.core.doctor.masks import set_visible_height
from ssc.core.resize import ResizeParams, resize


def scale_target(visible_heights: Sequence[int]) -> int:
    """The one visible height the sets are resampled onto: the median of the sets' medians.

    The median, not the max, so a single outsized set does not pull every other set up to
    it; the median, not the mean, so the target is a whole pixel a nearest-neighbour
    resampler can hit rather than a fraction it cannot. A blank set — height zero — has no
    height to scale from or onto, and is refused rather than averaged in to a target it
    would move.
    """
    if any(height <= 0 for height in visible_heights):
        raise ValueError("a set with no visible height cannot be scaled")
    return round(float(np.median(visible_heights)))


def scale_factor(src_visible_height: int, target: int) -> float:
    """The factor that puts one set's visible height onto the target: `target / src`.

    A set already on the target gets `1.0` and is left untouched by the normaliser, since
    resampling it would risk the very drift the gate exists to remove, for no gain.
    """
    if src_visible_height <= 0:
        raise ValueError("a set with no visible height cannot be scaled")
    return target / src_visible_height


def scaled_size(canvas: tuple[int, int], factor: float) -> tuple[int, int]:
    """The resampled canvas, the source scaled uniformly by `factor` and rounded to pixels.

    One factor for width and height both, so the sprite's proportions survive; rounded to
    whole pixels, because the resampler takes integers and a fractional cell is not a cell
    an engine can address. Clamped to at least one pixel and at most `MAX_CANVAS`, so a
    giant set onto a tiny target cannot round the canvas away and a tiny set onto a giant
    target cannot blow the canvas ceiling the rest of the pipeline enforces.
    """
    width, height = canvas
    out_w = max(1, min(MAX_CANVAS, round(width * factor)))
    out_h = max(1, min(MAX_CANVAS, round(height * factor)))
    return (out_w, out_h)


@dataclass(frozen=True)
class ScalePlan:
    """One set's scale decision: the factor to apply, and the canvas the resampler lands on."""

    factor: float
    canvas: tuple[int, int]


def scale_plan(
    visible_heights: Sequence[int], canvases: Sequence[tuple[int, int]], target: int
) -> list[ScalePlan]:
    """One factor and one output canvas per set, all on `target`.

    A set already on the target is unchanged — factor `1.0` and its own canvas back — so the
    normaliser can skip the resampler for it entirely rather than run an identity resample
    that costs a pass and risks a rounding pixel.
    """
    if len(visible_heights) != len(canvases):
        raise ValueError("each set needs one visible height and one canvas")
    plans: list[ScalePlan] = []
    for height, canvas in zip(visible_heights, canvases, strict=True):
        factor = scale_factor(height, target)
        plans.append(ScalePlan(factor=factor, canvas=scaled_size(canvas, factor)))
    return plans


# ── the gate ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Normalised:
    """The sets of one asset on one baseline, one centre column and one canvas.

    `sheets` is one packed sheet per input set, every cell the same size and every sheet's
    anchor the same pixel — which is what makes an engine place idle and walk against the
    same floor and the same centreline. `factors` is the per-set resample factor that put
    each set's visible height on `target`.
    """

    sheets: list[np.ndarray]
    layout: Layout
    target: int
    factors: list[float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sets": len(self.sheets),
            "target": self.target,
            "factors": self.factors,
            "canvas": {"width": self.layout.cell[0], "height": self.layout.cell[1]},
            "anchor": {"x": self.layout.anchor[0], "y": self.layout.anchor[1]},
            "aligned": self.layout.aligned,
        }


def normalise_sets(
    sets: list[list[np.ndarray]], *, mode: Place = "feet", columns: int = 0
) -> Normalised:
    """Put the frame sets of one asset on one baseline, one centre column and one canvas.

    The scale decision (4.1) resamples each set onto one target visible height through the
    project's single resampler. Then `plan_alignment` moves every frame of every set onto one
    anchor pixel — the cross-set baseline and centre column `tool align` locks within a set but
    nothing else makes agree between sets — and `pack` lays each set out as a sheet of equal
    cells. Padding is `plan_alignment`'s canvas growth and layout is `pack`'s grid; this
    function orchestrates the two and resampling, and implements neither padding nor layout
    itself.
    """
    if not sets:
        raise ValueError("nothing to normalise: give at least one frame set")

    set_heights = [set_visible_height(frames) for frames in sets]
    target = scale_target(set_heights)
    factors = [scale_factor(height, target) for height in set_heights]

    resampled_sets: list[list[np.ndarray]] = []
    for frames, factor in zip(sets, factors, strict=True):
        if factor == 1.0:
            # Already on target; an identity resample would cost a pass and risk a rounding
            # pixel for no gain.
            resampled_sets.append(frames)
            continue
        resampled_sets.append(
            [
                resize(frame, ResizeParams(*scaled_size((frame.shape[1], frame.shape[0]), factor)))
                for frame in frames
            ]
        )

    # Align across sets, not within: the baseline and centre that agree inside one animation
    # are the ones that have to agree between two, so every frame of every set goes through
    # one `plan_alignment`.
    aligned = plan_alignment([frame for frames in resampled_sets for frame in frames], mode=mode)
    canvas = (aligned.frames[0].shape[1], aligned.frames[0].shape[0])

    sheets: list[np.ndarray] = []
    layout: Layout | None = None
    index = 0
    for frames in resampled_sets:
        count = len(frames)
        set_frames = aligned.frames[index : index + count]
        index += count
        sheet, layout = pack(
            set_frames, columns=columns if columns >= 1 else count, cell=canvas, mode=mode
        )
        sheets.append(sheet)
    assert layout is not None
    return Normalised(sheets=sheets, layout=layout, target=target, factors=factors)
