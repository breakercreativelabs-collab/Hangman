"""Foto referensi SINTETIS untuk uji asap ekstraksi (suite runner `cli`, Tugas 10 C-B3). Non-generatif: render Blender
ortografis model proyek dengan warna rata per peran meniru colorway foto asli (putih/hitam: mudguard, swoosh, overlay
gelap; midsole putih; kapsul abu = jendela). Bukan data ukur: hanya agar ekstrak_kontur / ekstrak_panel /
analisis_alfa bisa dijalankan tanpa foto klien (foto asli tidak pernah masuk repo).

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- modeling_referensi foto_uji --out <folder>
Keluaran: <folder>/{lateral,medial,atas,tumit,sol}.png (RGBA, alfa = siluet). Tampak atas/tumit berisi SEPASANG
sepatu (kanan + cermin) seperti foto produk (kontur.pisah_pasangan).
"""
import math
import os

import bpy
from mathutils import Vector

from ....inti.kamera import hadap, kamera
from ....inti.render import render_gambar
from ....inti.scene import objek_produk, root
from ....inti.warna import lin

# luma rata per peran (meniru FD9082-107: panel gelap luma < 0,45, midsole terang > 0,6, jendela < 0,6)
WARNA = dict(mudguard="#262626", overlay_suede="#2E2E2E", swoosh="#1A1A1A", outsole="#3A3A3A", midsole="#F4F4F4",
             kapsul_air="#8C8C8C", upper_mesh="#E8E8E8", lining="#E0E0E0", tali="#F0F0F0", aksen_chrome="#B0B0B0")
PX_M = 2500                   # piksel per meter (0,4 mm/px; panjang sepatu ~730 px)


def _bahan_emisi_uji(hexa):
    m = bpy.data.materials.new("_uji_" + hexa)
    t = m.node_tree
    for n in list(t.nodes):
        if n.type != "OUTPUT_MATERIAL":
            t.nodes.remove(n)
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(hexa), 1)
    t.links.new(em.outputs[0], next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL").inputs["Surface"])
    return m


def foto_uji(out):
    os.makedirs(out, exist_ok=True)
    sc = bpy.context.scene
    sc.view_settings.view_transform, sc.view_settings.exposure = "Standard", 0.0
    sc.world = bpy.data.worlds.new("_uji_dunia")
    sc.cycles.use_denoising = False
    mat = {k: _bahan_emisi_uji(v) for k, v in WARNA.items()}
    for ob in objek_produk():
        for i, m in enumerate(ob.data.materials):
            ob.data.materials[i] = mat.get(m.name if m else "", mat["midsole"])
    r0 = root()
    pasang = r0.copy()  # sepatu kiri (cermin Y) untuk tampak atas/tumit
    bpy.context.scene.collection.objects.link(pasang)
    for ob in objek_produk():
        c = ob.copy()
        bpy.context.scene.collection.objects.link(c)
        c.parent = pasang
    pasang.scale.y = -1
    pasang.location.y = 0.14
    c0 = Vector((0.147, 0.0, 0.065))
    hasil = []
    for nama, arah, w, h, dua in (("lateral", (0, -1, 0), 800, 400, False), ("medial", (0, 1, 0), 800, 400, False),
                                  ("sol", (0, 0, -1), 800, 400, False), ("atas", (0, 0, 1), 800, 800, True),
                                  ("tumit", (1, 0, 0), 800, 400, True)):
        pasang.hide_render = not dua
        for c in pasang.children:
            c.hide_render = not dua
        pusat = c0 + (Vector((0, 0.07, 0)) if dua else Vector())
        cam = kamera("CAM_uji_" + nama, pusat + Vector(arah) * 1.0, (0, 0, 0), orto=w / PX_M)
        hadap(cam, pusat)
        if nama == "sol":  # toe di kiri gambar
            cam.rotation_euler.z += math.pi
        hasil.append(render_gambar(cam, os.path.join(out, nama + ".png"), w, h, 1, True))
    return hasil
