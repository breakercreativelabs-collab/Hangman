"""TVC 'neon + wet' props (generic, everything from tvc.toml; used by the AM90 TVC "Cyber-Aero Genesis"):
wet floor (concrete + reflective puddles), neon rings (emissive torus), shock waves (emissive rings expanding on the
floor), ballistic water splash in slow motion (bullet time), plasma in the Air capsule cavity (spinning emissive arcs +
light), energy lines between exploded parts (thin emissive tubes following the XP_* part empties).
Non-generative: all geometry/materials/animation are built in Blender from config numbers. No LINEAR keys (TV-08).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector

from ...core.material import bsdf
from ...core.scene import fcurves, collection
from ...core.color import lin
from . import config
from .key import key, key_vector, show


def _emission(name, hexa, strong):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    t = m.node_tree
    for n in list(t.nodes):
        if n.type != "OUTPUT_MATERIAL":
            t.nodes.remove(n)
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value, em.inputs["Strength"].default_value = (*lin(hexa), 1), strong
    t.links.new(em.outputs[0], next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL").inputs["Surface"])
    m["tvc_role"] = "neon"
    return m


def _torus(name, R, r, coll, seg=96, seg2=12):
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
    me = bpy.data.meshes.new(name)
    me.from_pydata(V, [], F)
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def _spec_points(spec):
    return config.target(spec) if ("points" in spec or "relative_to_center" in spec) else config.C


def wet_floor():
    """Wet concrete floor plane: roughness from noise through a ramp (puddles at coarse[0] reflect the neon, concrete at
    coarse[1]), dark color with slight variation, fine concrete grain bump. [wet_floor] z, size, color, coarse, scale, show."""
    L = config.K["wet_floor"]
    me = bpy.data.meshes.new("wet_floor")
    s = L["size"]
    me.from_pydata([(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("wet_floor", me)
    collection("BACKDROP").objects.link(ob)
    ob.location = (config.C.x, 0.0, L["z"])
    m = bpy.data.materials.new("wet_floor")
    m.use_nodes = True
    t, b = m.node_tree, bsdf(m)
    coord = t.nodes.new("ShaderNodeTexCoord").outputs["Object"]
    n = t.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value, n.inputs["Detail"].default_value = L["scale"], 6.0
    t.links.new(coord, n.inputs["Vector"])
    ramp = t.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.45, 0.6
    ramp.color_ramp.elements[0].color = (L["coarse"][0],) * 3 + (1,)
    ramp.color_ramp.elements[1].color = (L["coarse"][1],) * 3 + (1,)
    t.links.new(n.outputs["Fac"], ramp.inputs["Fac"])
    t.links.new(ramp.outputs["Color"], b.inputs["Roughness"])
    b.inputs["Base Color"].default_value = (*lin(L["color"]), 1)
    b.inputs["Specular IOR Level"].default_value = 0.6
    grain = t.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = L["scale"] * 40
    t.links.new(coord, grain.inputs["Vector"])
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.15, 0.0005
    t.links.new(grain.outputs["Fac"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    me.materials.append(m)
    if L.get("show"):
        show(ob, [tuple(r) for r in L["show"]])
    return ob


def neon_rings():
    """[[neon_rings]]: name, points/relative_to_center, radius, thickness, rotation (deg), color, strong, show."""
    coll = collection("PROPS")
    out = []
    for c in config.K.get("neon_rings", []):
        ob = _torus(c["name"], c["radius"], c["thickness"], coll)
        ob.location = _spec_points(c)
        ob.rotation_euler = tuple(math.radians(a) for a in c.get("rotation", (90, 0, 0)))
        ob.data.materials.append(_emission(c["name"], c["color"], c["strong"]))
        ob.visible_shadow = False
        if c.get("show"):
            show(ob, [tuple(r) for r in c["show"]])
        out.append(ob)
    return out


def shock_wave():
    """[shock_wave]: points/relative_to_center (z = floor), frame, duration, n, pause (frames between rings), end_radius,
    thickness, color, strong. Each ring: a flat torus on the floor, scale 0.05 -> 1 (EXPO out), emission strong -> 0."""
    g = config.K["shock_wave"]
    coll = collection("PROPS")
    p = _spec_points(g)
    out = []
    for i in range(g["n"]):
        f0 = g["frame"] + i * g["pause"]
        f1 = f0 + g["duration"]
        ob = _torus(f"GK_{i}", g["end_radius"], g["thickness"], coll, 128, 8)
        ob.location = (p.x, p.y, p.z + 0.0008)
        ob.scale = (1, 1, 0.15)
        m = _emission(f"GK_{i}", g["color"], g["strong"])
        ob.data.materials.append(m)
        ob.visible_shadow = False
        show(ob, [(f0, f1)])
        key_vector(ob, "scale", f0, (0.05, 0.05, 0.15), "EXPO", "EASE_OUT")
        key_vector(ob, "scale", f1, (1.0, 1.0, 0.15))
        em = m.node_tree.nodes["Emission"].inputs["Strength"]
        key(em, "default_value", f0, g["strong"], "SINE", "EASE_IN")
        key(em, "default_value", f1, 0.0)
        out.append(ob)
    return out


def water_material():
    m = bpy.data.materials.get("water_drops") or bpy.data.materials.new("water_drops")
    m.use_nodes = True
    b = bsdf(m)
    b.inputs["Base Color"].default_value = (0.92, 0.97, 1.0, 1)
    b.inputs["Roughness"].default_value, b.inputs["IOR"].default_value = 0.02, 1.33
    b.inputs["Transmission Weight"].default_value = 1.0
    return m


def splash():
    """[splash]: points/relative_to_center, frame (impact), n, seed, r [min, max] m, speed [min, max] m/s,
    rise_angle [min, max] deg, gravity m/s2, slow (time factor after `fast` frames: bullet time), fast, end.
    Ballistic paths are computed in Python and keyed every 2 frames (BEZIER)."""
    g = config.K["splash"]
    coll = collection("PROPS")
    p0 = _spec_points(g)
    rng = np.random.default_rng(g["seed"])
    F, fps = g["frame"], config.FPS

    def t_sim(f):  # simulation time (s): normal for `fast` frames, then slowed down
        d = f - F
        return d / fps if d <= g["fast"] else (g["fast"] + (d - g["fast"]) * g["slow"]) / fps
    m = water_material()
    out = []
    for i in range(g["n"]):
        me = bpy.data.meshes.new(f"PC_{i:02d}")
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=float(rng.uniform(*g["r"])))
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        ob = bpy.data.objects.new(me.name, me)
        coll.objects.link(ob)
        me.materials.append(m)
        az = rng.uniform(0, 2 * math.pi)
        el = math.radians(rng.uniform(*g["rise_angle"]))
        v = rng.uniform(*g["speed"])
        vel = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el))) * v
        show(ob, [(F, g["end"])])
        for f in range(F, g["end"] + 1, 2):
            ts = t_sim(f)
            pos = p0 + vel * ts + Vector((0, 0, -0.5 * g["gravity"] * ts * ts))
            pos.z = max(pos.z, p0.z + 0.001)
            key_vector(ob, "location", f, tuple(pos))
            key_vector(ob, "scale", f, (1.0, 1.0, 1.0 + 0.6 * min(1.0, v * 0.1)))
        out.append(ob)
    return out


def plasma_capsule():
    """[plasma_capsule]: points (capsule cavity center, m), n, radius, thickness, color, strong, lamp (W), show [f0, f1],
    turn (rad over the show span). Arcs = thin tori with fixed random axes, spinning + pulsing (BEZIER/SINE)."""
    g = config.K["plasma_capsule"]
    coll = collection("PROPS")
    p = Vector(g["points"])
    rng = np.random.default_rng(g.get("seed", 3))
    f0, f1 = g["show"]
    out = []
    parent = bpy.data.objects.get(g.get("parent", ""))
    for i in range(g["n"]):
        ob = _torus(f"PL_{i}", g["radius"] * float(rng.uniform(0.7, 1.0)), g["thickness"], coll, 64, 6)
        ob.location = p + Vector((float(rng.uniform(-1, 1)) * g["scatter"], 0, 0))
        ob.scale = (1.0, 0.45, 1.0)
        ob.data.materials.append(_emission(f"PL_{i}", g["color"], g["strong"]))
        ob.visible_shadow = False
        if parent:
            ob.parent = parent
        show(ob, [(f0, f1)])
        r0 = [float(x) for x in rng.uniform(0, 2 * math.pi, 3)]
        key_vector(ob, "rotation_euler", f0, r0, "SINE", "EASE_IN_OUT")
        key_vector(ob, "rotation_euler", f1, (r0[0] + g["turn"], r0[1] - 0.6 * g["turn"], r0[2]))
        out.append(ob)
    d = bpy.data.lights.new("PL_lamp", "POINT")
    d.energy, d.shadow_soft_size, d.color = g["lamp"], 0.003, tuple(lin(g["color"]))
    L = bpy.data.objects.new("PL_lamp", d)
    collection("LIGHTS").objects.link(L)
    L.location = p
    if parent:
        L.parent = parent
    return out


def energy_line():
    """[energy_line]: pair [[part_a, part_b]], part_points {part: [x, y, z] m (model points)}, color, strong,
    thickness (m), show [f0, f1]. Thin tubes between part points in world space, keyed every 3 frames to follow the
    XP_<part> empty animation (exploded)."""
    g = config.K["energy_line"]
    coll = collection("PROPS")
    sc = bpy.context.scene
    f0, f1 = g["show"]
    m = _emission("energy_line", g["color"], g["strong"])
    out = []
    for i, (a, b) in enumerate(g["pair"]):
        me = bpy.data.meshes.new(f"GE_{i}")
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=False, segments=8, radius1=g["thickness"], radius2=g["thickness"], depth=1.0)
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(me.name, me)
        coll.objects.link(ob)
        me.materials.append(m)
        ob.visible_shadow = False
        ob.rotation_mode = "QUATERNION"
        show(ob, [(f0, f1)])
        ea, eb = bpy.data.objects["XP_" + a], bpy.data.objects["XP_" + b]
        pa, pb = Vector(g["part_points"][a]), Vector(g["part_points"][b])
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


def floor_contact():
    """[contact] frame, z: the lowest product point at `frame` is placed exactly at floor z. The offset is added to the
    TURNTABLE z location keys from `frame` up to the next shot (measured from geometry, not guessed). Returns the
    offset (m) for the report."""
    g = config.K.get("contact")
    if not g:
        return None
    sc = bpy.context.scene
    sc.frame_set(g["frame"])
    dg = bpy.context.evaluated_depsgraph_get()
    zmin = min((o.evaluated_get(dg).matrix_world @ v.co).z for o in collection("PRODUCT").all_objects
               if o.type == "MESH" for v in o.evaluated_get(dg).data.vertices)
    dz = g["z"] - zmin
    name, f0, f1 = next(s for s in config.shot_span() if s[1] <= g["frame"] <= s[2])
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
    bpy.data.objects["CONTROL"]["contact_dz_mm"] = round(dz * 1000, 3)
    return dz


PROPS_NEON = {"wet_floor": wet_floor, "neon_rings": neon_rings, "shock_wave": shock_wave,
              "splash": splash, "plasma_capsule": plasma_capsule, "energy_line": energy_line}
