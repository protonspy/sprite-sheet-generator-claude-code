"""`doctor` — measure a finished asset, name the command that repairs each defect.

Pure: arrays in, findings out. The command that reads files is `ssc.cli.commands.doctor`.
"""

from ssc.core.doctor.checks import (
    BleedParams,
    DriftParams,
    FlickerParams,
    HaloParams,
    NineSliceParams,
    PaletteParams,
    PixelGridParams,
    SeamParams,
    SilhouetteParams,
    check_bleed,
    check_drift,
    check_flicker,
    check_halo,
    check_nineslice,
    check_palette,
    check_pixel_grid,
    check_seam,
    check_silhouette,
    detect_pixel_size,
)
from ssc.core.doctor.finding import Check, Finding, Report, Status

__all__ = [
    "BleedParams",
    "Check",
    "DriftParams",
    "Finding",
    "FlickerParams",
    "HaloParams",
    "NineSliceParams",
    "PaletteParams",
    "PixelGridParams",
    "Report",
    "SeamParams",
    "SilhouetteParams",
    "Status",
    "check_bleed",
    "check_drift",
    "check_flicker",
    "check_halo",
    "check_nineslice",
    "check_palette",
    "check_pixel_grid",
    "check_seam",
    "check_silhouette",
    "detect_pixel_size",
]
