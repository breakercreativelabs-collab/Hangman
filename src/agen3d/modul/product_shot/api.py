"""Kontrak product_shot untuk modul lain (satu-satunya pintu impor lintas modul, uji struktur e).

- AMBANG: ambang QC-01..12 (modeling_referensi AM-15 dan tvc TV-02/03 memakai aturan yang sama)
- qc_kaca(): QC-11 bahan bening berongga (dipakai QC kapsul modeling_referensi)
"""
from .ambang import AMBANG
from .qc_scene import qc_kaca

__all__ = ["AMBANG", "qc_kaca"]
