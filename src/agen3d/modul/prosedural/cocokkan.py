"""Spike: tiru referensi pohon (inverse procedural modeling) lewat skor siluet.

Pohon referensi dibuat dengan parameter RAHASIA + seed berbeda. Optimizer hanya
melihat siluet (alpha render Workbench) dan mencari parameter dengan IoU tertinggi.
Claude tidak melihat gambar di tiap putaran; angka IoU yang menuntun.
  blender -b --factory-startup -P blender_cli.py -- prosedural cocokkan [--out <folder>]   (bawaan artefak/prosedural)
"""
import json
import math
import os
import time

import bpy
import numpy as np

from ...inti.material import bahan
from ...inti.qc import iou
from ...inti.render import pilih_perangkat
from . import pohon


def cocokkan(OUT):
    RAHASIA = dict(pohon.PRESET["rindang"], radius_tajuk=2.7, tebal_tajuk=3.4, tinggi_tajuk=6.2)
    SEED_REF, SEED_CALON = 33, 7  # seed beda: meniru karakter, bukan klon cabang per cabang
    CARI = ["radius_tajuk", "tebal_tajuk", "tinggi_tajuk"]
    sc = bpy.context.scene


    def bersihkan():
        for o in list(bpy.data.objects):
            if o.type != "CAMERA":
                bpy.data.objects.remove(o)
        for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
            for d in list(coll):
                if d.users == 0:
                    coll.remove(d)


    def siluet(params, seed, nama):
        bersihkan()
        pohon.PRESET["uji"] = params
        pohon.bangun_pohon("uji", seed, 0.0)
        sc.render.filepath = os.path.join(OUT, f"_mask_{nama}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        a = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[:, :, 3] > 0.5
        bpy.data.images.remove(img)
        return a


    # kamera ortografis tampak depan + render Workbench transparan (alpha = siluet)
    cam = sc.camera
    cam.location, cam.rotation_euler = (0, -40, 5.5), (math.radians(90), 0, 0)
    cam.data.type, cam.data.ortho_scale = "ORTHO", 15
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = 220
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGBA"

    t0 = time.time()
    ref = siluet(RAHASIA, SEED_REF, "referensi")
    tebak = dict(pohon.PRESET["rindang"])  # titik awal: preset standar (belum mirip)
    langkah = {"radius_tajuk": 0.8, "tebal_tajuk": 0.8, "tinggi_tajuk": 0.8}
    skor = iou(ref, siluet(tebak, SEED_CALON, "calon"))
    riwayat = [round(skor, 3)]
    evaluasi = 1
    for putaran in range(8):
        membaik = False
        for k in CARI:
            for arah in (+1, -1):
                coba = dict(tebak, **{k: max(0.5, tebak[k] + arah * langkah[k])})
                s = iou(ref, siluet(coba, SEED_CALON, "calon"))
                evaluasi += 1
                if s > skor:
                    tebak, skor, membaik = coba, s, True
                    break
        riwayat.append(round(skor, 3))
        if not membaik:
            langkah = {k: v / 2 for k, v in langkah.items()}
            if max(langkah.values()) < 0.1:
                break

    terbaik = siluet(tebak, SEED_CALON, "terbaik")
    # gambar perbandingan siluet: merah = referensi saja, biru = tebakan saja, putih = cocok
    h, w = ref.shape
    rgb = np.zeros((h, w, 4), dtype=np.float32)
    rgb[..., 3] = 1
    rgb[ref & terbaik] = (1, 1, 1, 1)
    rgb[ref & ~terbaik] = (0.9, 0.2, 0.2, 1)
    rgb[~ref & terbaik] = (0.2, 0.4, 0.95, 1)
    cmp = bpy.data.images.new("banding", w, h, alpha=True)
    cmp.pixels = rgb.ravel()
    cmp.filepath_raw, cmp.file_format = os.path.join(OUT, "cocok_siluet.png"), "PNG"
    cmp.save()

    hasil = {
        "parameter_rahasia": {k: RAHASIA[k] for k in CARI},
        "parameter_awal": {k: pohon.PRESET["rindang"][k] for k in CARI},
        "parameter_tebakan": {k: round(tebak[k], 2) for k in CARI},
        "IoU_awal": riwayat[0], "IoU_akhir": round(skor, 3), "riwayat_IoU": riwayat,
        "jumlah_evaluasi": evaluasi, "detik": round(time.time() - t0, 1),
    }
    with open(os.path.join(OUT, "cocok_hasil.json"), "w") as f:
        json.dump(hasil, f, indent=1)
    print("HASIL " + json.dumps(hasil))

    # render cantik: referensi (kiri) vs tiruan (kanan)
    bersihkan()
    pohon.PRESET["ref"], pohon.PRESET["tiru"] = RAHASIA, tebak
    pohon.bangun_pohon("ref", SEED_REF, -5.0)
    pohon.bangun_pohon("tiru", SEED_CALON, 5.0)
    bpy.ops.mesh.primitive_plane_add(size=80)
    bpy.context.active_object.data.materials.append(bahan("tanah", (0.16, 0.20, 0.10), 0.95))
    sun = bpy.data.objects.new("Matahari", bpy.data.lights.new("Matahari", "SUN"))
    sun.data.energy, sun.rotation_euler = 4.0, (math.radians(50), 0, math.radians(35))
    bpy.context.collection.objects.link(sun)
    bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value, bg.inputs[1].default_value = (0.55, 0.70, 0.95, 1), 0.9
    cam.data.type, cam.data.lens = "PERSP", 35
    cam.location, cam.rotation_euler = (0, -26, 5.5), (math.radians(87), 0, 0)
    sc.render.film_transparent = False
    sc.render.engine, sc.cycles.samples = "CYCLES", 96
    sc.cycles.transparent_max_bounces = 48
    pilih_perangkat()  # GPU bila ada, selain itu CPU (spike lama memaksa OptiX)
    sc.render.resolution_x, sc.render.resolution_y = 1400, 720
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = os.path.join(OUT, "cocok_render.png")
    bpy.ops.render.render(write_still=True)
    for f in os.listdir(OUT):
        if f.startswith("_mask_"):
            os.remove(os.path.join(OUT, f))
