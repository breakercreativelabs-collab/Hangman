"""Uji negatif QC TV: perusak scene generik (dipilih + diberi parameter oleh tvc.toml [[negatif]]) dan negatif
berbasis berkas (frame hitam, flash tak tercatat, video salah, tinta putih). Cek `wajib` HARUS gagal."""
import math
import os

import bpy
import numpy as np

from ...inti.kamera import uv_ke_lokal
from ...inti.qc import tertangkap
from ...inti.scene import fcurves
from . import konfig
from .kunci import kunci
from .produksi import bangun_tvc, encode_mp4
from .qc_gambar import qc_frame, qc_kontras, qc_video, render_kontras, res_uji
from .qc_scene import qc_scene_tv
from .teks import bahan_tinta


# ---------------- perusak scene (n = baris [[negatif]] tvc.toml) ----------------
def geser_marker(n):
    """Marker shot digeser `nilai` frame (durasi shot salah)."""
    m = next(m for m in bpy.context.scene.timeline_markers if m.name == n["shot"])
    m.frame += n["nilai"]


def dolly(n):
    """Jarak kamera shot dikali `nilai` (terlalu dekat: produk terpotong)."""
    cam = bpy.data.objects["CAM_" + n["shot"]]
    for fc in fcurves(cam):
        if fc.data_path == "location":
            for k in fc.keyframe_points:
                k.co.y *= n["nilai"]
                k.handle_left.y *= n["nilai"]
                k.handle_right.y *= n["nilai"]


def balik(n):
    """Kamera shot menghadap ke luar rig (membelakangi target)."""
    bpy.data.objects["CAM_" + n["shot"]].rotation_euler.z += math.pi


def getar(n):
    """Kamera bergetar: key tiap 2 frame di `rentang`, +-`nilai` m acak (`seed`) di lokal x (BEZIER, bukan linear)."""
    cam = bpy.data.objects["CAM_" + n["shot"]]
    rng = np.random.default_rng(n["seed"])
    for f in range(n["rentang"][0], n["rentang"][1], 2):
        kunci(cam, "location", f, float(rng.uniform(-n["nilai"], n["nilai"])), "BEZIER", "AUTO", 0)


def goyang(n):
    """Kamera goyang rotasi: key tiap 2 frame di `rentang`, +-`nilai` deg acak (`seed`) di rotasi lokal z (BEZIER)."""
    cam = bpy.data.objects["CAM_" + n["shot"]]
    rng = np.random.default_rng(n["seed"])
    for f in range(n["rentang"][0], n["rentang"][1], 2):
        kunci(cam, "rotation_euler", f, math.radians(180 + rng.uniform(-n["nilai"], n["nilai"])), "BEZIER", "AUTO", 2)


def lompat(n):
    """Lonjakan di tengah shot (potongan palsu/glitch): azimut rig melompat `nilai` deg di `frame`."""
    rig = bpy.data.objects["RIG_" + n["shot"]]
    sc = bpy.context.scene
    f = n["frame"]
    sc.frame_set(f - 1)
    az = rig.rotation_euler.z
    kunci(rig, "rotation_euler", f - 1, az, "CONSTANT", "AUTO", 2)
    sc.frame_set(f)
    kunci(rig, "rotation_euler", f, rig.rotation_euler.z + math.radians(n["nilai"]), "BEZIER", "AUTO", 2)


def rakit_meleset(n):
    """Bagian exploded tidak kembali: kunci z terakhir empty bagian digeser `nilai` m."""
    for fc in fcurves(bpy.data.objects["XP_" + n["bagian"]]):
        if fc.data_path == "location" and fc.array_index == 2:
            fc.keyframe_points[-1].co.y += n["nilai"]


def tanpa_rakit(n):
    """Semua bagian exploded berhenti di posisi terurai (kunci terakhir = kunci sebelumnya)."""
    for b in konfig.K["exploded"]["bagian"]:
        for fc in fcurves(bpy.data.objects["XP_" + b["nama"]]):
            if fc.data_path == "location":
                kp = fc.keyframe_points
                kp[-1].co.y = kp[-2].co.y  # kunci terakhir = posisi terurai
                kp[-1].handle_left.y = kp[-1].handle_right.y = kp[-2].co.y


