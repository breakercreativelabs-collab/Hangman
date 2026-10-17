"""Kamera: arah azimut/elevasi, menghadap target, proyeksi titik ke frame, kamera tetap, sinar per piksel."""
import math

import bpy
import numpy as np
from mathutils import Vector

from .scene import koleksi


def arah(az, el):
    """Vektor satuan: az derajat dari -Y (arah kamera) ke +X, el derajat elevasi."""
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def hadap(ob, target):
    ob.rotation_euler = (target - ob.location).to_track_quat("-Z", "Y").to_euler()


def proyeksi(cam, pts):
    """Proyeksi titik dunia ke koordinat frame kamera (0..1, y ke atas) + kedalaman. Sama dengan world_to_camera_view."""
    sc = bpy.context.scene
    Mi = np.array(cam.matrix_world.normalized().inverted())
    loc = pts @ Mi[:3, :3].T + Mi[:3, 3]
    fr = cam.data.view_frame(scene=sc)
    fz = -fr[0].z
    z = -loc[:, 2]
    zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
    x, y = loc[:, 0] * fz / zs, loc[:, 1] * fz / zs
    u = (x - fr[2].x) / (fr[1].x - fr[2].x)
    v = (y - fr[1].y) / (fr[0].y - fr[1].y)
    return u, v, z


def kamera(nama, lok, rot, orto=None, lensa=50.0):
    """Kamera di collection CAMERAS (dipakai ulang bila sudah ada): ortografis (orto = lebar m) atau perspektif."""
    kc = koleksi("CAMERAS")
    cam = bpy.data.objects.get(nama)
    if cam is None:
        cam = bpy.data.objects.new(nama, bpy.data.cameras.new(nama))
        kc.objects.link(cam)
    cam.location, cam.rotation_euler = lok, rot
    if orto:
        cam.data.type, cam.data.ortho_scale = "ORTHO", orto
    else:
        cam.data.type, cam.data.lens = "PERSP", lensa
    cam.data.clip_start, cam.data.clip_end = 0.001, 10.0
    return cam


def sinar(cam, w, h, langkah):
    """Sinar kamera per piksel (perspektif dan ortografis). (x, y) piksel, baris 0 = bawah (konvensi PNG Blender)."""
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    fr = cam.data.view_frame(scene=sc)  # 0 kanan-atas, 1 kanan-bawah, 2 kiri-bawah, 3 kiri-atas
    Mw = cam.matrix_world.normalized()
    R = Mw.to_3x3()
    for y in range(0, h, langkah):
        for x in range(0, w, langkah):
            p = fr[2] + (fr[1] - fr[2]) * ((x + 0.5) / w) + (fr[3] - fr[2]) * ((y + 0.5) / h)
            if cam.data.type == "ORTHO":
                yield x, y, Mw @ Vector((p.x, p.y, 0.0)), (R @ Vector((0, 0, -1))).normalized()
            else:
                yield x, y, Mw.translation.copy(), (R @ p).normalized()


def uv_ke_lokal(cam, u, v, jarak):
    """Koordinat frame (u, v) -> titik lokal kamera di kedalaman `jarak` (view_frame sudah memuat shift).
    Mengembalikan (titik, lebar frame di kedalaman itu)."""
    fr = cam.data.view_frame(scene=bpy.context.scene)  # kanan-atas, kanan-bawah, kiri-bawah, kiri-atas
    s = jarak / -fr[0].z
    x0, x1, y0, y1 = fr[2].x * s, fr[0].x * s, fr[2].y * s, fr[0].y * s
    return Vector((x0 + u * (x1 - x0), y0 + v * (y1 - y0), -jarak)), (x1 - x0)
