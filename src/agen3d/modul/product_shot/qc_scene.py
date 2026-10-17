"""QC angka product shot, bagian scene (tanpa render): QC-01/02/03/04/06/07/08/09/11.
Setiap cek = satu baris di ATURAN_QC.md (ID sama). Semua cek: dict id, nama, nilai, ambang, lulus, konteks.
"""
import math

import bpy
import numpy as np
from mathutils import Vector, interpolate

from ...inti.kamera import proyeksi
from ...inti.qc import cek
from ...inti.scene import KOLEKSI, control, fcurves, objek_produk, root as produk_root, titik_produk
from .ambang import AMBANG
from .bingkai import pakai_kamera
from .verbs import ukuran_produk


def frame_sampel(n=9):
    sc = bpy.context.scene
    return sorted({round(f) for f in np.linspace(sc.frame_start, sc.frame_end, n)})


# ---------------- geometri ----------------
def qc_kontak_lantai():
    """QC-01: produk tidak melayang/tenggelam, dicek di sepanjang turntable."""
    sc, terburuk, f_buruk = bpy.context.scene, 0.0, None
    for f in frame_sampel():
        sc.frame_set(f)
        z = float(titik_produk()[:, 2].min()) * 1000
        if abs(z) >= abs(terburuk):
            terburuk, f_buruk = z, f
    sc.frame_set(sc.frame_start)
    a = AMBANG["kontak_lantai_mm"]
    status = "melayang" if terburuk > a else "tenggelam" if terburuk < -a else "menapak"
    return cek("QC-01", "kontak_lantai_z_min_mm", terburuk, abs(terburuk) <= a, f"|z| <= {a} mm",
               f"{status}, terburuk di frame {f_buruk}")


def qc_kamera(cam):
    """QC-02 isi frame, QC-03 tidak terpotong (semua frame sampel), QC-08 kamera di luar produk."""
    sc = bpy.context.scene
    pakai_kamera(cam)
    hasil, isi0, margin, f_m = [], None, 1.0, None
    for f in frame_sampel():
        sc.frame_set(f)
        pts = titik_produk()
        u, v, z = proyeksi(cam, pts)
        if isi0 is None:
            isi0 = max(u.max() - u.min(), v.max() - v.min())
        m = float(min(u.min(), v.min(), 1 - u.max(), 1 - v.max())) if (z > 0).all() else -1.0
        if m < margin:
            margin, f_m = m, f
    sc.frame_set(sc.frame_start)
    A = AMBANG
    hasil.append(cek("QC-02", "isi_frame", float(isi0), A["isi_min"] <= isi0 <= A["isi_maks"],
                     f"{A['isi_min']}..{A['isi_maks']}", cam.name))
    hasil.append(cek("QC-03", "margin_tepi_min", margin, margin >= A["margin_min"], f">= {A['margin_min']}",
                     f"{cam.name}, terburuk frame {f_m}" + (" (TERPOTONG)" if margin < 0 else "")))
    pts = titik_produk()
    lo, hi = pts.min(0), pts.max(0)
    c = np.array(cam.location)
    di_dalam = bool(((c >= lo) & (c <= hi)).all())
    jarak = float(np.linalg.norm(pts - c, axis=1).min())
    batas = cam.data.clip_start * A["jarak_kamera_min_x_clip"]
    hasil.append(cek("QC-08", "jarak_kamera_ke_produk_m", jarak, (not di_dalam) and jarak > batas,
                     f"di luar bbox dan > {A['jarak_kamera_min_x_clip']} x clip_start", cam.name))
    return hasil


def _uv_di(ob, idx, lokasi):
    """Koordinat UV di titik `lokasi` (ruang lokal objek) pada face `idx` (interpolasi barisentrik)."""
    me = ob.data
    if not me.uv_layers:
        return None
    poly = me.polygons[idx]
    w = interpolate.poly_3d_calc([me.vertices[v].co for v in poly.vertices], lokasi)
    uv = me.uv_layers.active.data
    return Vector(sum((uv[li].uv * wi for li, wi in zip(poly.loop_indices, w)), Vector((0, 0))))


