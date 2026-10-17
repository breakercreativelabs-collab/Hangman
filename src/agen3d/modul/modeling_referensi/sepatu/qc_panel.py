"""QC panel GENERIK (proyek panel data kelas warna, Tugas 11): AM-10g IoU proyeksi tiap panel per sisi vs poligon data.

AM-10 AM1 (swoosh) diperluas ke semua panel `[[model.panel]]` alas upper. Proyeksi = ray sepanjang Y ke objek panel
sisi itu saja (abaikan objek lain), grid 0,25 mm (panel < 1500 mm2) atau 0,5 mm. Ambang per panel = lantai data:
IoU poligon data vs dirinya digeser (0,5; 0,5) mm (aturan AM-10 AM1: galat <= setengah jarak kolom data), dihitung
dari data, bukan dipilih. Tautologis (data yang sama membangun): cek konsistensi build. Independen = AM-06 + mata.
"""
import bpy
import numpy as np

from ....inti.qc import cek, iou
from ..qc_siluet import masker_poligon, ray_ob
from . import data
from .panel_data import spesifikasi


def raster_poligon(hs, vs, polis, geser=(0.0, 0.0)):
    """Poligon {luar, lubang} (mm) -> masker grid (baris = vs, kolom = hs), scanline genap-ganjil (lubang terkurang)."""
    m = np.zeros((len(vs), len(hs)), bool)
    for pg in polis:
        for loop in [pg["luar"]] + list(pg["lubang"]):
            P = np.array(loop, float) + np.array(geser)
            A, B = P, np.roll(P, -1, 0)
            for i, v in enumerate(vs):
                sil = ((A[:, 1] <= v) & (B[:, 1] > v)) | ((B[:, 1] <= v) & (A[:, 1] > v))
                if not sil.any():
                    continue
                a, b = A[sil], B[sil]
                xs = np.sort(a[:, 0] + (v - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1]))
                for x0, x1 in zip(xs[0::2], xs[1::2]):
                    m[i] ^= (hs >= x0) & (hs < x1)
    return m


def qc_panel_iou():
    """Kembalikan (daftar cek AM-10, artefak {nama_sisi: (masker model, masker data)})."""
    hasil, art = [], {}
    for sp in spesifikasi():
        if sp.get("alas", "upper") != "upper":
            continue
        nama = sp["nama"]
        for sisi, sg in (("lateral", 1), ("medial", -1)):
            polis = data.panel_kelas(nama, sisi)
            if not polis:
                continue
            P = np.vstack([np.array(pg["luar"], float) for pg in polis])
            luas = sum(abs(0.5 * float(np.dot(Q[:, 0], np.roll(Q[:, 1], -1)) - np.dot(np.roll(Q[:, 0], -1), Q[:, 1])))
                       for Q in (np.array(pg["luar"], float) for pg in polis))
            r = 0.25 if luas < 1500 else 0.5
            hs = np.arange(P[:, 0].min() - 2, P[:, 0].max() + 2, r) + r / 2
            vs = np.arange(P[:, 1].min() - 2, P[:, 1].max() + 2, r) + r / 2
            # data dipotong ke siluet sisi itu: poligon sengaja melewati tepi siluet (luar_mm) agar tepi melengkung
            # tertutup; bagian di luar siluet tidak punya permukaan untuk diproyeksikan
            sx, slo, shi = data.profil_samping(sisi)
            sil = masker_poligon(hs, vs, sx, slo, shi)
            d = raster_poligon(hs, vs, polis) & sil
            lantai = iou(d, raster_poligon(hs, vs, polis, (0.5, 0.5)) & sil)
            obs = [o for o in bpy.context.scene.objects if o.get("panel") == nama]
            m = np.zeros_like(d)
            for o in obs:  # objek panel = potongan L + M; hanya titik kena di separuh sisi ini yang dihitung
                for i, z in enumerate(vs):
                    for j, x in enumerate(hs):
                        if m[i, j]:
                            continue
                        h = ray_ob(o, (x, sg * 300.0, z), (0, -sg, 0))
                        if h is not None and sg * (h[0].y - data.plan_y(min(max(x, 0.0), data.PANJANG))[0]) >= 0.0:
                            m[i, j] = True
            v = iou(m, d)
            hasil.append(cek("AM-10", f"iou_{nama}_{sisi}", v, v >= lantai, f">= {lantai:.4f} (lantai data)",
                             f"{int(m.sum())} px model, {int(d.sum())} px data, {r} mm/px; lantai = IoU data vs data "
                             f"geser (0,5; 0,5) mm" + ("" if obs else "; objek panel tidak ada")))
            art[f"{nama}_{sisi}"] = (m, d)
    return hasil, art
