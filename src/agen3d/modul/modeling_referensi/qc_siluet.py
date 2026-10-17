"""QC generik modeling dari referensi: IoU masker, rasterisasi poligon data, overlay data vs model, ray ke satu
objek, uji titik di dalam mesh, riak normal, hue rata-rata sirkular."""
import math

import numpy as np
from mathutils import Vector

from ...inti import warna
from ...inti.io import simpan_gambar


def masker_poligon(hs, vs, x, lo, hi):
    """Poligon data x-monoton (bawah(x) <= v <= atas(x)) dirasterisasi di grid (hs kolom, vs baris)."""
    LO, HI = np.interp(hs, x, lo), np.interp(hs, x, hi)
    dalam_x = (hs >= x[0]) & (hs <= x[-1])
    V = vs[:, None]
    return (V >= LO[None]) & (V <= HI[None]) & dalam_x[None]


def overlay_masker(m, d, path):
    """Abu muda = model & data; biru = model saja; merah = data saja (kontur data vs siluet model)."""
    rgb = np.full(m.shape + (3,), 0.10, "f")
    rgb[m & d] = (0.78, 0.78, 0.78)
    rgb[m & ~d] = (0.20, 0.45, 0.95)
    rgb[~m & d] = (0.95, 0.20, 0.15)
    tepi = d & ~(np.roll(d, 1, 0) & np.roll(d, -1, 0) & np.roll(d, 1, 1) & np.roll(d, -1, 1))
    rgb[tepi] = (0.95, 0.20, 0.15)  # garis kontur data
    return simpan_gambar(path, rgb, "ovl")


def ray_ob(ob, asal_mm, arah, halus=False):
    """Ray ke SATU objek (abaikan objek lain). Kembalikan (lokasi mm dunia, normal dunia) atau None.
    halus=True: normal shading (interpolasi normal vertex, bobot 1/jarak) - yang dilihat render; normal face mentah
    berisi lompatan faset antar cincin loft (~3-6 derajat) yang bukan gelombang."""
    mw = ob.matrix_world
    inv = mw.inverted()
    o = inv @ (Vector(asal_mm) / 1000.0)
    d = (inv.to_3x3() @ Vector(arah)).normalized()
    ok, loc, nrm, fi = ob.ray_cast(o, d)
    if not ok:
        return None
    if halus:
        me = ob.data
        vs = me.polygons[fi].vertices
        w = [1.0 / ((me.vertices[i].co - loc).length + 1e-7) for i in vs]
        nrm = sum((me.vertices[i].normal * wi for i, wi in zip(vs, w)), Vector()) / sum(w)
    return (mw @ loc) * 1000.0, (inv.to_3x3().transposed() @ nrm).normalized()


def di_dalam(bvh, q):
    """Titik di dalam mesh tertutup: paritas jumlah perpotongan ray +Z (dan -Z sebagai cek; keduanya harus ganjil)."""
    hasil = []
    for arah in (Vector((0, 0, 1)), Vector((0.0123, 0.0071, -1)).normalized()):
        n, o = 0, q.copy()
        for _ in range(64):
            loc, _, _, _ = bvh.ray_cast(o, arah)
            if loc is None:
                break
            n += 1
            o = loc + arah * 1e-4
        hasil.append(n % 2 == 1)
    return all(hasil)


def riak_deg(normal, jendela=15):
    """RMS sudut antara normal dan rata-rata gesernya (`jendela` sampel): riak/gelombang antar stasiun. Lengkung
    besar yang halus hampir tidak menyumbang, gelombang 1-5 mm terbaca penuh."""
    N = np.array(normal)
    k = np.ones(jendela) / jendela
    rata = np.stack([np.convolve(np.pad(N[:, i], jendela // 2, mode="edge"), k, "valid") for i in range(3)], 1)
    rata /= np.linalg.norm(rata, axis=1, keepdims=True)
    sudut = np.degrees(np.arccos(np.clip((N * rata).sum(1), -1, 1)))
    return float(np.sqrt(np.mean(sudut[jendela // 2:-(jendela // 2)] ** 2)))


def hue_rata(px):
    """Rata-rata hue sirkular (bobot saturasi) piksel (n, 3) -> (hue 0..1, jumlah piksel bersaturasi >= 0,15)."""
    hsv = np.array([warna.hsv(p) for p in px])
    pakai = hsv[:, 1] >= 0.15
    if pakai.sum() < 30:
        return float("nan"), int(pakai.sum())
    a = hsv[pakai, 0] * 2 * math.pi
    wgt = hsv[pakai, 1]
    return (math.atan2((np.sin(a) * wgt).sum(), (np.cos(a) * wgt).sum()) / (2 * math.pi)) % 1.0, int(pakai.sum())