def qc_depan(cam):
    """QC-04: logo (sisi depan) menghadap kamera di frame hero. Sinar dari kamera ke sumbu produk setinggi logo
    harus mengenai material LABEL, dan u di titik kena harus = u logo (selisih dalam derajat keliling).
    Tanpa data logo (impor tanpa logo_u/logo_z): hanya arah depan yang dideklarasikan (lebih lemah)."""
    sc = bpy.context.scene
    sc.frame_set(sc.frame_start)
    pakai_kamera(cam)
    root = produk_root()
    h, _ = ukuran_produk()
    pusat = root.matrix_world @ Vector((0, 0, root.get("logo_z", h / 2)))
    depan = (root.matrix_world.to_3x3() @ Vector((0, -1, 0)))
    ke_kamera = cam.location - pusat
    depan.z = ke_kamera.z = 0
    sudut_dekl = math.degrees(depan.angle(ke_kamera)) if depan.length and ke_kamera.length else 180.0
    dg = bpy.context.evaluated_depsgraph_get()
    kena, _, _, _, ob, _ = sc.ray_cast(dg, cam.location, (pusat - cam.location).normalized())
    produk = {o.name for o in objek_produk()}
    punya_label = any(m and m.name.startswith("LABEL") for o in objek_produk() for m in o.data.materials)
    nama_mat, sudut_logo = "", None
    if kena and ob and ob.name in produk:
        mi = ob.matrix_world.inverted()
        ok, lok, _, idx = ob.ray_cast(mi @ cam.location, (mi.to_3x3() @ (pusat - cam.location)).normalized())
        if ok:
            mats = ob.data.materials
            nama_mat = mats[ob.data.polygons[idx].material_index].name if len(mats) else ""
            uv = _uv_di(ob, idx, lok)
            if uv is not None and "logo_u" in root:
                sudut_logo = abs((uv.x - root["logo_u"] + 0.5) % 1.0 - 0.5) * 360
    terlihat = bool(kena and ob and ob.name in produk and (nama_mat.startswith("LABEL") or not punya_label))
    a = AMBANG["sudut_depan_maks"]
    lulus = sudut_dekl <= a and terlihat and (sudut_logo is None or sudut_logo <= a)
    nilai = sudut_logo if sudut_logo is not None else sudut_dekl
    return [cek("QC-04", "sudut_logo_ke_kamera_deg" if sudut_logo is not None else "sudut_depan_deklarasi_deg",
                float(nilai), lulus, f"<= {a} deg + sinar kena LABEL",
                f"{cam.name}; deklarasi {sudut_dekl:.1f} deg; sinar kena: {ob.name if kena and ob else 'tidak ada'} / "
                f"{nama_mat or '-'}")]


