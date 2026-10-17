"""Kontrak modeling_referensi untuk modul lain (tvc). Satu-satunya pintu impor lintas modul (uji struktur e).

- muat_proyek(id): muat proyek.toml + data referensi (wajib sebelum fungsi lain)
- path_model(): path .blend model hasil QC/bangun (artefak, dipakai tvc)
- bangun_model(**param) / simpan_model(path): bangun scene model (M1+M2+M3) dan simpan .blend
- studio_palet(): studio cek mata palet proyek (gradasi + softbox + rim), dipakai tvc
- qc_slot_material(): AM-18 (material peran non-default), diuji ulang di scene tvc
"""
import os

import bpy

from .sepatu import data
from .sepatu.qc_material import qc_slot_material
from .sepatu.sol import bangun_sepatu as bangun_model
from .sepatu.studio import studio_p3 as studio_palet


def muat_proyek(proyek="am1"):
    return data.muat_data(proyek)


def path_model():
    return data.path_keluaran("blend")


def simpan_model(path=None):
    path = os.path.abspath(path or path_model())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)  # C-10: path absolut
    return path


__all__ = ["muat_proyek", "path_model", "bangun_model", "simpan_model", "studio_palet", "qc_slot_material"]
