"""Scene standar .blend (PS-1), dipakai semua modul.

Collection PRODUCT / LIGHTS / CAMERAS / BACKDROP + objek CONTROL (custom property).
Hierarki produk: TURNTABLE (empty, dianimasikan) -> PRODUCT_ROOT (empty, identitas) -> mesh produk.
Konvensi: satuan meter, lantai z = 0, sisi depan produk menghadap -Y, kamera di arah -Y.
"""
import bpy
import numpy as np
from bpy_extras import anim_utils

KOLEKSI = ("PRODUCT", "LIGHTS", "CAMERAS", "BACKDROP")
STANDAR = "PS-1"
RASIO_BAWAAN = "16:9,9:16,1:1"  # CONTROL['rasio'] (rasio render product shot)


def koleksi(nama):
    k = bpy.data.collections.get(nama)
    if k is None:
        k = bpy.data.collections.new(nama)
    if k.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(k)
    return k


def control():
    return bpy.data.objects.get("CONTROL")


def siapkan_scene():
    """Kosongkan scene, buat 4 collection standar + objek CONTROL."""
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    for k in list(bpy.data.collections):
        bpy.data.collections.remove(k)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)  # material/mesh lama tidak menumpuk
    for nama in KOLEKSI:
        koleksi(nama)
    c = bpy.data.objects.new("CONTROL", None)
    c.empty_display_type, c.empty_display_size = "CUBE", 0.02
    bpy.context.scene.collection.objects.link(c)
    c["standar"] = STANDAR
    c["warna_varian"] = [0.5, 0.5, 0.5]
    c.id_properties_ui("warna_varian").update(subtype="COLOR", min=0.0, max=1.0)
    c["warna_hex"] = "#808080"
    c["intensitas_cahaya"] = 1.0
    c.id_properties_ui("intensitas_cahaya").update(min=0.0, soft_max=3.0)
    for k, v in (("produk", ""), ("preset_cahaya", ""), ("easing", ""), ("durasi_detik", 0.0),
                 ("fps", 25), ("isi_target", 0.70), ("rasio", RASIO_BAWAAN)):
        c[k] = v
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.view_settings.view_transform = "Khronos PBR Neutral"  # warna brand akurat (AgX mendesaturasi kuning terang, QC-10)
    sc.view_settings.look = "None"
    return c


def drive(idblock, path, prop, ekspresi="var", indeks=-1):
    """Driver sederhana dari CONTROL[prop] (ekspresi aritmetika sederhana, tidak butuh auto-run Python)."""
    fc = idblock.driver_add(path, indeks) if indeks >= 0 else idblock.driver_add(path)
    d = fc.driver
    d.type, d.expression = "SCRIPTED", ekspresi
    v = d.variables.new()
    v.name, v.type = "var", "SINGLE_PROP"
    v.targets[0].id = control()
    v.targets[0].data_path = f'["{prop}"]' + (f"[{indeks}]" if indeks >= 0 else "")
    return fc


def fcurves(idblock):
    """F-curve sebuah ID (objek, kamera, node group; action berlapis Blender 4.4+/5.x)."""
    ad = idblock.animation_data
    if not ad or not ad.action:
        return []
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(cb.fcurves) if cb else []


def objek_produk():
    return [o for o in koleksi("PRODUCT").all_objects if o.type == "MESH" and not o.hide_render]


def titik_produk():
    """Semua vertex produk (sesudah modifier) dalam koordinat dunia, array N x 3 (meter)."""
    dg = bpy.context.evaluated_depsgraph_get()
    hasil = []
    for ob in objek_produk():
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, "f")
        me.vertices.foreach_get("co", co)
        M = np.array(ev.matrix_world)
        hasil.append(co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3])
        ev.to_mesh_clear()
    return np.vstack(hasil) if hasil else np.zeros((0, 3))


def root():
    """PRODUCT_ROOT (dibuat bersama TURNTABLE induknya bila belum ada)."""
    r = bpy.data.objects.get("PRODUCT_ROOT")
    if r:
        return r
    pk = koleksi("PRODUCT")
    tt = bpy.data.objects.new("TURNTABLE", None)
    tt.empty_display_type, tt.empty_display_size = "CIRCLE", 0.05
    r = bpy.data.objects.new("PRODUCT_ROOT", None)
    r.empty_display_size = 0.02
    pk.objects.link(tt)
    pk.objects.link(r)
    r.parent = tt
    r["depan"] = "-Y"
    return r
