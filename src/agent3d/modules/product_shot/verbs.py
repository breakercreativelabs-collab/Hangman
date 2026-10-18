"""Product shot verbs (Blender 5.2 LTS). Python computes, Claude decides.

Verbs: import_product · normalize · studio_lighting (light.py) · turntable · material_variant ·
render_variants (framing.py). .blend standard and product hierarchy: agent3d.core.scene.
Convention: meters, floor z = 0, product front side faces -Y, camera in the -Y direction.
"""
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ...core import color as W
from ...core.scene import control, fcurves, collection, root, product_points
from . import sample_products, specification
from .make_material import product_material

RATIO = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}  # final resolution (laptop)
COLOR = {"red": "#C8102E", "blue": "#1F4E9C", "green": "#2E7D32", "black": "#1A1A1A",
         "white": "#F2F2F2", "yellow": "#F2C230", "purple": "#5E2A84", "orange": "#E8641B"}
EASING = {  # name -> Blender (interpolation, easing). "linear" is only for negative QC tests.
    "ease_in_out": ("SINE", "EASE_IN_OUT"),
    "cubic": ("CUBIC", "EASE_IN_OUT"),
    "expo": ("EXPO", "EASE_IN_OUT"),
    "bezier": ("BEZIER", "AUTO"),
    "linear": ("LINEAR", "AUTO"),
}


def color_to_linear(h):
    """Palette name (COLOR) or '#RRGGBB' -> linear."""
    return W.hex_to_linear(COLOR.get(h, h))


# ---------------- VERB 1: import_product ----------------
def import_product(source):
    """Put the product into the PRODUCT collection under PRODUCT_ROOT.
    source: "sample:bottle" / "sample:can" (procedural test product) or a .glb/.gltf/.obj/.fbx/.stl/.blend path."""
    pk, r = collection("PRODUCT"), root()
    before = set(bpy.data.objects)
    if source.startswith("sample:"):
        name = source.split(":", 1)[1]
        sample_products.build_product(name, pk, product_material(name))
        s = specification.SPEC[name]
        r["spec_height_mm"] = specification.total_height_mm(name)
        for k, v in specification.spec_qc(name).items():  # round: diameter; box/flat: width + thickness
            r[k] = v
        r["spec_source"] = s["source"]
        r["color_points"] = specification.color_points(name)
        r["logo_u"], r["logo_z"] = specification.logo(name)
    else:
        ext = os.path.splitext(source)[1].lower()
        if not os.path.isfile(source):
            raise FileNotFoundError(source)
        if ext in (".glb", ".gltf"):
            bpy.ops.import_scene.gltf(filepath=source)
        elif ext == ".obj":
            bpy.ops.wm.obj_import(filepath=source)
        elif ext == ".fbx":
            bpy.ops.import_scene.fbx(filepath=source)
        elif ext == ".stl":
            bpy.ops.wm.stl_import(filepath=source)
        elif ext == ".blend":
            with bpy.data.libraries.load(source) as (src, dst):
                dst.objects = list(src.objects)
            for o in dst.objects:
                if o is not None and o.type == "MESH":
                    pk.objects.link(o)
        else:
            raise ValueError(f"unsupported format: {ext}")
        name = os.path.splitext(os.path.basename(source))[0]
    new = [o for o in bpy.data.objects if o not in before and o.type in ("MESH", "EMPTY")]
    for o in [o for o in bpy.data.objects if o not in before and o not in new]:
        bpy.data.objects.remove(o)  # default cameras/lights from the imported file are dropped: our standard is used
    for o in new:
        for k in list(o.users_collection):
            if k != pk:
                k.objects.unlink(o)
        if pk not in o.users_collection:
            pk.objects.link(o)
        if o.parent is None:
            mw = o.matrix_world.copy()
            o.parent = r
            o.matrix_world = mw
    r["source"] = source
    control()["product"] = name
    bpy.context.view_layer.update()
    return r


# ---------------- VERB 2: normalize ----------------
UNIT = {"m": 1.0, "cm": 0.01, "mm": 0.001, "in": 0.0254}
ROT_FRONT = {"-Y": 0.0, "+X": -90.0, "+Y": 180.0, "-X": 90.0}
ROT_TOP = {"+Z": None, "+Y": ("X", 90.0), "-Y": ("X", -90.0)}


