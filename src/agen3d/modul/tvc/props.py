"""Props TVC: gelembung sabun thin-film pastel (letus + percikan + naik) dan podium gradasi."""
import bmesh
import bpy
import numpy as np
from mathutils import Vector

from ...inti.material import bsdf, matematika
from ...inti.scene import koleksi
from ...inti.warna import lin
from . import konfig
from .kunci import kunci_vektor, tampil


def bahan_gelembung():
    """Gelembung sabun thin-film pastel: transparan di tengah, film tipis interferensi (Principled Thin Film, tebal
    acak 280-720 nm per objek) makin kuat ke tepi (Layer Weight facing), sedikit emisi pastel di tepi."""
    m = bpy.data.materials.get("gelembung")
    if m:
        return m
    m = bpy.data.materials.new("gelembung")
    m.use_nodes = True
    t = m.node_tree
    for n in list(t.nodes):
        if n.type != "OUTPUT_MATERIAL":
            t.nodes.remove(n)
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    info = t.nodes.new("ShaderNodeObjectInfo")
    tebal = matematika(t, "ADD", matematika(t, "MULTIPLY", info.outputs["Random"], 440.0), 280.0)
    b = t.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value, b.inputs["IOR"].default_value = 0.02, 1.33
    b.inputs["Specular IOR Level"].default_value = 1.0
    t.links.new(tebal, b.inputs["Thin Film Thickness"])
    b.inputs["Thin Film IOR"].default_value = 1.33
    tr = t.nodes.new("ShaderNodeBsdfTransparent")
    lw = t.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    fac = matematika(t, "POWER", lw.outputs["Facing"], 2.2)
    mix = t.nodes.new("ShaderNodeMixShader")
    t.links.new(fac, mix.inputs[0])
    t.links.new(tr.outputs[0], mix.inputs[1])
    t.links.new(b.outputs[0], mix.inputs[2])
    ramp = t.nodes.new("ShaderNodeValToRGB")  # warna tepi pastel per gelembung
    el = ramp.color_ramp.elements
    for i, (pos, h) in enumerate(konfig.K["gelembung"]["warna_tepi"]):
        e = el[i] if i < len(el) else el.new(pos)
        e.position, e.color = pos, (*lin(h), 1)
    t.links.new(info.outputs["Random"], ramp.inputs["Fac"])
    em = t.nodes.new("ShaderNodeEmission")
    t.links.new(ramp.outputs["Color"], em.inputs["Color"])
    t.links.new(matematika(t, "MULTIPLY", fac, 0.6), em.inputs["Strength"])
    add = t.nodes.new("ShaderNodeAddShader")
    t.links.new(mix.outputs[0], add.inputs[0])
    t.links.new(em.outputs[0], add.inputs[1])
    t.links.new(add.outputs[0], out.inputs["Surface"])
    m["peran_tvc"] = "gelembung"
    return m


def bola(nama, r, kol, sub=3):
    me = bpy.data.meshes.new(nama)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    ob = bpy.data.objects.new(nama, me)
    kol.objects.link(ob)
    ob.data.materials.append(bahan_gelembung())
    ob.visible_shadow = False  # gelembung hampir bening: bayangan gelap di sepatu tidak wajar
    return ob


def gelembung():
    """Gelembung besar menyelubungi produk, meletus di frame `letus` (ketukan) + 16 percikan; gelembung kecil melayang
    di awal (sampai `akhir_s1`) lalu naik dari bawah podium mulai `naik_mulai` (posisi acak tetap, `seed`)."""
    g = konfig.K["gelembung"]
    C, F = konfig.C, g["letus"]
    k = koleksi("GELEMBUNG")
    besar = bola("GL_besar", g["r_besar"], k, 4)
    besar.location = C
    tampil(besar, [(1, F - 1)])
    kunci_vektor(besar, "scale", 1, (0.55,) * 3)
    kunci_vektor(besar, "scale", F - 8, (0.97, 1.03, 0.97))
    kunci_vektor(besar, "scale", F - 3, (1.0, 1.0, 1.0), "BACK", "EASE_IN")
    kunci_vektor(besar, "scale", F - 1, (1.14,) * 3)
    rng = np.random.default_rng(g["seed"])
    arah = rng.normal(size=(16, 3))
    arah /= np.linalg.norm(arah, axis=1, keepdims=True)
    for i, a in enumerate(arah):
        p = bola(f"GL_percik_{i:02d}", float(rng.uniform(0.004, 0.009)), k, 2)
        tampil(p, [(F, F + 14)])
        a = Vector(a)
        kunci_vektor(p, "location", F, C + a * 0.20, "EXPO", "EASE_OUT")
        kunci_vektor(p, "location", F + 14, C + a * 0.34 + Vector((0, 0, -0.03)))
        kunci_vektor(p, "scale", F, (1, 1, 1), "SINE", "EASE_IN")
        kunci_vektor(p, "scale", F + 14, (0.05,) * 3)
    s1, n0, n1 = g["akhir_s1"], g["naik_mulai"], g["naik_akhir"]
    for i in range(14):
        r = float(rng.uniform(0.006, 0.020))
        b = bola(f"GL_naik_{i:02d}", r, k, 3)
        x = float(rng.uniform(-0.08, 0.38))
        y = float(rng.choice([-1, 1]) * rng.uniform(0.08, 0.20))
        tampil(b, [(1, s1), (n0, n1)])
        # S1: melayang pelan; S4: naik dari bawah podium (tunda bertingkat), goyang x
        z1 = float(rng.uniform(-0.02, 0.20))
        kunci_vektor(b, "location", 1, (x, y, z1))
        kunci_vektor(b, "location", s1, (x + 0.01, y, z1 + 0.03))
        mulai = n0 + int(rng.integers(0, 30))
        kunci_vektor(b, "location", n0 - 1, (x, y, -0.12), "CONSTANT")
        kunci_vektor(b, "location", mulai, (x, y, -0.12), "SINE", "EASE_IN")
        kunci_vektor(b, "location", mulai + 25, (x + 0.012, y, 0.05))
        kunci_vektor(b, "location", mulai + 50, (x - 0.01, y, 0.24))
    return k


def podium():
    """Podium silinder gradasi (bawah -> atas), tepi atas bevel, coat tipis. Tampil hanya di rentang `tampil`."""
    p = konfig.K["podium"]
    me = bpy.data.meshes.new("podium")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=96, radius1=p["radius"], radius2=p["radius"], depth=p["tinggi"])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("podium", me)
    koleksi("BACKDROP").objects.link(ob)
    ob.location = (konfig.C.x, 0.0, p["atas_z"] - p["tinggi"] / 2)
    bv = ob.modifiers.new("bevel", "BEVEL")
    bv.width, bv.segments = 0.008, 4
    for pg in me.polygons:
        pg.use_smooth = True
    m = bpy.data.materials.new("podium")
    m.use_nodes = True
    t, b = m.node_tree, bsdf(m)
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(t.nodes.new("ShaderNodeTexCoord").outputs["Generated"], xyz.inputs[0])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*lin(p["warna"][0]), 1)
    ramp.color_ramp.elements[1].color = (*lin(p["warna"][1]), 1)
    t.links.new(xyz.outputs[2], ramp.inputs["Fac"])
    t.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Coat Weight"].default_value, b.inputs["Coat Roughness"].default_value = 0.4, 0.1
    me.materials.append(m)
    tampil(ob, [tuple(p["tampil"])])
    return ob
