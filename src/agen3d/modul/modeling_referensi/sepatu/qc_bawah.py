"""QC resep sepatu M1 (bagian bawah): AM-01 siluet samping, AM-02 plan, AM-03 garis midsole, AM-04 jendela Air,
AM-05 ukuran, AM-06 siluet medial (independen), AM-07 tapak/banding, AM-08 takik dinding midsole.
Setiap cek = satu baris ATURAN_QC.md proyek (AM-xx). Konvensi sumbu: data.py."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ....inti.io import baca_rgba
from ....inti.kamera import kamera
from ....inti.qc import cek
from ....inti.render import render_gambar
from ....inti.scene import objek_produk
from ..geometri import mm
from ..penyaring import opening, rata_geser
from ..qc_siluet import masker_poligon
from . import data
from .ambang import AMBANG, CARI_JENDELA, KOLOM_MIN, PIX, RAY, VIEW


# ---------------- render ortografis -> masker ----------------
def masker(view, folder):
    """Render ortografis Cycles (16 sampel, film transparan), masker = alfa > 0,5. Baris 0 = bawah gambar.
    Sumbu: samping -> (x, z), kamera di -Y; bawah -> (x, y), kamera di bawah, atas gambar = -Y."""
    v = VIEW[view]
    (h0, h1), (v0, v1) = v["h"], v["v"]
    W, H = round((h1 - h0) / PIX), round((v1 - v0) / PIX)
    hc, vc = (h0 + h1) / 2, (v0 + v1) / 2
    if view == "samping":
        cam = kamera("CAM_orto_samping", (mm(hc), -0.6, mm(vc)), (math.pi / 2, 0, 0), mm(h1 - h0))
    else:
        cam = kamera("CAM_orto_bawah", (mm(hc), mm(vc), -0.6), (math.pi, 0, 0), mm(h1 - h0))
    path = render_gambar(cam, os.path.join(folder, f"masker_{view}.png"), W, H, 16, True)
    m = baca_rgba(path)[..., 3] > 0.5
    hs = h0 + (np.arange(W) + 0.5) * PIX
    vs = v0 + (np.arange(H) + 0.5) * PIX
    if view == "bawah":
        vs = v1 - (np.arange(H) + 0.5) * PIX  # atas gambar = -Y -> baris bawah = +Y
    return m, hs, vs


def masker_data(view, hs, vs):
    """Poligon data dirasterisasi di grid yang sama (x-monoton: bawah(x) <= v <= atas(x))."""
    if view == "samping":
        x, lo, hi = data.profil_samping("lateral")
    elif view == "samping_medial":
        x, lo, hi = data.profil_samping("medial")
    else:
        x, lo, hi = data.plan_data_y()
    return masker_poligon(hs, vs, x, lo, hi)


# ---------------- ray dari samping ----------------
def _ray(dg, x, z, sisi=1, y0=300.0):
    """Ray mendatar dari sisi lateral (+Y, sisi=1) atau medial (-Y). Kembalikan nama objek pertama yang kena atau None."""
    hit, _, _, _, ob, _ = bpy.context.scene.ray_cast(dg, Vector((mm(x), mm(sisi * y0), mm(z))),
                                                       Vector((0, -sisi, 0)))
    return ob.name if hit else None


def peta_samping(x0, x1, z0, z1, sisi=1, langkah=RAY):
    dg = bpy.context.evaluated_depsgraph_get()
    xs = np.arange(x0, x1, langkah) + langkah / 2
    zs = np.arange(z0, z1, langkah) + langkah / 2
    kode = {"midsole": 1, "outsole": 2, "kapsul_air": 4}
    peta = np.zeros((len(zs), len(xs)), np.int8)
    for i, z in enumerate(zs):
        for j, x in enumerate(xs):
            nama = _ray(dg, x, z, sisi)
            peta[i, j] = 0 if nama is None else kode.get(nama, 3)  # 3 = upper/panel apa pun (AM-C07)
    return peta, xs, zs


def ukur_jendela(peta, xs, zs):
    """Kolom jendela = ray pertama kena kapsul atau menembus, hanya di CARI_JENDELA. Kolom dihitung jika tingginya >= 3 mm."""
    x0, x1, z0, z1 = CARI_JENDELA
    jen = ((peta == 4) | (peta == 0)) & (zs[:, None] >= z0) & (zs[:, None] <= z1)
    kol = []
    for j, x in enumerate(xs):
        if not x0 <= x <= x1:
            continue
        z = zs[jen[:, j]]
        if len(z) * RAY >= KOLOM_MIN:
            kol.append((float(x), float(z.min()), float(z.max())))
    if not kol:
        return None, []
    k = np.array(kol)
    return (float(k[:, 0].min()), float(k[:, 0].max()), float(k[:, 1].min()), float(k[:, 2].max())), kol


def qc_jendela(peta, xs, zs, sisi_nama):
    d = data.bbox_jendela_data()
    m, kol = ukur_jendela(peta, xs, zs)
    a = AMBANG["jendela_mm"]
    if m is None:
        return cek("AM-04", f"jendela_air_galat_mm_{sisi_nama}", 99.0, False, f"<= {a} mm", "jendela tidak ditemukan")
    g = dict(pusat_x=(m[0] + m[1]) / 2 - (d[0] + d[1]) / 2, pusat_z=(m[2] + m[3]) / 2 - (d[2] + d[3]) / 2,
             lebar=(m[1] - m[0]) - (d[1] - d[0]), tinggi=(m[3] - m[2]) - (d[3] - d[2]))
    nilai = max(abs(v) for v in g.values())
    return cek("AM-04", f"jendela_air_galat_mm_{sisi_nama}", nilai, nilai <= a, f"<= {a} mm (pusat x/z, lebar, tinggi)",
               f"model x {m[0]:.1f}-{m[1]:.1f} z {m[2]:.1f}-{m[3]:.1f} vs data x {d[0]:.1f}-{d[1]:.1f} "
               f"z {d[2]:.1f}-{d[3]:.1f}; " + ", ".join(f"{k} {v:+.2f}" for k, v in g.items()))


def garis_midsole_model(xs_data, z_data):
    """Garis atas midsole yang TERLIHAT dari lateral: z tertinggi di mana ray pertama kena midsole (scan 0,5 mm, lalu
    bisection 0,01 mm). Ini yang dilihat kamera, jadi upper yang menggembung melewati bibir midsole ikut tertangkap."""
    dg = bpy.context.evaluated_depsgraph_get()
    hasil = []
    for x, zd in zip(xs_data, z_data):
        zs = np.arange(zd - 15.0, zd + 15.0, 0.5)
        kena = [_ray(dg, x, z) == "midsole" for z in zs]
        idx = [i for i in range(len(zs) - 1) if kena[i] and not kena[i + 1]]
        if not idx:
            hasil.append(np.nan)
            continue
        lo, hi = zs[idx[-1]], zs[idx[-1] + 1]
        while hi - lo > 0.01:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _ray(dg, x, mid) == "midsole" else (lo, mid)
        hasil.append((lo + hi) / 2)
    return np.array(hasil)


def qc_midsole():
    mid, buang = data.garis_midsole()
    zm = garis_midsole_model(mid[:, 0], mid[:, 1])
    ok = ~np.isnan(zm)
    g = np.abs(zm[ok] - mid[ok, 1])
    nilai = float(g.mean()) if ok.any() else 99.0
    a = AMBANG["midsole_mm"]
    return cek("AM-03", "garis_atas_midsole_galat_rata_mm", nilai, ok.all() and nilai <= a, f"<= {a} mm",
               f"{ok.sum()}/{len(ok)} titik, maks {g.max():.2f} mm, median {np.median(g):.2f}; "
               f"{len(buang)} pencilan data dibuang (aturan tetap |z - median tetangga| > 5 mm: "
               + ", ".join(f"x {p[0]:.1f} z {p[1]:.1f}" for p in buang) + ")"), (mid, zm)


def qc_ukuran():
    dg = bpy.context.evaluated_depsgraph_get()
    p = []
    for ob in objek_produk():
        e = ob.evaluated_get(dg)
        v = np.empty(len(e.data.vertices) * 3)
        e.data.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3) @ np.array(e.matrix_world)[:3, :3].T + np.array(e.matrix_world)[:3, 3]
        p.append(v)
    p = np.vstack(p) * 1000
    panjang = float(p[:, 0].max() - p[:, 0].min())
    depan = p[p[:, 0] < p[:, 0].min() + panjang / 2]
    lebar = float(depan[:, 1].max() - depan[:, 1].min())
    sp, sl = data.PANJANG, data.LAB["lebar_forefoot_mm"]
    gp, gl = panjang - sp, lebar - sl
    return [cek("AM-05", "panjang_galat_mm", gp, abs(gp) <= AMBANG["panjang_mm"], f"|g| <= {AMBANG['panjang_mm']} mm",
                f"{panjang:.2f} vs {sp} mm [D] (kalibrasi)"),
            cek("AM-05", "lebar_forefoot_galat_mm", gl, abs(gl) <= AMBANG["lebar_mm"], f"|g| <= {AMBANG['lebar_mm']} mm",
                f"{lebar:.2f} vs {sl} mm [F] lab RunRepeat")]


def dasar_midsole_model(xs):
    """Tepi BAWAH midsole yang terlihat dari lateral: z terendah di mana ray pertama kena midsole (scan 0,5 mm, lalu
    bisection 0,01 mm). Takik di dasar sol (C-A2) tampak sebagai lonjakan naik garis ini."""
    dg = bpy.context.evaluated_depsgraph_get()
    hasil = []
    for x in xs:
        zs = np.arange(0.0, 60.0, 0.5)
        idx = next((i for i, z in enumerate(zs) if _ray(dg, x, z) == "midsole"), None)
        if not idx:
            hasil.append(np.nan)
            continue
        lo, hi = zs[idx - 1], zs[idx]
        while hi - lo > 0.01:
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if _ray(dg, x, mid) == "midsole" else (mid, hi)
        hasil.append((lo + hi) / 2)
    return np.array(hasil)


def qc_takik():
    """AM-08 (C-A2): takik di dinding samping midsole = tepi bawah midsole dikurangi selubung bawahnya
    (opening 21 mm: puncak sempit dibuang, toe spring & bevel tumit tetap). Kedalaman maks."""
    mid, _ = data.garis_midsole()
    xs = np.arange(mid[0, 0] + 3.0, mid[-1, 0] - 3.0, 1.0)
    z = dasar_midsole_model(xs)
    ok = ~np.isnan(z)
    a = AMBANG["takik_mm"]
    if ok.sum() < 10:
        return cek("AM-08", "takik_dinding_midsole_mm", 99.0, False, f"<= {a} mm", "dasar midsole tidak terukur")
    d = z[ok] - opening(xs[ok], z[ok])
    i = int(np.argmax(d))
    return cek("AM-08", "takik_dinding_midsole_mm", float(d[i]), d[i] <= a and ok.all(), f"<= {a} mm",
               f"{ok.sum()}/{len(ok)} x terukur (1 mm), terdalam di x {xs[ok][i]:.0f} mm; "
               f"{int((d > 0.5).sum())} x dengan takik > 0,5 mm")


def render_bawah_shaded(folder, lantai):
    """Tampak bawah berbayang di grid yang sama dengan masker AM-02 (0,5 mm/px), lantai disembunyikan."""
    sc = bpy.context.scene
    v = VIEW["bawah"]
    (h0, h1), (v0, v1) = v["h"], v["v"]
    cam = kamera("CAM_orto_bawah", (mm((h0 + h1) / 2), mm((v0 + v1) / 2), -0.6), (math.pi, 0, 0), mm(h1 - h0))
    den, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    lantai.hide_render = True
    path = render_gambar(cam, os.path.join(folder, "bawah_qc.png"), round((h1 - h0) / PIX), round((v1 - v0) / PIX), 24, False)
    lantai.hide_render = False
    sc.cycles.use_denoising = den
    return path


def qc_tapak(folder, m_bawah, lantai):
    """AM-07 (C-A1) di outsole tampak bawah (masker AM-02 dikikis 10 mm, x 20-275 mm):
    banding = std rata-rata luma per kolom setelah dikurangi rata-rata geser 15 mm (garis vertikal antar stasiun /
    tapak berarah X); tapak = std luma frekuensi tinggi (luma - blur 2,5 mm), harus cukup agar pola terbaca."""
    path = render_bawah_shaded(folder, lantai)
    L = baca_rgba(path)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], "f")
    r = int(10 / PIX)
    dalam = m_bawah.copy()
    for _ in range(r):
        dalam = dalam & np.roll(dalam, 1, 0) & np.roll(dalam, -1, 0) & np.roll(dalam, 1, 1) & np.roll(dalam, -1, 1)
    hs = VIEW["bawah"]["h"][0] + (np.arange(L.shape[1]) + 0.5) * PIX
    dalam &= ((hs >= 20) & (hs <= 275))[None]
    # banding = sqrt(kovarians) rata-rata kolom separuh atas vs bawah: garis antar stasiun loft menembus seluruh lebar
    # sol (koheren), tekstur tapak acak tidak (kovarians ~0). Std biasa mencampur keduanya (Voronoi 0,024 vs polos 0,009).
    kol = np.nonzero(dalam.sum(0) >= 40)[0]
    hp = lambda c: c - rata_geser(c, int(15 / PIX) | 1, 0)
    atas, bawah = [], []
    for j in kol:
        i = np.nonzero(dalam[:, j])[0]
        tengah = (i.min() + i.max()) // 2
        atas.append(L[i[i > tengah], j].mean())
        bawah.append(L[i[i <= tengah], j].mean())
    kov = float(np.mean(hp(np.array(atas)) * hp(np.array(bawah))))
    banding = math.sqrt(max(kov, 0.0))
    blur = rata_geser(rata_geser(L, 5, 0), 5, 1)
    tapak = float(np.std((L - blur)[dalam]))
    return [cek("AM-07", "banding_kolom_bawah", banding, banding <= AMBANG["banding_maks"], f"<= {AMBANG['banding_maks']}",
                f"{len(kol)} kolom, rata-rata luma outsole {float(L[dalam].mean()):.3f}"),
            cek("AM-07", "kontras_tapak_bawah", tapak, tapak >= AMBANG["tapak_min"], f">= {AMBANG['tapak_min']}",
                f"{int(dalam.sum())} px outsole")], path