def teks_tepi(n):
    """Teks digeser `nilai` x lebar frame ke kanan (keluar title-safe)."""
    ob = bpy.data.objects[n["teks"]]
    _, lebar = uv_ke_lokal(bpy.data.objects["CAM_" + konfig.K["teks"]["shot"]], 0.5, 0.5, konfig.K["teks"]["jarak"])
    ob.location.x += n["nilai"] * lebar


def linear(n):
    """Semua key rig + kamera shot diubah ke LINEAR."""
    for idb in (bpy.data.objects["RIG_" + n["shot"]], bpy.data.objects["CAM_" + n["shot"]]):
        for fc in fcurves(idb):
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"


def ganti_bahan(n):
    """Material utama objek produk diganti material tinta teks (bukan material peran)."""
    bpy.data.objects[n["objek"]].data.materials[0] = bpy.data.materials["tinta"]


PERUSAK = dict(geser_marker=geser_marker, dolly=dolly, balik=balik, getar=getar, goyang=goyang, lompat=lompat,
               rakit_meleset=rakit_meleset, tanpa_rakit=tanpa_rakit, teks_tepi=teks_tepi, linear=linear,
               bahan_produk=ganti_bahan)


def daftar(pilih_teks=""):
    """[[negatif]] proyek (difilter nama memuat `pilih_teks`)."""
    return [n for n in konfig.K.get("negatif", []) if not pilih_teks or pilih_teks in n["nama"]]


def negatif_scene(pilih, model=None):
    out = []
    for n in pilih:
        bangun_tvc("9x16", "uji", model)
        PERUSAK[n["perusak"]](n)
        bpy.context.view_layer.update()
        hasil, _ = qc_scene_tv("9x16")
        ok, gagal = tertangkap(hasil, n["wajib"])
        out.append(dict(nama=n["nama"], wajib_gagal=n["wajib"], gagal=gagal, tertangkap=ok,
                        nilai={f"{c['id']} {c['nama']}": c["nilai"] for c in hasil if not c["lulus"]}))
        print(("TERTANGKAP " if ok else "LOLOS(!) ") + f"negatif '{n['nama']}': gagal {gagal}")
    return out


def negatif_gambar(folder, stat, flash, frames, model=None):
    """Negatif berbasis berkas: frame hitam, flash tak tercatat, video salah durasi/fps, teks tinta putih (kontras)."""
    out = []

    def catat(nama, hasil, wajib):
        ok, gagal = tertangkap(hasil, wajib)
        out.append(dict(nama=nama, wajib_gagal=wajib, gagal=gagal, tertangkap=ok,
                        nilai={f"{c['id']} {c['nama']}": c["nilai"] for c in hasil}))
        print(("TERTANGKAP " if ok else "LOLOS(!) ") + f"negatif '{nama}': gagal {gagal}")

    s = stat.copy()
    s[199] = (0.0, 0.0)
    catat("frame 200 hitam", [qc_frame(s, flash, "9x16")], ["TV-03"])
    s = stat.copy()
    s[149, 0] = min(1.0, s[149, 0] + 0.45)
    catat("flash tak tercatat di frame 150", [qc_frame(s, flash, "9x16")], ["TV-03"])
    catat("flash tercatat dihapus dari daftar", [qc_frame(stat, {}, "9x16")], ["TV-03"])
    # video salah: 100 frame pertama, 24 fps
    salah = os.path.join(folder, "negatif_video_24fps_100f.mp4")
    encode_mp4(os.path.dirname(frames[0]), salah, *res_uji("9x16"), fps=24, f0=1, f1=100)
    catat("video 100 frame @ 24 fps", [qc_video(salah, res_uji("9x16"), "9x16")], ["TV-07"])
    # tinta putih: kontras rendah di latar gradasi
    bangun_tvc("9x16", "uji", model)
    bahan_tinta(hexa="#FFFFFF")
    pa, pb = render_kontras(os.path.join(folder, "negatif"), "9x16")
    catat("teks tinta putih", [qc_kontras(pa, pb, "9x16")], ["TV-06"])
    return out
