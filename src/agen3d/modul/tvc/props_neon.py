"""Props TVC 'neon + basah' (generik, semua dari tvc.toml; dipakai TVC AM90 "Cyber-Aero Genesis"):
lantai basah (beton + genangan memantul), cincin neon (torus emisi), gelombang kejut (cincin emisi melebar di lantai),
percikan air balistik dengan gerak lambat (bullet time), plasma di rongga kapsul Air (lengkung emisi berputar + lampu),
garis energi antar bagian exploded (tabung emisi tipis yang mengikuti empty XP_* bagian).
Non-generatif: semua geometri/material/animasi dibuat di Blender dari angka konfigurasi. Kunci tanpa LINEAR (TV-08).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from ...inti.material import bsdf
from ...inti.scene import fcurves, koleksi
from ...inti.warna import lin
from . import konfig
from .kunci import kunci, kunci_vektor, tampil


def _emisi(nama, hexa, kuat):
    m = bpy.data.materials.new(nama)
    m.use_nodes = True
    t = m.node_tree
    for n in list(t.nodes):
        if n.type != "OUTPUT_MATERIAL":
            t.nodes.remove(n)
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value, em.inputs["Strength"].default_value = (*lin(hexa), 1), kuat
    t.links.new(em.outputs[0], next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL").inputs["Surface"])
    m["peran_tvc"] = "neon"
    return m


def _torus(nama, R, r, kol, seg=96, seg2=12):
    V, F = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        for j in range(seg2):
            b = 2 * math.pi * j / seg2
            V.append(((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b)))
    for i in range(seg):
        for j in range(seg2):
            F.append((i * seg2 + j, ((i + 1) % seg) * seg2 + j, ((i + 1) % seg) * seg2 + (j + 1) % seg2,
                      i * seg2 + (j + 1) % seg2))
    me = bpy.data.meshes.new(nama)
    me.from_pydata(V, [], F)
    me.shade_smooth()
    ob = bpy.data.objects.new(nama, me)
    kol.objects.link(ob)
    return ob


def _titik_spek(spek):
    return konfig.target(spek) if ("titik" in spek or "relatif_pusat" in spek) else konfig.C


def lantai_basah():
    """Bidang lantai beton basah: kekasaran dari noise lewat ramp (genangan kasar[0] memantulkan neon, beton kasar[1]),
    warna gelap sedikit bervariasi, bump butir beton halus. [lantai_basah] z, ukuran, warna, kasar, skala, tampil."""
    L = konfig.K["lantai_basah"]
    me = bpy.data.meshes.new("lantai_basah")
    s = L["ukuran"]
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("lantai_basah", me)
    koleksi("BACKDROP").objects.link(ob)
    ob.location = (konfig.C.x, 0.0, L["z"])
    m = bpy.data.materials.new("lantai_basah")
    m.use_nodes = True
    t, b = m.node_tree, bsdf(m)
    koord = t.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    n = t.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value, n.inputs["Detail"].default_value = L["skala"], 6.0
    t.links.new(koord, n.inputs["Vector"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.45, 0.6
    ramp.color_ramp.elements[0].color = (L["kasar"][0],) * 3 + (1,)
    ramp.color_ramp.elements[1].color = (L["kasar"][1],) * 3 + (1,)
    t.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    t.links.new(ramp.outputs["Color"], b.inputs["Roughness"])
    b.inputs["Base Color"].default_value = (*lin(L["warna"]), 1)
    b.inputs["Specular IOR Level"].default_value = 0.6
    butir = t.nodes.new("ShaderNodeTexNoise")
    butir.inputs["Scale"].default_value = L["skala"] * 40
    t.links.new(koord, butir.inputs["Vector"])
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.15, 0.0005
    t.links.new(butir.outputs["Fac"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    me.materials.append(m)
    if L.get("tampil"):
        tampil(ob, [tuple(r) for r in L["tampil"]])
    return ob


def cincin_neon():
    """[[cincin_neon]]: nama, titik/relatif_pusat, radius, tebal, rotasi (deg), warna, kuat, tampil."""
    kol = koleksi("PROPS")
    out = []
    for c in konfig.K.get("cincin_neon", []):
        ob = _torus(c["nama"], c["radius"], c["tebal"], kol)
        ob.location = _titik_spek(c)
        ob.rotation_euler = tuple(math.radians(a) for a in c.get("rotasi", (90, 0, 0)))
        ob.data.materials.append(_emisi(c["nama"], c["warna"], c["kuat"]))
        ob.visible_shadow = False
        if c.get("tampil"):
            tampil(ob, [tuple(r) for r in c["tampil"]])
        out.append(ob)
    return out


def gelombang_kejut():
    """[gelombang_kejut]: titik/relatif_pusat (z = lantai), frame, durasi, n, jeda (frame antar cincin), radius_akhir,
    tebal, warna, kuat. Tiap cincin: torus pipih di lantai, skala 0,05 -> 1 (EXPO keluar), emisi kuat -> 0."""
    g = konfig.K["gelombang_kejut"]
    kol = koleksi("PROPS")
    p = _titik_spek(g)
    out = []
    for i in range(g["n"]):
        f0 = g["frame"] + i * g["jeda"]
        f1 = f0 + g["durasi"]
        ob = _torus(f"GK_{i}", g["radius_akhir"], g["tebal"], kol, 128, 8)
        ob.location = (p.x, p.y, p.z + 0.0008)
        ob.scale = (1, 1, 0.15)
        m = _emisi(f"GK_{i}", g["warna"], g["kuat"])
        ob.data.materials.append(m)
        ob.visible_shadow = False
        tampil(ob, [(f0, f1)])
        kunci_vektor(ob, "scale", f0, (0.05, 0.05, 0.15), "EXPO", "EASE_OUT")
        kunci_vektor(ob, "scale", f1, (1.0, 1.0, 0.15))
        em = m.node_tree.nodes["Emission"].inputs["Strength"]
        kunci(em, "default_value", f0, g["kuat"], "SINE", "EASE_IN")
        kunci(em, "default_value", f1, 0.0)
        out.append(ob)
    return out


def bahan_air():
    m = bpy.data.materials.get("air_tetes") or bpy.data.materials.new("air_tetes")
    m.use_nodes = True
    b = bsdf(m)
    b.inputs["Base Color"].default_value = (0.92, 0.97, 1.0, 1)
    b.inputs["Roughness"].default_value, b.inputs["IOR"].default_value = 0.02, 1.33
    b.inputs["Transmission Weight"].default_value = 1.0
    return m


def percikan():
    """[percikan]: titik/relatif_pusat, frame (benturan), n, seed, r [min, maks] m, kecepatan [min, maks] m/s,
    sudut_naik [min, maks] deg, gravitasi m/s2, lambat (faktor waktu setelah `cepat` frame: bullet time), cepat, akhir.
    Lintasan balistik dihitung di Python, dikunci tiap 2 frame (BEZIER)."""
    g = konfig.K["percikan"]
    kol = koleksi("PROPS")
    p0 = _titik_spek(g)
    rng = np.random.default_rng(g["seed"])
    F, fps = g["frame"], konfig.FPS

    def t_sim(f):  # waktu simulasi (s): normal sampai `cepat` frame, lalu diperlambat
        d = f - F
        return d / fps if d <= g["cepat"] else (g["cepat"] + (d - g["cepat"]) * g["lambat"]) / fps
    m = bahan_air()
    out = []
    for i in range(g["n"]):
        me = bpy.data.meshes.new(f"PC_{i:02d}")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=float(rng.uniform(*g["r"])))
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        ob = bpy.data.objects.new(me.name, me)
        kol.objects.link(ob)
        me.materials.append(m)
        az = rng.uniform(0, 2 * math.pi)
        el = math.radians(rng.uniform(*g["sudut_naik"]))
        v = rng.uniform(*g["kecepatan"])
        vel = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el))) * v
        tampil(ob, [(F, g["akhir"])])
        for f in range(F, g["akhir"] + 1, 2):
            ts = t_sim(f)
            pos = p0 + vel * ts + Vector((0, 0, -0.5 * g["gravitasi"] * ts * ts))
            pos.z = max(pos.z, p0.z + 0.001)
            kunci_vektor(ob, "location", f, tuple(pos))
            kunci_vektor(ob, "scale", f, (1.0, 1.0, 1.0 + 0.6 * min(1.0, v * 0.1)))
        out.append(ob)
    return out


def plasma_kapsul():
    """[plasma_kapsul]: titik (pusat rongga kapsul, m), n, radius, tebal, warna, kuat, lampu (W), tampil [f0, f1],
    putaran (rad selama tampil). Lengkung = torus tipis dengan sumbu acak tetap, berputar + berdenyut (BEZIER/SINE)."""
    g = konfig.K["plasma_kapsul"]
    kol = koleksi("PROPS")
    p = Vector(g["titik"])
    rng = np.random.default_rng(g.get("seed", 3))
    f0, f1 = g["tampil"]
    out = []
    induk = bpy.data.objects.get(g.get("induk", ""))
    for i in range(g["n"]):
        ob = _torus(f"PL_{i}", g["radius"] * float(rng.uniform(0.7, 1.0)), g["tebal"], kol, 64, 6)
        ob.location = p + Vector((float(rng.uniform(-1, 1)) * g["sebar"], 0, 0))
        ob.scale = (1.0, 0.45, 1.0)
        ob.data.materials.append(_emisi(f"PL_{i}", g["warna"], g["kuat"]))
        ob.visible_shadow = False
        if induk:
            ob.parent = induk
        tampil(ob, [(f0, f1)])
        r0 = [float(x) for x in rng.uniform(0, 2 * math.pi, 3)]
        kunci_vektor(ob, "rotation_euler", f0, r0, "SINE", "EASE_IN_OUT")
        kunci_vektor(ob, "rotation_euler", f1, (r0[0] + g["putaran"], r0[1] - 0.6 * g["putaran"], r0[2]))
        out.append(ob)
    d = bpy.data.lights.new("PL_lampu", "POINT")
    d.energy, d.shadow_soft_size, d.color = g["lampu"], 0.003, tuple(lin(g["warna"]))
    L = bpy.data.objects.new("PL_lampu", d)
    koleksi("LIGHTS").objects.link(L)
    L.location = p
    if induk:
        L.parent = induk
    return out


def garis_energi():
    """[garis_energi]: pasangan [[bagian_a, bagian_b]], titik_bagian {bagian: [x, y, z] m (titik model)}, warna, kuat,
    tebal (m), tampil [f0, f1]. Tabung tipis antar titik bagian di ruang dunia, dikunci tiap 3 frame mengikuti
    animasi empty XP_<bagian> (exploded)."""
    g = konfig.K["garis_energi"]
    kol = koleksi("PROPS")
    sc = bpy.context.scene
    f0, f1 = g["tampil"]
    m = _emisi("garis_energi", g["warna"], g["kuat"])
    out = []
    for i, (a, b) in enumerate(g["pasangan"]):
        me = bpy.data.meshes.new(f"GE_{i}")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=g["tebal"], radius2=g["tebal"], depth=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(me.name, me)
        kol.objects.link(ob)
        me.materials.append(m)
        ob.visible_shadow = False
        ob.rotation_mode = "QUATERNION"
        tampil(ob, [(f0, f1)])
        ea, eb = bpy.data.objects["XP_" + a], bpy.data.objects["XP_" + b]
        pa, pb = Vector(g["titik_bagian"][a]), Vector(g["titik_bagian"][b])
        for f in list(range(f0, f1 + 1, 3)) + [f1]:
            sc.frame_set(f)
            A, B = ea.matrix_world @ pa, eb.matrix_world @ pb
            d = B - A
            ob.location = (A + B) / 2
            ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(d.normalized())
            ob.scale = (1, 1, max(d.length, 1e-4))
            for path in ("location", "rotation_quaternion", "scale"):
                ob.keyframe_insert(path, frame=f)
        out.append(ob)
    sc.frame_set(1)
    return out


def kontak_lantai():
    """[kontak] frame, z: titik produk terendah di `frame` ditempatkan tepat di z lantai. Selisih ditambahkan ke kunci
    lokasi z TURNTABLE dari `frame` sampai sebelum shot berikutnya (angka dari geometri, bukan tebakan). Mengembalikan
    selisih (m) untuk laporan."""
    g = konfig.K.get("kontak")
    if not g:
        return None
    sc = bpy.context.scene
    sc.frame_set(g["frame"])
    dg = bpy.context.evaluated_depsgraph_get()
    zmin = min((o.evaluated_get(dg).matrix_world @ v.co).z for o in koleksi("PRODUCT").all_objects
               if o.type == "MESH" for v in o.evaluated_get(dg).data.vertices)
    dz = g["z"] - zmin
    nama, f0, f1 = next(s for s in konfig.rentang_shot() if s[1] <= g["frame"] <= s[2])
    tt = bpy.data.objects["TURNTABLE"]
    for fc in fcurves(tt):
        if fc.data_path.endswith("location") and fc.array_index == 2:
            for k in fc.keyframe_points:
                if g["frame"] <= k.co.x <= f1:
                    k.co.y += dz
                    k.handle_left.y += dz
                    k.handle_right.y += dz
            fc.update()
    sc.frame_set(1)
    bpy.data.objects["CONTROL"]["kontak_dz_mm"] = round(dz * 1000, 3)
    return dz


PROPS_NEON = {"lantai_basah": lantai_basah, "cincin_neon": cincin_neon, "gelombang_kejut": gelombang_kejut,
              "percikan": percikan, "plasma_kapsul": plasma_kapsul, "garis_energi": garis_energi}
