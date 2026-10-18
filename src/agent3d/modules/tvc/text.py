"""Kinetic 3D text (extrude + bevel, emissive ink) parented to the text shot's camera. Content, per-ratio layout and
timing: tvc.toml [text]. Font: Blender's bundled Inter.woff2 (Bfont draws "1" like "I")."""
import math
import os

import bpy
from mathutils import Matrix

from ...core.camera import uv_to_local
from ...core.scene import collection
from ...core.color import lin
from . import config
from .key import key, key_vector, show


def ink_material(name="ink", hexa=None):
    hexa = hexa or config.K["text"]["ink"]
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
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
    """Inter (bundled with Blender, same on Windows and Linux). The default Bfont draws "1" like "I" (visual check)."""
    p = os.path.join(bpy.utils.system_resource("DATAFILES", path="fonts") or "", "Inter.woff2")
    f = next((f for f in bpy.data.fonts if f.filepath == p), None)
    if f is None and os.path.isfile(p):
        f = bpy.data.fonts.load(p)
    return f


def text_obj(name, contents, coll, extrude=0.06, thickness=0.0):
    """thickness = glyph contour offset (variable Inter loads as Regular; the offset makes the title bolder)."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = contents
    f = font()
    if f:
        cu.font = f
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    cu.size, cu.extrude, cu.bevel_depth, cu.bevel_resolution = 1.0, extrude, 0.012, 2
    cu.offset, cu.space_character = thickness, 1.0 + 2.5 * thickness  # offset widens glyphs: letter spacing follows
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    cu.materials.append(ink_material())
    return ob


def text(ratio, cam):
    """Title flips in + pops (BACK) at the start of the text shot, tagline word by word on eighth beats (6 frames),
    pop_word enlarged + tilted like a sticker, spec label eases in."""
    T = config.K["text"]
    k = collection("TEXT")
    sc = bpy.context.scene
    layout = T["layout"][ratio]
    distance = T["distance"]
    f0, _ = config.f_shot(T["shot"])
    out = {}

    def install(ob, u, v, width):
        bpy.context.view_layer.update()
        p, wf = uv_to_local(cam, u, v, distance)
        s = width * wf / max(ob.dimensions.x, 1e-6)
        ob.parent = cam
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.location, ob["scale"] = p, s
        return s

    j = text_obj("TX_title", T["title"], k, thickness=0.014)
    sj = install(j, *layout["title"])
    key_vector(j, "scale", 1, (0, 0, 0), "CONSTANT")
    key_vector(j, "scale", f0, (0, 0, 0), "BACK", "EASE_OUT")
    key_vector(j, "scale", f0 + 11, (sj,) * 3)
    key(j, "rotation_euler", f0, math.radians(75), "BACK", "EASE_OUT", 0)
    key(j, "rotation_euler", f0 + 13, 0.0, index=0)
    out["title"] = j
    # tagline word by word: total width = target width; spacing in font space widths
    word = T["tagline"].split()
    obs = [text_obj(f"TX_tag_{i}_{w.strip(',.')}", w, k, thickness=0.008) for i, w in enumerate(word)]
    bpy.context.view_layer.update()
    spacing = [T["spacing"]] * (len(obs) - 2) + [T["pop_spacing"]]
    total_width = sum(o.dimensions.x for o in obs) + sum(spacing)
    u, v, width = layout["tagline"]
    p0, wf = uv_to_local(cam, u, v, distance)
    s = width * wf / total_width
    x = p0.x - total_width * s / 2
    for i, o in enumerate(obs):
        w = o.dimensions.x
        o.parent = cam
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.location = (x + w * s / 2, p0.y, p0.z)
        x += (w + (spacing[i] if i < len(spacing) else 0)) * s
        f = f0 + 13 + 6 * i
        pop = o.name.endswith(T["pop_word"])
        key_vector(o, "scale", 1, (0, 0, 0), "CONSTANT")
        key_vector(o, "scale", f, (0, 0, 0), "BACK", "EASE_OUT")
        key_vector(o, "scale", f + 7, (s * (1.12 if pop else 1.0),) * 3)
        key(o, "location", f, p0.y - 0.012 * s * 4, "BACK", "EASE_OUT", 1)
        key(o, "location", f + 7, p0.y, index=1)
        if pop:
            key(o, "rotation_euler", f, math.radians(-14), "BACK", "EASE_OUT", 2)
            key(o, "rotation_euler", f + 9, math.radians(-5), index=2)
    out["tagline"] = obs
    lb = text_obj("TX_label", T["label"], k, extrude=0.0)
    sl = install(lb, *layout["label"])
    key_vector(lb, "scale", 1, (0, 0, 0), "CONSTANT")
    key_vector(lb, "scale", f0 + 44, (sl * 0.6,) * 3, "SINE", "EASE_OUT")
    key_vector(lb, "scale", f0 + 51, (sl,) * 3)
    out["label"] = lb
    for o in [j, lb] + obs:
        show(o, [(f0, config.END_FRAME)])
        o.visible_shadow = False
    sc.frame_set(sc.frame_start)
    return out
