"""QC angka product shot, bagian gambar (dari render PNG): QC-05 frame gelap/kosong, QC-10 warna, QC-12 logam."""
import colorsys
import os
import tempfile

import bpy
import numpy as np
from mathutils import Vector

from ...inti.io import baca_png, ubah_ukuran
from ...inti.kamera import proyeksi
from ...inti.qc import cek
from ...inti.scene import control, objek_produk, root as produk_root
from .ambang import AMBANG
from .bingkai import isi_frame, pakai_kamera
from .verbs import ukuran_produk


_PLAT = {}
VIS = ("camera", "diffuse", "glossy", "transmission", "volume_scatter", "shadow")


def plat_bersih(cam):
    """Clean plate: render kecil (25%, 4 sampel) scene TANPA produk, per kamera + preset cahaya + intensitas.
    Dipakai QC-05 untuk memisahkan produk dari gradasi backdrop."""
    sc, c = bpy.context.scene, control()
    kunci = (cam.name, c["preset_cahaya"], float(c["intensitas_cahaya"]), sc.render.resolution_x, sc.render.resolution_y)
    if kunci in _PLAT:
        return _PLAT[kunci]
    simpan = dict(path=sc.render.filepath, pct=sc.render.resolution_percentage, spp=sc.cycles.samples, cam=sc.camera)
    vis = {o.name: [getattr(o, "visible_" + k) for k in VIS] for o in objek_produk()}
    for o in objek_produk():
        for k in VIS:
            setattr(o, "visible_" + k, False)
    path = os.path.join(tempfile.gettempdir(), "hegemoni_plat", "_".join(str(x) for x in kunci) + ".png")
    sc.camera, sc.render.filepath = cam, path
    sc.render.resolution_percentage, sc.cycles.samples = 25, 4
    bpy.ops.render.render(write_still=True)
    for o in objek_produk():
        for k, v in zip(VIS, vis[o.name]):
            setattr(o, "visible_" + k, v)
    sc.render.filepath, sc.render.resolution_percentage, sc.cycles.samples, sc.camera = (
        simpan["path"], simpan["pct"], simpan["spp"], simpan["cam"])
    _PLAT[kunci] = baca_png(path) @ np.array([0.2126, 0.7152, 0.0722], "f")
    return _PLAT[kunci]


def qc_histogram(path, cam):
    """QC-05: frame tidak gelap/kosong. Luminans dari PNG; kontras produk = selisih terhadap clean plate
    di kotak proyeksi produk (gradasi backdrop tidak terhitung sebagai produk)."""
    rgb = baca_png(path)
    L = rgb @ np.array([0.2126, 0.7152, 0.0722], "f")
    pakai_kamera(cam)
    plat = plat_bersih(cam)
    ph, pw = plat.shape
    Lk = ubah_ukuran(L, ph, pw)
    _, (u0, u1, v0, v1) = isi_frame(cam)
    kotak = Lk[max(0, int(v0 * ph)):int(np.ceil(v1 * ph)), max(0, int(u0 * pw)):int(np.ceil(u1 * pw))]
    kplat = plat[max(0, int(v0 * ph)):int(np.ceil(v1 * ph)), max(0, int(u0 * pw)):int(np.ceil(u1 * pw))]
    kontras = float(np.abs(kotak - kplat).mean()) if kotak.size else 0.0
    m = dict(luma_rata=float(L.mean()), fraksi_hitam=float((L < 0.02).mean()), fraksi_putih=float((L > 0.98).mean()),
             kontras_produk=kontras,
             histogram_8=[round(float(x), 4) for x in np.histogram(L, 8, (0, 1))[0] / L.size])
    A = AMBANG
    alasan = []
    if not A["luma_min"] <= m["luma_rata"] <= A["luma_maks"]:
        alasan.append("luma rata di luar rentang")
    if m["fraksi_hitam"] > A["fraksi_hitam_maks"]:
        alasan.append("terlalu banyak hitam")
    if m["fraksi_putih"] > A["fraksi_putih_maks"]:
        alasan.append("terlalu banyak putih terpotong")
    if m["kontras_produk"] < A["kontras_produk_min"]:
        alasan.append("produk tidak terlihat/menyatu dengan latar (kosong)")
    m = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}
    return cek("QC-05", "frame_tidak_gelap_kosong", m, not alasan,
               f"luma {A['luma_min']}..{A['luma_maks']}, hitam/putih <= {A['fraksi_hitam_maks']}, "
               f"kontras >= {A['kontras_produk_min']}", "; ".join(alasan) or "ok")


