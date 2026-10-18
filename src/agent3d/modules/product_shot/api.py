"""product_shot contract for other modules (the only cross-module import point, structure test e).

- THRESHOLD: QC-01..12 thresholds (reference_modeling AM-15 and tvc TV-02/03 use the same rules)
- qc_glass(): QC-11 hollow clear material check (used by the reference_modeling capsule QC)
"""
from .threshold import THRESHOLD
from .qc_scene import qc_glass

__all__ = ["THRESHOLD", "qc_glass"]