def qc_keyframe():
    """QC-06: turntable tidak linear: interpolasi bukan LINEAR/CONSTANT dan ada ease di awal & akhir."""
    tt = produk_root().parent
    fcs = fcurves(tt)
    if not fcs:
        return [cek("QC-06", "keyframe_tidak_linear", "tanpa animasi", False, "ada turntable", "TURNTABLE")]
    sc = bpy.context.scene
    fc = next((f for f in fcs if f.data_path == "rotation_euler" and f.array_index == 2), fcs[0])
    interp = sorted({k.interpolation for k in fc.keyframe_points})
    f0, f1 = sc.frame_start, sc.frame_end
    t = np.linspace(f0, f1, 401)
    a = np.array([fc.evaluate(x) for x in t])
    v = np.abs(np.diff(a))
    rata = v.mean() if v.mean() > 0 else 1e-9
    n = max(1, len(v) // 20)
    rasio = float(max(v[:n].mean(), v[-n:].mean()) / rata)
    batas = AMBANG["kecepatan_ujung_maks"]
    lulus = not ({"LINEAR", "CONSTANT"} & set(interp)) and rasio <= batas
    return [cek("QC-06", "rasio_kecepatan_ujung", rasio, lulus, f"<= {batas}, interpolasi bukan LINEAR",
                f"interpolasi {interp}, {f1 - f0 + 1} frame")]


def qc_dimensi():
    """QC-07: ukuran nyata. Produk uji dibandingkan dengan spec datasheet; impor: hanya cek rentang wajar."""
    root = produk_root()
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    p = titik_produk()
    tinggi = float(p[:, 2].max() - p[:, 2].min()) * 1000
    diam = float(2 * np.hypot(p[:, 0], p[:, 1]).max()) * 1000
    tol = AMBANG["dimensi_mm"]
    if "spec_lebar_mm" in root:  # kotak/pipih: lebar (X, sisi depan) dan tebal (Y) dicek terpisah
        dt = tinggi - root["spec_tinggi_mm"]
        dl = float(p[:, 0].max() - p[:, 0].min()) * 1000 - root["spec_lebar_mm"]
        dk = float(p[:, 1].max() - p[:, 1].min()) * 1000 - root["spec_tebal_mm"]
        return [cek("QC-07", "selisih_tinggi_mm", dt, abs(dt) <= tol, f"|d| <= {tol} mm", f"tinggi {tinggi:.2f} mm"),
                cek("QC-07", "selisih_lebar_mm", dl, abs(dl) <= tol, f"|d| <= {tol} mm", "lebar X (sisi depan)"),
                cek("QC-07", "selisih_tebal_mm", dk, abs(dk) <= tol, f"|d| <= {tol} mm", "tebal Y")]
    if "spec_tinggi_mm" in root:
        dt = tinggi - root["spec_tinggi_mm"]
        # diameter: komponen terlebar boleh label/tutup sedikit di atas diameter badan
        dd = diam - root["spec_diameter_mm"]
        return [cek("QC-07", "selisih_tinggi_mm", dt, abs(dt) <= tol, f"|d| <= {tol} mm", f"tinggi {tinggi:.2f} mm"),
                cek("QC-07", "selisih_diameter_mm", dd, abs(dd) <= tol, f"|d| <= {tol} mm", f"diameter {diam:.2f} mm")]
    return [cek("QC-07", "tinggi_mm", tinggi, 10 <= tinggi <= 3000, "10..3000 mm (tanpa spec)", "produk impor")]


def qc_standar():
    """QC-09: standar .blend: 4 collection berisi + CONTROL dengan property wajib."""
    kurang = [k for k in KOLEKSI if not bpy.data.collections.get(k) or not bpy.data.collections[k].all_objects]
    c = control()
    wajib = ("standar", "produk", "warna_varian", "warna_hex", "intensitas_cahaya", "preset_cahaya",
             "durasi_detik", "easing", "fps", "isi_target")
    kurang += [f"CONTROL[{k}]" for k in wajib if c is None or k not in c]
    return [cek("QC-09", "standar_blend_kurang", len(kurang), not kurang, "= 0", ", ".join(kurang) or "lengkap")]


def adalah_bening(m):
    """Material kaca/plastik bening: Principled dengan transmisi dominan dan IOR >= ambang (bukan cairan)."""
    if not (m and m.node_tree):
        return False
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    return bool(b) and b.inputs["Transmission Weight"].default_value > 0.5 \
        and b.inputs["IOR"].default_value >= AMBANG["kaca_ior_min"]


def qc_kaca():
    """QC-11 (C-11): objek kaca/plastik bening harus berongga. Kaca pejal membiaskan latar & sisi belakang label
    menjadi pita gelap. Sinar mendatar menembus objek setinggi 40% tingginya: rasio tebal dinding pertama terhadap
    lebar total (pejal ~1,0) dan jumlah permukaan yang ditembus (berongga >= 4)."""
    dg, hasil = bpy.context.evaluated_depsgraph_get(), []
    for ob in objek_produk():
        if not any(adalah_bening(s.material) for s in ob.material_slots):
            continue
        bb = [Vector(c) for c in ob.bound_box]
        lo, hi = Vector([min(c[i] for c in bb) for i in range(3)]), Vector([max(c[i] for c in bb) for i in range(3)])
        z, cy = lo.z + 0.4 * (hi.z - lo.z), (lo.y + hi.y) / 2
        asal, arah, kena = Vector((lo.x - 0.01, cy, z)), Vector((1, 0, 0)), []
        for _ in range(16):
            ok, loc, *_ = ob.ray_cast(asal, arah, depsgraph=dg)  # ruang lokal objek
            if not ok:
                break
            kena.append(loc.x)
            asal = loc + arah * 1e-5
        if len(kena) < 2:
            continue
        rasio = (kena[1] - kena[0]) / max(kena[-1] - kena[0], 1e-9)
        a = AMBANG["dinding_rasio_maks"]
        hasil.append(cek("QC-11", "kaca_berongga_rasio_dinding", rasio, len(kena) >= 4 and rasio <= a,
                         f"<= {a} dan >= 4 permukaan",
                         f"{ob.name}: {len(kena)} permukaan, dinding {(kena[1] - kena[0]) * 1000:.1f} mm"))
    return hasil


def qc_scene(kamera):
    """Semua cek non-gambar untuk scene saat ini."""
    hasil = qc_standar() + qc_dimensi() + [qc_kontak_lantai()] + qc_keyframe() + qc_kaca()
    for cam in kamera:
        hasil += qc_kamera(cam) + qc_depan(cam)
    return hasil
