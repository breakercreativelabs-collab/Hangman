"""Analisis kanal alfa foto referensi (di klien/<proyek>, tidak masuk repo).

Foto produk (AM1: CDN brand) berisi persegi bayangan semi-transparan di belakang sepatu, sehingga
alfa > 0 tidak sama dengan sepatu. Skrip ini mencetak distribusi alfa dan menyimpan
masker uji (ke folder referensi, bukan repo) untuk dicek mata sekali.
  blender -b --factory-startup -P blender_cli.py -- modeling_referensi analisis_alfa --ref <folder_referensi>
"""
import os

import bpy
import numpy as np

from .foto import baca_foto


def simpan(REF, nama, masker):
    h, w = masker.shape
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[..., :3] = masker[..., None]
    rgba[..., 3] = 1
    im = bpy.data.images.new(nama, w, h)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw, im.file_format = os.path.join(REF, nama + ".png"), "PNG"
    im.save()


def analisis_alfa(REF):
    for nama in ("lateral", "medial", "atas", "tumit", "sol"):
        p = baca_foto(REF, nama, 3, atas_dulu=False)  # baris 0 = bawah
        a = p[..., 3]
        q = np.quantile(a[a > 0.01], [0.05, 0.25, 0.5, 0.75, 0.95]) if (a > 0.01).any() else []
        hist = np.histogram(a, bins=[0, 0.01, 0.2, 0.4, 0.6, 0.8, 0.95, 0.99, 1.01])[0] / a.size
        print(f"ALFA {nama}: kuantil(a>0.01)={np.round(q, 3).tolist()} hist={np.round(hist, 3).tolist()}")
        simpan(REF, f"_masker_{nama}_a099", (a > 0.99).astype(np.float32))
