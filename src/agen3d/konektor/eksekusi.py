"""Dijalankan DI DALAM Blender lewat CLI tunggal (perintah meta, tidak tercantum di `bantuan`):

  blender -b [berkas.blend] --factory-startup -P blender_cli.py -- __kode__ <folder_pekerjaan>
  blender -b --factory-startup -P blender_cli.py -- __diagnosa__ <berkas.json>

__kode__ menjalankan `kode.py` di folder pekerjaan (alat MCP `jalankan_kode`: Python Blender BEBAS), lalu menulis
`hasil.json`: ok, galat (traceback), stdout, HASIL (variabel opsional yang diisi kode), ringkasan scene, berkas tersimpan,
pratinjau. Kode punya akses penuh ke Blender dan komputer pengguna: pengguna menyetujui setiap panggilan di aplikasi
Claude, dan setiap kode tersimpan di folder pekerjaannya (jejak audit + bahan belajar: kode yang sering dipakai
dijadikan verb teruji).
"""
import contextlib
import io as _io
import json
import math
import os
import sys
import time
import traceback

import bpy
from mathutils import Vector

from ..inti.io import tulis_json
from ..inti.render import pilih_perangkat, render_gambar

MAKS_STDOUT = 20000


def ringkas_scene():
    sc = bpy.context.scene
    obs = list(sc.objects)
    jenis = {}
    for o in obs:
        jenis[o.type] = jenis.get(o.type, 0) + 1
    contoh = [dict(nama=o.name, jenis=o.type, dimensi_m=[round(x, 4) for x in o.dimensions],
                   lokasi_m=[round(x, 4) for x in o.location]) for o in obs[:30]]
    return dict(berkas=bpy.data.filepath or "(belum disimpan)", objek=len(obs), per_jenis=jenis, contoh=contoh,
                kamera=sc.camera.name if sc.camera else None, frame=[sc.frame_start, sc.frame_end],
                mesin=sc.render.engine, material=len(bpy.data.materials))


def _kamera_pratinjau():
    """Kamera aktif scene; bila tidak ada, kamera 3/4 sementara yang membingkai semua objek bergeometri."""
    sc = bpy.context.scene
    if sc.camera:
        return sc.camera
    pts = [o.matrix_world @ Vector(c) for o in sc.objects if o.type in ("MESH", "CURVE", "SURFACE", "META", "FONT")
           for c in o.bound_box]
    if not pts:
        pts = [Vector((0, 0, 0))]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    pusat, r = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)
    data = bpy.data.cameras.new("_PRATINJAU")
    cam = bpy.data.objects.new("_PRATINJAU", data)
    sc.collection.objects.link(cam)
    jarak = r / math.tan(data.angle / 2) * 1.15
    arah = Vector((math.cos(math.radians(35)) * math.cos(math.radians(-50)),
                   math.cos(math.radians(35)) * math.sin(math.radians(-50)), math.sin(math.radians(25))))
    cam.location = pusat + arah.normalized() * jarak
    cam.rotation_euler = (pusat - cam.location).to_track_quat("-Z", "Y").to_euler()
    data.clip_end = max(100.0, jarak * 4)
    return cam


def render_pratinjau(path, lebar=640):
    """Render cepat Cycles (GPU bila ada) 640 px; tidak mengubah berkas .blend (dipanggil setelah simpan)."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    pilih_perangkat()
    sc.cycles.use_denoising = True
    if not any(o.type == "LIGHT" for o in sc.objects) and sc.world is None:
        sc.world = bpy.data.worlds.new("_PRATINJAU")
    if sc.world and sc.world.use_nodes is False:
        sc.world.use_nodes = True
    cam = _kamera_pratinjau()
    rx, ry = max(sc.render.resolution_x, 1), max(sc.render.resolution_y, 1)
    tinggi = max(int(lebar * ry / rx), 16)
    return render_gambar(cam, path, lebar, tinggi, 16, False)


def kode(argv):
    folder = os.path.abspath(argv[0])
    with open(os.path.join(folder, "permintaan.json"), encoding="utf-8") as f:
        req = json.load(f)
    with open(os.path.join(folder, "kode.py"), encoding="utf-8") as f:
        sumber = f.read()
    t0, buf = time.time(), _io.StringIO()
    hasil = dict(ok=False)
    ns = {"__name__": "__main__", "__file__": os.path.join(folder, "kode.py"), "bpy": bpy}
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(sumber, ns["__file__"], "exec"), ns)  # noqa: S102 - inti alat jalankan_kode (disetujui pengguna)
        hasil["ok"] = True
    except SystemExit as e:  # sys.exit(0)/sys.exit() di kode = selesai normal; kode lain = gagal
        hasil["ok"] = e.code in (0, None)
        if not hasil["ok"]:
            hasil["galat"] = f"SystemExit({e.code!r})"
    except BaseException:  # noqa: BLE001 - KeyboardInterrupt dll. juga dilaporkan sebagai galat kode
        hasil["galat"] = traceback.format_exc()[-6000:]
    hasil["stdout"] = buf.getvalue()[-MAKS_STDOUT:]
    if "HASIL" in ns:
        try:
            json.dumps(ns["HASIL"])
            hasil["HASIL"] = ns["HASIL"]
        except (TypeError, ValueError):
            hasil["HASIL"] = repr(ns["HASIL"])[:5000]
    if hasil["ok"] and req.get("simpan"):
        tujuan = os.path.abspath(req["simpan"])  # C-10
        os.makedirs(os.path.dirname(tujuan), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=tujuan, compress=True)
        hasil["tersimpan"] = tujuan if os.path.isfile(tujuan) else None
    hasil["scene"] = ringkas_scene()
    if req.get("pratinjau"):
        try:
            hasil["pratinjau"] = render_pratinjau(os.path.join(folder, "pratinjau.png"))
        except Exception:  # noqa: BLE001 - pratinjau opsional; galatnya dilaporkan
            hasil["galat_pratinjau"] = traceback.format_exc()[-2000:]
    hasil["detik"] = round(time.time() - t0, 2)
    tulis_json(os.path.join(folder, "hasil.json"), hasil)
    print("KODE", "OK" if hasil["ok"] else "GAGAL", hasil["detik"], "s")
    return 0 if hasil["ok"] else 1


def diagnosa(argv):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = {}
    for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = t
        except TypeError:
            continue
        prefs.get_devices()
        nama = [d.name for d in prefs.devices if d.type == t]
        if nama:
            gpu[t] = nama
    import numpy
    tulis_json(os.path.abspath(argv[0]), dict(blender=bpy.app.version_string, python=sys.version.split()[0],
                                          numpy=numpy.__version__, gpu=gpu, perangkat_dipilih=next(iter(gpu), "CPU")))
    return 0
