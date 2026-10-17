"""Render cek mata resep sepatu (tampak, studio P3), swatch peran, overlay data vs model (tumit, mudguard)."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ....inti.io import simpan_gambar
from ....inti.kamera import hadap, kamera
from ....inti.render import render_gambar
from ....inti.warna import hex_rgb
from ..qc_siluet import ray_ob
from . import data
from .ambang import RAY
from .qc_bawah import ukur_jendela
from .qc_upper import cari_objek
from .studio import pakai_studio


def render_p3(folder):
    """Render cek mata di studio P3: hero 3/4, samping kiri/kanan, makro kapsul, makro mesh/suede. Eksposur -0,5
    (AM-C02: pastel terang menyatu/rata di Khronos PBR Neutral pada eksposur 0)."""
    sc = bpy.context.scene
    pakai_studio("p3")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", -0.5
    den, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    pusat = Vector((0.147, 0.0, 0.06))
    cams = {
        "p3_hero": (kamera("CAM_p3_hero", (-0.16, 0.36, 0.17), (0, 0, 0), lensa=50), pusat, 720, 480),
        "p3_lateral": (kamera("CAM_p3_lat", (0.147, 0.55, 0.075), (0, 0, 0), lensa=50), Vector((0.147, 0, 0.06)), 640, 360),
        "p3_medial": (kamera("CAM_p3_med", (0.147, -0.55, 0.075), (0, 0, 0), lensa=50), Vector((0.147, 0, 0.06)), 640, 360),
        "p3_makro_kapsul": (kamera("CAM_p3_kap", (0.235, 0.15, 0.04), (0, 0, 0), lensa=70), Vector((0.2163, 0.045, 0.02)), 480, 320),
        "p3_makro_mesh": (kamera("CAM_p3_mesh", (0.035, 0.12, 0.085), (0, 0, 0), lensa=70), Vector((0.07, 0.04, 0.045)), 480, 320),
    }
    out = {}
    lampu = [o for o in bpy.data.objects if o.name.startswith("P3_") and o.type == "LIGHT"]
    asal = {o.name: o.location.copy() for o in lampu}
    for nama, (cam, t, w, h) in cams.items():
        hadap(cam, t)
        for o in lampu:  # key selalu di sisi kamera, rim di seberangnya (medial = cermin Y)
            p = asal[o.name]
            o.location = (p.x, p.y if cam.location.y >= 0 else -p.y, p.z)
            hadap(o, Vector((0.147, 0.0, 0.05)))
        out[nama] = render_gambar(cam, os.path.join(folder, f"{nama}.png"), w, h, 32, False)
    for o in lampu:
        o.location = asal[o.name]
        hadap(o, Vector((0.147, 0.0, 0.05)))
    sc.cycles.use_denoising = den
    pakai_studio("review")
    return out


def swatch_png(folder, swatch):
    """Satu PNG per peran: kiri = hex P3 target, kanan = median render netral (AM-15)."""
    out = {}
    for peran, (hexa, med, _) in swatch.items():
        rgb = np.zeros((60, 120, 3), "f")  # nilai tampilan (sRGB) langsung, sama dengan yang dibaca baca_png
        rgb[:, :60] = hex_rgb(hexa)
        rgb[:, 60:] = med
        out[peran] = simpan_gambar(os.path.join(folder, f"swatch_{peran}.png"), rgb, "ovl")
    return out


# ---------------- gambar overlay ----------------
def overlay_tumit(art, path):
    """Peta objek lateral (tumit) + garis atas midsole data (merah) + kolom jendela data (kuning) + bbox model (cyan)."""
    peta, xs, zs = art["peta"]
    warna = np.array([(0.10, 0.10, 0.10), (0.88, 0.88, 0.86), (0.35, 0.35, 0.36), (0.55, 0.55, 0.58),
                      (0.45, 0.70, 1.00)], "f")
    rgb = warna[peta]
    ij = lambda x, z: (int((z - zs[0]) / RAY + 0.5), int((x - xs[0]) / RAY + 0.5))

    def titik(x, z, c, r=1):
        i, j = ij(x, z)
        if 0 <= i < rgb.shape[0] and 0 <= j < rgb.shape[1]:
            rgb[max(i - r, 0):i + r + 1, max(j - r, 0):j + r + 1] = c
    mid, _ = art["midsole"]
    for x, z in mid:
        titik(x, z, (0.95, 0.15, 0.15))
    jx, jb, jt = data.jendela_data()
    for x, b, t in zip(jx, jb, jt):
        titik(x, b, (1.0, 0.85, 0.1))
        titik(x, t, (1.0, 0.85, 0.1))
    m, _ = ukur_jendela(peta, xs, zs)
    if m:
        for x in np.arange(m[0], m[1], RAY):
            titik(x, m[2], (0.1, 0.9, 0.9), 0)
            titik(x, m[3], (0.1, 0.9, 0.9), 0)
        for z in np.arange(m[2], m[3], RAY):
            titik(m[0], z, (0.1, 0.9, 0.9), 0)
            titik(m[1], z, (0.1, 0.9, 0.9), 0)
    return simpan_gambar(path, rgb, "ovl")


def render_tampak(folder, hanya=None):
    """Tampak cek mata (Cycles CPU uji). Eksposur -1 hanya di sini (AM-C02: model putih menyatu dengan latar);
    render QC AM-07 tetap eksposur 0."""
    sc = bpy.context.scene
    pakai_studio("review")
    sc.cycles.samples, sc.cycles.use_denoising = 24, True
    sc.view_settings.view_transform = "Khronos PBR Neutral"
    eks, sc.view_settings.exposure = sc.view_settings.exposure, -1.0
    out = {}
    px = data.model("tampak", "pusat_x_mm", 147.0) / 1000  # tengah panjang sepatu (AM1 0,147 m)
    jx, jz = (v / 1000 for v in data.model("tampak", "jendela_xz_mm", [216.3, 19.0]))  # pusat makro jendela
    pusat = Vector((px, 0.0, 0.06))
    cams = {  # nama: (kamera, w, h, target); posisi relatif tengah sepatu (nilai AM1 tetap identik)
        "samping_lateral": (kamera("CAM_samping", (px, 0.6, 0.068), (math.pi / 2, 0, math.pi), 0.32), 640, 340, None),
        "samping_medial": (kamera("CAM_samping_m", (px, -0.6, 0.068), (math.pi / 2, 0, 0), 0.32), 640, 340, None),
        "tiga_perempat": (kamera("CAM_34", (px - 0.317, 0.33, 0.23), (0, 0, 0), lensa=50), 640, 420, pusat),
        "tiga_perempat_belakang": (kamera("CAM_34b", (px + 0.313, -0.26, 0.24), (0, 0, 0), lensa=50), 640, 420, pusat),
        "atas": (kamera("CAM_atas", (px, 0.0, 0.6), (0, 0, 0), 0.32), 640, 300, None),
        "makro_swoosh": (kamera("CAM_m_sw", (0.205, 0.20, 0.10), (0, 0, 0), lensa=60), 640, 420,
                         Vector((0.205, 0.04, 0.078))),
        "makro_tali": (kamera("CAM_m_tali", (0.10, 0.16, 0.22), (0, 0, 0), lensa=60), 640, 420,
                       Vector((0.145, 0.0, 0.112))),
        "makro_jendela": (kamera("CAM_makro", (jx - 0.0113, 0.17, jz + 0.026), (0, 0, 0), lensa=60), 640, 420,
                          Vector((jx, 0.045, jz))),
    }
    for nama, (cam, w, h, t) in cams.items():
        if hanya and nama not in hanya:
            continue
        if t is not None:
            hadap(cam, t)
        out[nama] = render_gambar(cam, os.path.join(folder, f"{nama}.png"), w, h, 24, False)
    sc.view_settings.exposure = eks
    return out


def overlay_mudguard(art_m, path):
    """Proyeksi lateral objek mudguard (abu) + garis atas data (merah) + garis atas terukur model (cyan), x 0-296."""
    ob = cari_objek("mudguard")
    xs = np.arange(0.0, 296.0, 0.5) + 0.25
    zs = np.arange(0.0, 100.0, 0.5) + 0.25
    rgb = np.full((len(zs), len(xs), 3), 0.10, "f")
    if ob is not None:
        for i, z in enumerate(zs):
            for j, x in enumerate(xs):
                if ray_ob(ob, (x, 300.0, z), (0, -1, 0)) is not None:
                    rgb[i, j] = (0.55, 0.55, 0.57)

    def titik(x, z, c):
        i, j = int(z / 0.5), int(x / 0.5)
        if 0 <= i < rgb.shape[0] and 0 <= j < rgb.shape[1]:
            rgb[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2] = c
    mg = np.array(data.DATA["garis_mudguard_atas_lateral"], float)
    for x in np.arange(mg[0, 0], mg[-1, 0], 0.25):
        titik(x, float(np.interp(x, mg[:, 0], mg[:, 1])), (0.95, 0.15, 0.15))
    if art_m is not None:
        for x, _, z in zip(*art_m):
            if not np.isnan(z):
                titik(x, z, (0.1, 0.9, 0.9))
    return simpan_gambar(path, rgb, "ovl")
