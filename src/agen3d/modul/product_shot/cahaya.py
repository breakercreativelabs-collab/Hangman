"""VERB 3 studio_lighting: lampu area + backdrop cyclorama, diskalakan ke tinggi produk."""
import math

import bpy
import numpy as np
from mathutils import Vector

from ...inti.kamera import arah, hadap
from ...inti.material import bahan
from ...inti.scene import control, drive, koleksi
from .verbs import ukuran_produk

# az: derajat dari -Y (arah kamera) ke +X; el: derajat elevasi; jarak & ukuran dalam kelipatan tinggi produk.
PRESET_CAHAYA = {
    "softbox": dict(latar=0.30, dunia=0.04, lampu=[
        ("key", -40, 28, 4.0, (1.6, 2.4), 1.00),
        ("fill", 55, 12, 5.0, (2.2, 2.2), 0.30),
        ("rim", 155, 35, 3.5, (0.4, 3.0), 0.90)]),
    "high_key": dict(latar=0.80, dunia=0.25, lampu=[
        ("kiri", -55, 20, 4.0, (2.4, 3.0), 0.55),   # v2: 0,80 -> 0,55, label botol pudar (QC-10 0,63)
        ("kanan", 55, 20, 4.0, (2.4, 3.0), 0.55),
        ("atas", 0, 75, 4.0, (2.4, 2.4), 0.40)]),
    "dramatis": dict(latar=0.06, dunia=0.0, lampu=[
        ("rim_kiri", -115, 18, 3.0, (0.35, 3.2), 1.30),
        ("rim_kanan", 115, 18, 3.0, (0.35, 3.2), 1.30),
        ("key", -30, 50, 4.5, (1.2, 1.2), 1.40)],  # v2: 0,45 -> 1,40, label putih tampil abu (QC-10)
        # C-15: logam tegak (leher kaleng slim) memantulkan arah depan-bawah yang gelap -> hitam pekat.
        # Kartu pantulan di belakang kamera, hanya terlihat sinar glossy (tidak menambah cahaya difus).
        refleksi=[("kartu_depan", 0, 10, 4.5, (6.0, 1.5), 0.10)]),
}
DAYA_DASAR = 12.0  # W per m^2 jarak (kalibrasi 2026-10-13, QC-10); daya lampu = faktor x DAYA_DASAR x jarak^2 (irradiansi konstan lintas ukuran produk)


def backdrop(h, kecerahan):
    """Cyclorama: lantai menyambung lengkung ke dinding (tanpa garis horizon). Ukuran relatif tinggi produk."""
    kb = koleksi("BACKDROP")
    for o in list(kb.objects):
        bpy.data.objects.remove(o)
    W, F, B, R, H = 30 * h, 12 * h, 3 * h, 5 * h, 18 * h
    prof = [(-F, 0.0), (B, 0.0)] + [(B + R * math.sin(t), R - R * math.cos(t))
                                     for t in np.linspace(0, math.pi / 2, 17)[1:]] + [(B + R, H)]
    vs = [(x, y, z) for y, z in prof for x in (-W / 2, W / 2)]
    fs = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(prof) - 1)]
    me = bpy.data.meshes.new("backdrop")
    me.from_pydata(vs, [], fs)
    me.shade_smooth()
    ob = bpy.data.objects.new("backdrop", me)
    kb.objects.link(ob)
    me.materials.append(bahan("backdrop", (kecerahan,) * 3, 0.6))
    return ob


def studio_lighting(preset="softbox"):
    """Lampu area (softbox/strip) + backdrop cyclorama, diskalakan ke tinggi produk.
    Energi semua lampu di-drive CONTROL['intensitas_cahaya']."""
    p = PRESET_CAHAYA[preset]
    h, _ = ukuran_produk()
    pusat = Vector((0, 0, h * 0.5))
    kl = koleksi("LIGHTS")
    for o in list(kl.objects):
        bpy.data.objects.remove(o)
    refleksi = {r[0] for r in p.get("refleksi", [])}
    for nama, az, el, jarak, (sx, sy), f in p["lampu"] + p.get("refleksi", []):
        d = bpy.data.lights.new(f"L_{nama}", "AREA")
        d.shape, d.size, d.size_y = "RECTANGLE", sx * h, sy * h
        energi = f * DAYA_DASAR * (jarak * h) ** 2
        d.energy = energi
        ob = bpy.data.objects.new(f"L_{nama}", d)
        ob.location = pusat + arah(az, el) * jarak * h
        hadap(ob, pusat)
        kl.objects.link(ob)
        if nama in refleksi:  # kartu pantulan: hanya sinar glossy (sorot di logam/kaca), bukan cahaya difus
            ob.visible_diffuse = ob.visible_transmission = ob.visible_volume_scatter = False
        drive(d, "energy", "intensitas_cahaya", f"var*{energi:.5f}")
    backdrop(h, p["latar"])
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (1, 1, 1, 1)
    bg.inputs[1].default_value = p["dunia"]
    control()["preset_cahaya"] = preset
    return [o.name for o in kl.objects]
