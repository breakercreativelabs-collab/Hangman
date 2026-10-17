"""Baca foto referensi (PNG beralfa) sebagai array RGBA float, dengan langkah sampel."""
import os

import bpy
import numpy as np


def baca_foto(folder, nama, langkah=2, atas_dulu=True):
    """<folder>/<nama>.png -> array (h, w, 4) disampel tiap `langkah` px. atas_dulu: baris 0 = atas gambar
    (konvensi ekstraksi kontur/panel); False: baris 0 = bawah (konvensi Blender)."""
    im = bpy.data.images.load(os.path.join(folder, nama + ".png"))
    w, h = im.size
    p = np.empty(w * h * 4, np.float32)
    im.pixels.foreach_get(p)
    bpy.data.images.remove(im)
    p = p.reshape(h, w, 4)
    return (p[::-1] if atas_dulu else p)[::langkah, ::langkah]
