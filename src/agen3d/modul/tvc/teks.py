"""Teks kinetik 3D (extrude + bevel, tinta emisi) sebagai anak kamera shot teks. Isi, tata letak per rasio, dan
jadwal: tvc.toml [teks]. Font Inter.woff2 bawaan Blender (Bfont menggambar "1" seperti "I")."""
import math
import os

import bpy
from mathutils import Matrix

from ...inti.kamera import uv_ke_lokal
from ...inti.scene import koleksi
from ...inti.warna import lin
from . import konfig
from .kunci import kunci, kunci_vektor, tampil


def bahan_tinta(nama="tinta", hexa=None):
    hexa = hexa or konfig.K["teks"]["tinta"]
    m = bpy.data.materials.get(nama)
    if m is None:
        m = bpy.data.materials.new(nama)
        m.use_nodes = True
        t = m.node_tree
        for n in list(t.nodes):
            if n.type != "OUTPUT_MATERIAL":
                t.nodes.remove(n)
        em = t.nodes.new("ShaderNodeEmission")
        t.links.new(em.outputs[0], next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL").inputs["Surface"])
    em = next(n for n in m.node_tree.nodes if n.type == "EMISSION")
    em.inputs["Color"].default_value = (*lin(hexa), 1)
    em.inputs["Strength"].default_value = 1.0
    m["hex"] = hexa
    return m


def font():
    """Inter (bawaan Blender, sama di Windows dan Linux). Bfont bawaan menggambar "1" seperti "I" (cek mata)."""
    p = os.path.join(bpy.utils.system_resource("DATAFILES", path="fonts") or "", "Inter.woff2")
    f = next((f for f in bpy.data.fonts if f.filepath == p), None)
    if f is None and os.path.isfile(p):
        f = bpy.data.fonts.load(p)
    return f


def teks_obj(nama, isi, kol, extrude=0.06, tebal=0.0):
    """tebal = offset kontur glyph (Inter variable dimuat sebagai Regular; offset menebalkan judul)."""
    cu = bpy.data.curves.new(nama, "FONT")
    cu.body = isi
    f = font()
    if f:
        cu.font = f
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.size, cu.extrude, cu.bevel_depth, cu.bevel_resolution = 1.0, extrude, 0.012, 2
    cu.offset, cu.space_character = tebal, 1.0 + 2.5 * tebal  # offset melebarkan glyph: jarak huruf ikut
    ob = bpy.data.objects.new(nama, cu)
    kol.objects.link(ob)
    cu.materials.append(bahan_tinta())
    return ob


def teks(rasio, cam):
    """Judul flip-in + pop (BACK) di awal shot teks, tagline kata per kata di seperdelapan ketukan (6 frame),
    kata_pop diperbesar + miring seperti stiker, label spec muncul halus."""
    T = konfig.K["teks"]
    k = koleksi("TEKS")
    sc = bpy.context.scene
    tata = T["tata"][rasio]
    jarak = T["jarak"]
    f0, _ = konfig.f_shot(T["shot"])
    out = {}

    def pasang(ob, u, v, lebar):
        bpy.context.view_layer.update()
        p, wf = uv_ke_lokal(cam, u, v, jarak)
        s = lebar * wf / max(ob.dimensions.x, 1e-6)
        ob.parent = cam
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.location, ob["skala"] = p, s
        return s

    j = teks_obj("TX_judul", T["judul"], k, tebal=0.014)
    sj = pasang(j, *tata["judul"])
    kunci_vektor(j, "scale", 1, (0, 0, 0), "CONSTANT")
    kunci_vektor(j, "scale", f0, (0, 0, 0), "BACK", "EASE_OUT")
    kunci_vektor(j, "scale", f0 + 11, (sj,) * 3)
    kunci(j, "rotation_euler", f0, math.radians(75), "BACK", "EASE_OUT", 0)
    kunci(j, "rotation_euler", f0 + 13, 0.0, indeks=0)
    out["judul"] = j
    # tagline kata per kata: lebar total = lebar target; spasi = lebar spasi font
    kata = T["tagline"].split()
    obs = [teks_obj(f"TX_tag_{i}_{w.strip(',.')}", w, k, tebal=0.008) for i, w in enumerate(kata)]
    bpy.context.view_layer.update()
    spasi = [T["spasi"]] * (len(obs) - 2) + [T["spasi_pop"]]
    lebar_total = sum(o.dimensions.x for o in obs) + sum(spasi)
    u, v, lebar = tata["tagline"]
    p0, wf = uv_ke_lokal(cam, u, v, jarak)
    s = lebar * wf / lebar_total
    x = p0.x - lebar_total * s / 2
    for i, o in enumerate(obs):
        w = o.dimensions.x
        o.parent = cam
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.location = (x + w * s / 2, p0.y, p0.z)
        x += (w + (spasi[i] if i < len(spasi) else 0)) * s
        f = f0 + 13 + 6 * i
        pop = o.name.endswith(T["kata_pop"])
        kunci_vektor(o, "scale", 1, (0, 0, 0), "CONSTANT")
        kunci_vektor(o, "scale", f, (0, 0, 0), "BACK", "EASE_OUT")
        kunci_vektor(o, "scale", f + 7, (s * (1.12 if pop else 1.0),) * 3)
        kunci(o, "location", f, p0.y - 0.012 * s * 4, "BACK", "EASE_OUT", 1)
        kunci(o, "location", f + 7, p0.y, indeks=1)
        if pop:
            kunci(o, "rotation_euler", f, math.radians(-14), "BACK", "EASE_OUT", 2)
            kunci(o, "rotation_euler", f + 9, math.radians(-5), indeks=2)
    out["tagline"] = obs
    lb = teks_obj("TX_label", T["label"], k, extrude=0.0)
    sl = pasang(lb, *tata["label"])
    kunci_vektor(lb, "scale", 1, (0, 0, 0), "CONSTANT")
    kunci_vektor(lb, "scale", f0 + 44, (sl * 0.6,) * 3, "SINE", "EASE_OUT")
    kunci_vektor(lb, "scale", f0 + 51, (sl,) * 3)
    out["label"] = lb
    for o in [j, lb] + obs:
        tampil(o, [(f0, konfig.FRAME_AKHIR)])
        o.visible_shadow = False
    sc.frame_set(sc.frame_start)
    return out