def qc_warna(path, cam, hexa):
    """QC-10: warna varian terbaca (tidak pudar/overexposed). Sampel 5x5 piksel di titik label depan
    (frame hero), dibandingkan dengan hex target dalam HSV."""
    root = produk_root()
    if "titik_warna" not in root:
        return cek("QC-10", "warna_varian_terbaca", "n/a", True, "-", "produk tanpa titik_warna (impor)")
    pakai_kamera(cam)
    p = np.array(root.matrix_world @ Vector(root["titik_warna"]))[None]
    u, v, _ = proyeksi(cam, p)
    rgb = baca_png(path)
    h, w = rgb.shape[:2]
    x, y = int(u[0] * w), int(v[0] * h)
    pix = rgb[max(0, y - 2):y + 3, max(0, x - 2):x + 3].reshape(-1, 3).mean(0)
    hp, sp, vp = colorsys.rgb_to_hsv(*pix)
    ht, st, vt = colorsys.rgb_to_hsv(*[int(hexa.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    A = AMBANG
    if st < 0.2:
        d = abs(vp - vt)
        return cek("QC-10", "warna_varian_selisih_nilai", float(d), d <= A["nilai_selisih_maks"],
                   f"<= {A['nilai_selisih_maks']} (warna netral)", f"{hexa} vs piksel {pix.round(3).tolist()}")
    rasio = sp / st
    dh = abs((hp - ht + 0.5) % 1.0 - 0.5) * 360
    return cek("QC-10", "warna_varian_rasio_saturasi", float(rasio),
               rasio >= A["saturasi_rasio_min"] and dh <= A["hue_selisih_maks"],
               f">= {A['saturasi_rasio_min']} dan selisih hue <= {A['hue_selisih_maks']} deg",
               f"{hexa}: hue selisih {dh:.1f} deg, piksel {pix.round(3).tolist()}")


def adalah_logam(m):
    """Material logam produk (bukan label): Principled Metallic >= 0,5."""
    if not (m and m.node_tree) or m.name.startswith("LABEL"):
        return False
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    return bool(b) and b.inputs["Metallic"].default_value >= 0.5


def piksel_logam(path, cam, langkah=None):
    """Luminans piksel render yang sinar kameranya mengenai material logam produk (ray per piksel di kotak produk).
    Mengembalikan (luma, tinggi relatif titik kena 0..1, komponen z normal), array (bisa kosong).
    langkah=None: otomatis, ~360 baris sampel berapa pun resolusinya (render final tetap cepat)."""
    sc = bpy.context.scene
    pakai_kamera(cam)
    L = baca_png(path) @ np.array([0.2126, 0.7152, 0.0722], "f")
    h, w = L.shape
    langkah = langkah or max(1, round(max(h, w) / 360))
    _, (u0, u1, v0, v1) = isi_frame(cam)
    fr = cam.data.view_frame(scene=sc)  # 0 kanan-atas, 1 kanan-bawah, 2 kiri-bawah, 3 kiri-atas (ruang kamera)
    M, asal = cam.matrix_world.normalized(), cam.location
    dg = bpy.context.evaluated_depsgraph_get()
    produk = {o.name for o in objek_produk()}
    hasil, tinggi, nz = [], [], []
    H, _ = ukuran_produk()
    for y in range(max(0, int(v0 * h)), min(h, int(np.ceil(v1 * h))), langkah):
        for x in range(max(0, int(u0 * w)), min(w, int(np.ceil(u1 * w))), langkah):
            u, v = (x + 0.5) / w, (y + 0.5) / h
            p = fr[2] + (fr[1] - fr[2]) * u + (fr[3] - fr[2]) * v
            arah = (M.to_3x3() @ p).normalized()
            kena, loc, nor, idx, ob, _ = sc.ray_cast(dg, asal, arah)
            if not (kena and ob and ob.name in produk):
                continue
            slot = ob.material_slots[ob.data.polygons[idx].material_index] if ob.material_slots else None
            if slot and adalah_logam(slot.material):
                hasil.append(L[y, x])
                tinggi.append(loc.z / H)
                nz.append(nor.z)
    return np.array(hasil, "f"), np.array(tinggi, "f"), np.array(nz, "f")


def qc_logam(path, cam):
    """QC-12 (C-15): logam produk tidak hitam pekat. Piksel yang sinar kameranya mengenai material logam
    (Metallic >= 0,5, bukan LABEL) dan bukan sisi bawah (normal z > -0,3; dasar kaleng memang gelap):
    fraksi luma < 0,02. Logam tegak tanpa sumber pantulan di preset gelap = pita hitam pekat."""
    L, _, nz = piksel_logam(path, cam)
    L = L[nz > -0.3]
    if L.size < 30:
        return cek("QC-12", "logam_hitam_pekat", "n/a", True, "-", f"{L.size} piksel logam (< 30)")
    fr = float((L < 0.02).mean())
    a = AMBANG["logam_hitam_maks"]
    return cek("QC-12", "logam_fraksi_hitam", fr, fr <= a, f"<= {a}",
               f"{L.size} piksel logam, median luma {float(np.median(L)):.3f}")