def _apply(T):
    """Apply T (world space) to every direct child of PRODUCT_ROOT; scale is baked into the mesh."""
    r = root()
    for c in r.children:
        c.matrix_world = T @ c.matrix_world
    bpy.context.view_layer.update()
    for c in r.children_recursive:
        if c.type == "MESH" and not c.children and c.data.users == 1:
            s = c.matrix_basis.to_scale()
            if (s - Vector((1, 1, 1))).length > 1e-6:
                c.data.transform(Matrix.Diagonal((*s, 1.0)))
                c.scale = (1, 1, 1)
    bpy.context.view_layer.update()


def normalize(unit="m", height_m=None, front="-Y", top="+Z"):
    """Real-world scale, origin at bottom center, standing on the floor (z=0), front facing -Y.
    unit: source file unit (m/cm/mm/in). height_m: force a height (if the source unit is unclear).
    front/top: front & top axes in the source file."""
    r = root()
    tt = r.parent
    tt.matrix_world = Matrix.Identity(4)
    r.matrix_parent_inverse = Matrix.Identity(4)
    r.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    R = Matrix.Identity(4)
    if ROT_TOP[top]:
        R = Matrix.Rotation(math.radians(ROT_TOP[top][1]), 4, ROT_TOP[top][0])
    R = Matrix.Rotation(math.radians(ROT_FRONT[front]), 4, "Z") @ R
    _apply(R @ Matrix.Scale(UNIT[unit], 4))
    if height_m:
        p = product_points()
        _apply(Matrix.Scale(height_m / (p[:, 2].max() - p[:, 2].min()), 4))
    p = product_points()
    lo, hi = p.min(0), p.max(0)
    _apply(Matrix.Translation(Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))))
    p = product_points()
    dim = (p.max(0) - p.min(0)) * 1000
    r["dimension_mm"] = dim_mm = [round(float(d), 2) for d in dim]
    return {"dimension_mm": dim_mm, "z_min_mm": round(float(p[:, 2].min()) * 1000, 3)}


def product_size():
    p = product_points()
    return float(p[:, 2].max()), float(np.hypot(p[:, 0], p[:, 1]).max())  # height, radius XY


# ---------------- VERB 4: turntable ----------------
def turntable(duration=6.0, easing="ease_in_out", fps=25, turn=1):
    """Rotate the product 360 degrees x turn around Z over `duration` seconds, ending facing front again."""
    sc, tt = bpy.context.scene, root().parent
    sc.render.fps, sc.render.fps_base = fps, 1.0
    sc.frame_start, sc.frame_end = 1, 1 + round(duration * fps)
    tt.animation_data_clear()
    tt.rotation_euler = (0, 0, 0)
    tt.keyframe_insert("rotation_euler", index=2, frame=sc.frame_start)
    tt.rotation_euler.z = 2 * math.pi * turn
    tt.keyframe_insert("rotation_euler", index=2, frame=sc.frame_end)
    interp, ease = EASING[easing]
    for fc in fcurves(tt):
        for k in fc.keyframe_points:
            k.interpolation, k.easing = interp, ease
    c = control()
    c["duration_seconds"], c["easing"], c["fps"] = float(duration), easing, fps
    sc.frame_set(sc.frame_start)
    return (sc.frame_start, sc.frame_end)


# ---------------- VERB 5: material_variant ----------------
def material_variant(color):
    """Change the label variant color (name in COLOR or hex '#RRGGBB'). Goes through CONTROL['variant_color'] -> driver."""
    hexa = COLOR.get(color, color)
    lin = color_to_linear(hexa)
    c = control()
    c["variant_color"], c["hex_color"] = lin, hexa
    c.update_tag()  # changing a custom property from Python does not trigger driver evaluation
    count = 0
    for m in bpy.data.materials:  # also set directly, so it is correct even before drivers evaluate
        n = m.node_tree.nodes.get("COLOR_VARIANT") if m.node_tree else None
        if n:
            n.outputs[0].default_value = (*lin, 1)
            count += 1
    c["variant_material"] = count
    if not count:  # do not fail silently: client models need an RGB node named COLOR_VARIANT in the label material
        print("WARNING material_variant: no 'COLOR_VARIANT' node; product color NOT changed")
    bpy.context.view_layer.update()
    return hexa
