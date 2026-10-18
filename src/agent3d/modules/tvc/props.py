"""TVC props: pastel thin-film soap bubbles (burst + splash + rising) and a gradient podium."""
import bmesh
import bpy
import numpy as np
from mathutils import Vector

from ...core.material import bsdf, math_node
from ...core.scene import collection
from ...core.color import lin
from . import config
from .key import key_vector, show


def bubble_material():
    """Pastel thin-film soap bubble: transparent in the middle, thin-film interference (Principled Thin Film, random
    thickness 280-720 nm per object) stronger toward the rim (Layer Weight facing), slight pastel emission at the rim."""
    m = bpy.data.materials.get("bubble")
    if m:
        return m
    m = bpy.data.materials.new("bubble")
    m.use_nodes = True
    t = m.node_tree
    for n in list(t.nodes):
        if n.type != "OUTPUT_MATERIAL":
            t.nodes.remove(n)
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    info = t.nodes.new("ShaderNodeObjectInfo")
    thickness = math_node(t, "ADD", math_node(t, "MULTIPLY", info.outputs["Random"], 440.0), 280.0)
    b = t.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value, b.inputs["IOR"].default_value = 0.02, 1.33
    b.inputs["Specular IOR Level"].default_value = 1.0
    t.links.new(thickness, b.inputs["Thin Film Thickness"])
    b.inputs["Thin Film IOR"].default_value = 1.33
    tr = t.nodes.new("ShaderNodeBsdfTransparent")
    lw = t.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    fac = math_node(t, "POWER", lw.outputs["Facing"], 2.2)
    mix = t.nodes.new("ShaderNodeMixShader")
    t.links.new(fac, mix.inputs[0])
    t.links.new(tr.outputs[0], mix.inputs[1])
    t.links.new(b.outputs[0], mix.inputs[2])
    ramp = t.nodes.new("ShaderNodeValToRGB")  # pastel rim color per bubble
    el = ramp.color_ramp.elements
    for i, (pos, h) in enumerate(config.K["bubble"]["edge_color"]):
        e = el[i] if i < len(el) else el.new(pos)
        e.position, e.color = pos, (*lin(h), 1)
    t.links.new(info.outputs["Random"], ramp.inputs["Fac"])
    em = t.nodes.new("ShaderNodeEmission")
    t.links.new(ramp.outputs["Color"], em.inputs["Color"])
    t.links.new(math_node(t, "MULTIPLY", fac, 0.6), em.inputs["Strength"])
    add = t.nodes.new("ShaderNodeAddShader")
    t.links.new(mix.outputs[0], add.inputs[0])
    t.links.new(em.outputs[0], add.inputs[1])
    t.links.new(add.outputs[0], out.inputs["Surface"])
    m["tvc_role"] = "bubble"
    return m


def sphere(name, r, coll, sub=3):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.data.materials.append(bubble_material())
    ob.visible_shadow = False  # bubbles are nearly clear: a dark shadow on the shoe looks wrong
    return ob


def bubble():
    """A large bubble wraps the product and bursts at frame `burst` (on the beat) + 16 droplets; small bubbles float
    at the start (until `s1_end`), then rise from below the podium from `rise_start` (fixed random positions, `seed`)."""
    g = config.K["bubble"]
    C, F = config.C, g["burst"]
    k = collection("GELEMBUNG")
    large = sphere("GL_large", g["r_large"], k, 4)
    large.location = C
    show(large, [(1, F - 1)])
    key_vector(large, "scale", 1, (0.55,) * 3)
    key_vector(large, "scale", F - 8, (0.97, 1.03, 0.97))
    key_vector(large, "scale", F - 3, (1.0, 1.0, 1.0), "BACK", "EASE_IN")
    key_vector(large, "scale", F - 1, (1.14,) * 3)
    rng = np.random.default_rng(g["seed"])
    direction = rng.normal(size=(16, 3))
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    for i, a in enumerate(direction):
        p = sphere(f"GL_percik_{i:02d}", float(rng.uniform(0.004, 0.009)), k, 2)
        show(p, [(F, F + 14)])
        a = Vector(a)
        key_vector(p, "location", F, C + a * 0.20, "EXPO", "EASE_OUT")
        key_vector(p, "location", F + 14, C + a * 0.34 + Vector((0, 0, -0.03)))
        key_vector(p, "scale", F, (1, 1, 1), "SINE", "EASE_IN")
        key_vector(p, "scale", F + 14, (0.05,) * 3)
    s1, n0, n1 = g["s1_end"], g["rise_start"], g["rise_end"]
    for i in range(14):
        r = float(rng.uniform(0.006, 0.020))
        b = sphere(f"GL_rise_{i:02d}", r, k, 3)
        x = float(rng.uniform(-0.08, 0.38))
        y = float(rng.choice([-1, 1]) * rng.uniform(0.08, 0.20))
        show(b, [(1, s1), (n0, n1)])
        # S1: slow float; S4: rise from below the podium (staggered delay), x wobble
        z1 = float(rng.uniform(-0.02, 0.20))
        key_vector(b, "location", 1, (x, y, z1))
        key_vector(b, "location", s1, (x + 0.01, y, z1 + 0.03))
        start = n0 + int(rng.integers(0, 30))
        key_vector(b, "location", n0 - 1, (x, y, -0.12), "CONSTANT")
        key_vector(b, "location", start, (x, y, -0.12), "SINE", "EASE_IN")
        key_vector(b, "location", start + 25, (x + 0.012, y, 0.05))
        key_vector(b, "location", start + 50, (x - 0.01, y, 0.24))
    return k


def podium():
    """Gradient cylinder podium (bottom -> top), beveled top edge, thin coat. Visible only within the `show` span."""
    p = config.K["podium"]
    me = bpy.data.meshes.new("podium")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=96, radius1=p["radius"], radius2=p["radius"], depth=p["height"])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("podium", me)
    collection("BACKDROP").objects.link(ob)
    ob.location = (config.C.x, 0.0, p["top_z"] - p["height"] / 2)
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
    ramp.color_ramp.elements[0].color = (*lin(p["color"][0]), 1)
    ramp.color_ramp.elements[1].color = (*lin(p["color"][1]), 1)
    t.links.new(xyz.outputs[2], ramp.inputs["Fac"])
    t.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.35
    b.inputs["Coat Weight"].default_value, b.inputs["Coat Roughness"].default_value = 0.4, 0.1
    me.materials.append(m)
    show(ob, [tuple(p["show"])])
    return ob
