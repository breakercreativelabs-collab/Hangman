"""Verbs product shot (Blender 5.2 LTS). Python menghitung, Claude memutuskan.

Verbs: import_product · normalize · studio_lighting (cahaya.py) · turntable · material_variant ·
render_variants (bingkai.py). Standar .blend dan hierarki produk: agen3d.inti.scene.
Konvensi: satuan meter, lantai z = 0, sisi depan produk menghadap -Y, kamera di arah -Y.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ...inti import warna as W
from ...inti.scene import control, fcurves, koleksi, root, titik_produk
from . import produk_uji, spesifikasi
from .bahan import bahan_produk

RASIO = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}  # resolusi final (laptop)
WARNA = {"merah": "#C8102E", "biru": "#1F4E9C", "hijau": "#2E7D32", "hitam": "#1A1A1A",
         "putih": "#F2F2F2", "kuning": "#F2C230", "ungu": "#5E2A84", "oranye": "#E8641B"}
EASING = {  # nama -> (interpolasi, easing) Blender. "linear" hanya untuk uji negatif QC.
    "ease_in_out": ("SINE", "EASE_IN_OUT"),
    "cubic": ("CUBIC", "EASE_IN_OUT"),
    "expo": ("EXPO", "EASE_IN_OUT"),
    "bezier": ("BEZIER", "AUTO"),
    "linear": ("LINEAR", "AUTO"),
}


def warna_ke_linear(h):
    """Nama palet (WARNA) atau '#RRGGBB' -> linear."""
    return W.hex_ke_linear(WARNA.get(h, h))


# ---------------- VERB 1: import_product ----------------
def import_product(sumber):
    """Masukkan produk ke collection PRODUCT di bawah PRODUCT_ROOT.
    sumber: "uji:botol" / "uji:kaleng" (produk uji prosedural) atau path .glb/.gltf/.obj/.fbx/.stl/.blend."""
    pk, r = koleksi("PRODUCT"), root()
    sebelum = set(bpy.data.objects)
    if sumber.startswith("uji:"):
        nama = sumber[4:]
        produk_uji.bangun_produk(nama, pk, bahan_produk(nama))
        s = spesifikasi.SPEC[nama]
        r["spec_tinggi_mm"] = spesifikasi.tinggi_total_mm(nama)
        for k, v in spesifikasi.spec_qc(nama).items():  # bulat: diameter; kotak/pipih: lebar + tebal
            r[k] = v
        r["spec_sumber"] = s["sumber"]
        r["titik_warna"] = spesifikasi.titik_warna(nama)
        r["logo_u"], r["logo_z"] = spesifikasi.logo(nama)
    else:
        ext = os.path.splitext(sumber)[1].lower()
        if not os.path.isfile(sumber):
            raise FileNotFoundError(sumber)
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=sumber)
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=sumber)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=sumber)
        elif ext == ".stl":
            bpy.ops.wm.stl_import(filepath=sumber)
        elif ext == ".blend":
            with bpy.data.libraries.load(sumber) as (src, dst):
                dst.objects = list(src.objects)
            for o in dst.objects:
                if o is not None and o.type == "MESH":
                    pk.objects.link(o)
        else:
            raise ValueError(f"format tidak didukung: {ext}")
        nama = os.path.splitext(os.path.basename(sumber))[0]
    baru = [o for o in bpy.data.objects if o not in sebelum and o.type in ("MESH", "EMPTY")]
    for o in [o for o in bpy.data.objects if o not in sebelum and o not in baru]:
        bpy.data.objects.remove(o)  # kamera/lampu bawaan file impor dibuang: standar kita yang dipakai
    for o in baru:
        for k in list(o.users_collection):
            if k != pk:
                k.objects.unlink(o)
        if pk not in o.users_collection:
            pk.objects.link(o)
        if o.parent is None:
            mw = o.matrix_world.copy()
            o.parent = r
            o.matrix_world = mw
    r["sumber"] = sumber
    control()["produk"] = nama
    bpy.context.view_layer.update()
    return r


# ---------------- VERB 2: normalize ----------------
SATUAN = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}
ROT_DEPAN = {"-Y": 0.0, "+X": -90.0, "+Y": 180.0, "-X": 90.0}
ROT_ATAS = {"+Z": None, "+Y": ("X", 90.0), "-Y": ("X", -90.0)}


def _terapkan(T):
    """Kalikan T (ruang dunia) ke semua anak langsung PRODUCT_ROOT; skala dibakar ke mesh."""
    r = root()
    for c in r.children:
        c.matrix_world = T @ c.matrix_world
    bpy.context.view_layer.update()
    for c in r.children_recursive:
        if c.type == "MESH" and not c.children and c.data.users == 1:
            s = c.matrix_basis.to_scale()
            if (s - Vector((1, 1, 1))).length > 1e-6:
                c.data.transform(Matrix.Diagonal((*s, 1.0)))
                c.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def normalize(satuan="m", tinggi_m=None, depan="-Y", atas="+Z"):
    """Skala nyata, origin di tengah dasar, berdiri di lantai (z=0), depan menghadap -Y.
    satuan: satuan file sumber (m/cm/mm/in). tinggi_m: paksa tinggi (jika satuan sumber tidak jelas).
    depan/atas: sumbu depan & atas di file sumber."""
    r = root()
    tt = r.parent
    tt.matrix_world = Matrix.Identity(4)
    r.matrix_parent_inverse = Matrix.Identity(4)
    r.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    R = Matrix.Identity(4)
    if ROT_ATAS[atas]:
        R = Matrix.Rotation(math.radians(ROT_ATAS[atas][1]), 4, ROT_ATAS[atas][0])
    R = Matrix.Rotation(math.radians(ROT_DEPAN[depan]), 4, "Z") @ R
    _terapkan(R @ Matrix.Scale(SATUAN[satuan], 4))
    if tinggi_m:
        p = titik_produk()
        _terapkan(Matrix.Scale(tinggi_m / (p[:, 2].max() - p[:, 2].min()), 4))
    p = titik_produk()
    lo, hi = p.min(0), p.max(0)
    _terapkan(Matrix.Translation(Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))))
    p = titik_produk()
    dim = (p.max(0) - p.min(0)) * 1000
    r["dimensi_mm"] = dim_mm = [round(float(d), 2) for d in dim]
    return {"dimensi_mm": dim_mm, "z_min_mm": round(float(p[:, 2].min()) * 1000, 3)}


def ukuran_produk():
    p = titik_produk()
    return float(p[:, 2].max()), float(np.hypot(p[:, 0], p[:, 1]).max())  # tinggi, radius XY


# ---------------- VERB 4: turntable ----------------
def turntable(durasi=6.0, easing="ease_in_out", fps=25, putaran=1):
    """Putar produk 360 derajat x putaran di sumbu Z selama `durasi` detik, berakhir menghadap depan lagi."""
    sc, tt = bpy.context.scene, root().parent
    sc.render.fps, sc.render.fps_base = fps, 1.0
    sc.frame_start, sc.frame_end = 1, 1 + round(durasi * fps)
    tt.animation_data_clear()
    tt.rotation_euler = (0, 0, 0)
    tt.keyframe_insert("rotation_euler", index=2, frame=sc.frame_start)
    tt.rotation_euler.z = 2 * math.pi * putaran
    tt.keyframe_insert("rotation_euler", index=2, frame=sc.frame_end)
    interp, ease = EASING[easing]
    for fc in fcurves(tt):
        for k in fc.keyframe_points:
            k.interpolation, k.easing = interp, ease
    c = control()
    c["durasi_detik"], c["easing"], c["fps"] = float(durasi), easing, fps
    sc.frame_set(sc.frame_start)
    return (sc.frame_start, sc.frame_end)


# ---------------- VERB 5: material_variant ----------------
def material_variant(warna):
    """Ganti warna varian label (nama di WARNA atau hex '#RRGGBB'). Lewat CONTROL['warna_varian'] -> driver."""
    hexa = WARNA.get(warna, warna)
    lin = warna_ke_linear(hexa)
    c = control()
    c["warna_varian"], c["warna_hex"] = lin, hexa
    c.update_tag()  # ubah custom property lewat Python tidak otomatis memicu evaluasi driver
    jumlah = 0
    for m in bpy.data.materials:  # set langsung juga, agar benar walau driver belum dievaluasi
        n = m.node_tree.nodes.get("WARNA_VARIAN") if m.node_tree else None
        if n:
            n.outputs[0].default_value = (*lin, 1)
            jumlah += 1
    c["material_varian"] = jumlah
    if not jumlah:  # jangan gagal senyap: model klien perlu node RGB bernama WARNA_VARIAN di material label
        print("PERINGATAN material_variant: tidak ada node 'WARNA_VARIAN'; warna produk TIDAK berubah")
    bpy.context.view_layer.update()
    return hexa
