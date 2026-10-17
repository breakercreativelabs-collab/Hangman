"""VERB 6 render_variants + pembingkaian kamera per rasio (isi frame target, produk dipusatkan)."""
import os

import bpy
from mathutils import Vector

from ...inti.kamera import arah, hadap, proyeksi
from ...inti.render import KUALITAS
from ...inti.scene import control, koleksi, titik_produk
from .verbs import RASIO


def isi_frame(cam, pts=None):
    u, v, _ = proyeksi(cam, titik_produk() if pts is None else pts)
    return max(u.max() - u.min(), v.max() - v.min()), (u.min(), u.max(), v.min(), v.max())


def pakai_kamera(cam):
    sc = bpy.context.scene
    q = KUALITAS[sc.get("kualitas", "uji")]
    w, h = RASIO[cam["rasio"]]
    sc.render.resolution_x, sc.render.resolution_y = round(w * q["skala"]), round(h * q["skala"])
    sc.camera = cam
    bpy.context.view_layer.update()


def bingkai(rasio, isi_target=0.70, elevasi=8.0, lensa=70.0):
    """Buat/atur kamera rasio tertentu: jarak dicari (bisection) agar produk mengisi `isi_target` frame,
    lalu shift kamera memusatkan produk tepat di tengah."""
    nama = "CAM_" + rasio.replace(":", "x")
    cam = bpy.data.objects.get(nama)
    if cam is None:
        cam = bpy.data.objects.new(nama, bpy.data.cameras.new(nama))
        koleksi("CAMERAS").objects.link(cam)
    cam["rasio"] = rasio
    cd = cam.data
    cd.lens, cd.sensor_width, cd.sensor_fit = lensa, 36.0, "AUTO"
    cd.shift_x = cd.shift_y = 0.0
    pakai_kamera(cam)
    sc = bpy.context.scene
    sc.frame_set(sc.frame_start)
    pts = titik_produk()
    h = float(pts[:, 2].max())
    pusat = Vector((0, 0, h / 2))
    a = arah(0, elevasi)
    lo, hi = 0.3 * h, 60 * h
    for _ in range(40):
        d = (lo + hi) / 2
        cam.location = pusat + a * d
        hadap(cam, pusat)
        bpy.context.view_layer.update()
        if isi_frame(cam, pts)[0] > isi_target:
            lo = d
        else:
            hi = d
    cd.clip_start, cd.clip_end = d * 0.05, d * 100
    _, (u0, u1, v0, v1) = isi_frame(cam, pts)
    w, hh = sc.render.resolution_x, sc.render.resolution_y
    cd.shift_x = ((u0 + u1) / 2 - 0.5) * w / max(w, hh)
    cd.shift_y = ((v0 + v1) / 2 - 0.5) * hh / max(w, hh)
    bpy.context.view_layer.update()
    control()["isi_target"] = isi_target
    return cam


def kamera_rasio(rasio, isi_target):
    """Kamera dibingkai sekali per rasio; dipakai ulang antar varian warna/cahaya (geometri tidak berubah)."""
    cam = bpy.data.objects.get("CAM_" + rasio.replace(":", "x"))
    if cam is None or abs(cam.get("isi_dibingkai", -1) - isi_target) > 1e-9:
        cam = bingkai(rasio, isi_target)
        cam["isi_dibingkai"] = isi_target
    return cam


def render_variants(folder, awalan, rasio=("16:9", "9:16", "1:1"), frame=None, isi_target=0.70):
    """Render satu still per rasio (kamera CAM_16x9 / CAM_9x16 / CAM_1x1). Mengembalikan daftar render."""
    os.makedirs(folder, exist_ok=True)
    sc, hasil = bpy.context.scene, []
    for r in rasio:
        cam = kamera_rasio(r, isi_target)
        pakai_kamera(cam)
        f = sc.frame_start if frame is None else frame
        sc.frame_set(f)
        path = os.path.join(folder, f"{awalan}_{r.replace(':', 'x')}_f{f:03d}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        hasil.append(dict(file=path, rasio=r, kamera=cam.name, frame=f, warna=control()["warna_hex"],
                          preset=control()["preset_cahaya"]))
    return hasil
