"""Kamera TVC: satu rig per shot (empty di target + kamera anak menghadap target), jarak dari bisection isi frame,
marker di frame awal shot di-bind ke kamera (potongan di ketukan). Rencana per shot: tvc.toml [kamera.<shot>]."""
import math

import bpy
import numpy as np

from ...inti.kamera import proyeksi
from ...inti.scene import koleksi, titik_produk
from . import konfig
from .kunci import kunci


def rig_kamera(nama, target, lensa):
    """Rig: empty RIG_<nama> di target, rotasi (elevasi, 0, azimut); kamera anak di (0, jarak, 0) menghadap -Y lokal
    (selalu memandang target). az 0 = sisi lateral (+Y), az + = ke arah toe (-X)."""
    kc = koleksi("CAMERAS")
    rig = bpy.data.objects.new("RIG_" + nama, None)
    kc.objects.link(rig)
    rig.location, rig.rotation_mode = target, "XYZ"
    cam = bpy.data.objects.new("CAM_" + nama, bpy.data.cameras.new("CAM_" + nama))
    kc.objects.link(cam)
    cam.parent = rig
    cam.rotation_euler = (math.radians(90), 0, math.radians(180))
    cam.data.lens, cam.data.sensor_width, cam.data.sensor_fit = lensa, 36.0, "AUTO"
    cam.data.clip_start, cam.data.clip_end = 0.005, 20.0
    return rig, cam


def pose_kamera(rig, cam, az, el, jarak):
    rig.rotation_euler = (math.radians(el), 0.0, math.radians(az))
    cam.location = (0.0, jarak, 0.0)
    bpy.context.view_layer.update()


def titik_subjek(langkah=7):
    """Vertex produk dunia (evaluated, setiap `langkah` vertex; cukup untuk bbox proyeksi)."""
    return titik_produk()[::langkah]


def bingkai_shot(rig, cam, f_sampel, az, el, isi, pusat_uv=(0.5, 0.5)):
    """Cari jarak (bisection) agar isi = max(rentang u, rentang v) produk di frame sampel = `isi`; shift kamera menaruh
    pusat bbox produk di `pusat_uv`. Dipakai di pose tengah gerak kamera."""
    sc = bpy.context.scene
    pts = []
    for f in f_sampel:
        sc.frame_set(f)
        pts.append(titik_subjek(11))
    pts = np.concatenate(pts)
    cam.data.shift_x = cam.data.shift_y = 0.0
    lo, hi = 0.03, 6.0
    for _ in range(36):
        d = (lo + hi) / 2
        pose_kamera(rig, cam, az, el, d)
        u, v, _ = proyeksi(cam, pts)
        if max(u.max() - u.min(), v.max() - v.min()) > isi:
            lo = d
        else:
            hi = d
    u, v, _ = proyeksi(cam, pts)
    w, h = sc.render.resolution_x, sc.render.resolution_y
    cam.data.shift_x = ((u.min() + u.max()) / 2 - pusat_uv[0]) * w / max(w, h)
    cam.data.shift_y = ((v.min() + v.max()) / 2 - pusat_uv[1]) * h / max(w, h)
    return d


def rencana_kamera(rasio):
    """Rencana per shot dari konfigurasi, nilai per rasio sudah dipilih."""
    out = {}
    for nama, r in konfig.K["kamera"].items():
        p = dict(target=konfig.target(r), lensa=r["lensa"], az=tuple(r["az"]), el=tuple(r["el"]))
        for k in ("jarak", "k", "isi", "bingkai", "k_tengah", "pusat_uv"):
            if k in r:
                p[k] = tuple(konfig.per_rasio(r[k], rasio)) if k != "isi" else konfig.per_rasio(r[k], rasio)
        out[nama] = p
    return out


def pasang_kamera(rasio):
    """Satu rig + kamera per shot, marker di frame awal shot di-bind ke kamera (potongan di ketukan)."""
    sc = bpy.context.scene
    sc.timeline_markers.clear()
    rk, cams = rencana_kamera(rasio), {}
    for nama, f0, f1 in konfig.rentang_shot():
        r = rk[nama]
        rig, cam = rig_kamera(nama, r["target"], r["lensa"])
        if "jarak" in r:
            d0, d1 = r["jarak"]
        else:
            d = bingkai_shot(rig, cam, r["bingkai"], sum(r["az"]) / 2, sum(r["el"]) / 2, r["isi"],
                             r.get("pusat_uv", (0.5, 0.5)))
            d0, d1 = d * r["k"][0], d * r["k"][1]
        for f, az, el, dd in ((f0, r["az"][0], r["el"][0], d0), (f1, r["az"][1], r["el"][1], d1)):
            kunci(rig, "rotation_euler", f, math.radians(el), "BEZIER", "AUTO", 0)
            kunci(rig, "rotation_euler", f, math.radians(az), "BEZIER", "AUTO", 2)
            kunci(cam, "location", f, dd, "BEZIER", "AUTO", 1)
        if "k_tengah" in r:
            kunci(cam, "location", r["k_tengah"][0], d * r["k_tengah"][1], "BEZIER", "AUTO", 1)
        m = sc.timeline_markers.new(nama, frame=f0)
        m.camera = cam
        cam["shot"], cam["rasio"] = nama, rasio
        cams[nama] = cam
    sc.camera = cams[konfig.K["shot"][0]["id"]]
    return cams
