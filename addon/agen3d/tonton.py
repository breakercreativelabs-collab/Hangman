"""Mode tonton: Blender yang terbuka memantau folder tonton (ditulis `perakit bangun --tonton 1`) dan menampilkan
model langkah demi langkah dengan efek tumbuh. Tanpa socket/jaringan: hanya membaca berkas.
Dipakai oleh __init__.py ekstensi (panel + preferensi). Lisensi: GPL-3.0-or-later.
"""
import json
import os
import time

import bpy
import numpy as np

JEDA = 0.35        # detik antar-tik pemantau
TUMBUH = 0.6       # detik efek tumbuh per langkah
NAMA_OBJ = "TONTON"
_keadaan = dict(aktif=False, akar="", sejak=0.0, folder="", tampil=-1, mulai_tumbuh=0.0)


def baca_manifest(folder):
    """dict manifest atau None (belum ada, sedang ditulis, rusak) - tidak pernah melempar galat."""
    try:
        with open(os.path.join(folder, "tonton.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d.get("langkah"), list) else None
    except (OSError, ValueError, AttributeError):
        return None


def folder_terbaru(akar, sejak=0.0):
    """Subfolder akar (atau akar itu sendiri) yang manifest-nya paling baru diubah (dan tidak lebih tua dari `sejak`);
    None bila tidak ada."""
    calon = [akar] + [os.path.join(akar, d) for d in sorted(os.listdir(akar))] if os.path.isdir(akar) else []
    calon = [c for c in calon if os.path.isfile(os.path.join(c, "tonton.json")) and
             os.path.getmtime(os.path.join(c, "tonton.json")) >= sejak]
    return max(calon, key=lambda c: os.path.getmtime(os.path.join(c, "tonton.json")), default=None)


def mesh_npz(path, nama):
    """Mesh Blender dari langkah_NN.npz (titik mm, quad) atau None bila berkas belum lengkap."""
    try:
        d = np.load(path)
        titik, quad = d["titik"].astype(np.float32) * 0.001, d["quad"].astype(np.int32)
    except Exception:  # noqa: BLE001 - npz setengah tertulis (BadZipFile, EOFError, ...): coba lagi tik berikutnya
        return None
    me = bpy.data.meshes.new(nama)
    me.vertices.add(len(titik))
    me.vertices.foreach_set("co", titik.ravel())
    me.loops.add(quad.size)
    me.loops.foreach_set("vertex_index", quad.ravel())
    me.polygons.add(len(quad))
    me.polygons.foreach_set("loop_start", np.arange(0, quad.size, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(quad), 4, np.int32))
    me.update()
    me.validate()
    return me


def mesh_glb(path, nama):
    """Mesh dari model.glb (langkah akhir = mesh serah, identik dengan hasil headless)."""
    if not os.path.isfile(path):
        return None
    sebelum = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    baru = [o for o in bpy.data.objects if o not in sebelum]
    ob = next((o for o in baru if o.type == "MESH"), None)
    me = None
    if ob:
        me = ob.data.copy()
        me.transform(ob.matrix_world)
        me.name = nama
    for o in baru:
        bpy.data.objects.remove(o)
    return me


def muat_langkah(folder, item):
    path = os.path.join(folder, item["berkas"])
    return mesh_glb(path, item["nama"]) if item["berkas"].endswith(".glb") else mesh_npz(path, item["nama"])


def tampilkan(me):
    """Ganti mesh objek TONTON (dibuat bila belum ada) dan mulai efek tumbuh."""
    ob = bpy.data.objects.get(NAMA_OBJ)
    if ob is None:
        ob = bpy.data.objects.new(NAMA_OBJ, me)
        bpy.context.scene.collection.objects.link(ob)
    else:
        lama = ob.data
        ob.data = me
        if lama.users == 0:
            bpy.data.meshes.remove(lama)
    for p in me.polygons:
        p.use_smooth = True
    ob.scale = (1.0, 1.0, 0.05)
    _keadaan["mulai_tumbuh"] = time.time()
    return ob


def tumbuh(ob, sekarang):
    """Skala Z 0,05 -> 1 dengan ease-out selama TUMBUH detik (alas di z = 0, jadi tumbuh dari bawah)."""
    t = min((sekarang - _keadaan["mulai_tumbuh"]) / TUMBUH, 1.0)
    ob.scale = (1.0, 1.0, 0.05 + 0.95 * (1 - (1 - t) ** 3))
    return t >= 1.0


def _bingkai():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next(r for r in area.regions if r.type == "WINDOW")
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.view3d.view_selected()
                return


def tik():
    """Satu langkah pemantau (dipanggil bpy.app.timers). Satu langkah model per tik agar prosesnya terlihat."""
    if not _keadaan["aktif"]:
        return None
    ob = bpy.data.objects.get(NAMA_OBJ)
    if ob and not tumbuh(ob, time.time()):
        return 0.03  # animasi tumbuh masih berjalan
    folder = folder_terbaru(_keadaan["akar"], _keadaan["sejak"])
    if folder is None:
        return JEDA
    if folder != _keadaan["folder"]:  # job baru: mulai dari langkah pertama
        _keadaan.update(folder=folder, tampil=-1)
    d = baca_manifest(folder)
    if d is None or _keadaan["tampil"] + 1 >= len(d["langkah"]):
        return JEDA
    i = _keadaan["tampil"] + 1
    me = muat_langkah(folder, d["langkah"][i])
    if me is None:
        return JEDA  # berkas belum siap: coba lagi tik berikutnya
    ob = tampilkan(me)
    _keadaan["tampil"] = i
    if i == 0:
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        _bingkai()
    print(f"[tonton] {os.path.basename(folder)} langkah {i + 1}/{len(d['langkah'])}: {d['langkah'][i]['nama']}")
    return 0.03


def mulai(akar, hanya_baru=False):
    """Mulai memantau `akar` (folder artefak/tonton di folder kerja). hanya_baru: abaikan job yang sudah ada
    (otomatis saat Blender dibuka, agar job lama tidak diputar ulang)."""
    _keadaan.update(aktif=True, akar=akar, sejak=time.time() if hanya_baru else 0.0, folder="", tampil=-1)
    if not bpy.app.timers.is_registered(tik):
        bpy.app.timers.register(tik, first_interval=0.1, persistent=True)


def henti():
    _keadaan["aktif"] = False


def status():
    """Teks status untuk panel."""
    if not _keadaan["aktif"]:
        return "live preview off"
    if not _keadaan["folder"]:
        return "waiting for a model from Claude..."
    d = baca_manifest(_keadaan["folder"]) or {}
    n = len(d.get("langkah", []))
    return f"{d.get('nama', '?')}: step {_keadaan['tampil'] + 1}/{n}" + (" (done)" if d.get("selesai") else "")
