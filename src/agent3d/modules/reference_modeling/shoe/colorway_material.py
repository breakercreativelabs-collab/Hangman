"""GENERIC shoe recipe M3: colorway materials from the project palette [palette.role] = [hex, source, kind] (Task 11).

Material kinds (one function per kind, not per shoe): leather, striped_leather (horizontal ribs, e.g. AM90 eyestay),
tpu (badge/tab, glossy), foam, striped_foam (striped painted cassette), mesh, rubber, capsule, lace, soft, suede.
Hex [F-photo] = median of the bright panel pixels in the photo (extraction/classes.py bright_color). Materials store
`role` + `hex_p3` like p3_material (read by AM-15/AM-18). Projects without `kind` (AM1) keep using p3_material (data.palette_typed).
"""
import bpy
import numpy as np

from ....core.material import make_material, bsdf, math_node
from ....core.color import lin
from . import data
from .p3_material import _bump, _facing_down, _coord, _noise, _mark, _color_variation, foam, capsule, rubber, soft, \
    knit_mesh, suede, woven_lace

RIB = {"striped_leather": (1.6, 0.25), "striped_foam": (2.5, 0.6)}  # (pitch mm, bump strength) [D] from macro photos
CAPSULE_TINT = 0.7  # [D] the capsule film is much clearer than the color seen through the window


def leather(role, hexa):
    """Smooth synthetic leather: roughness 0.42, light sheen, thin coat (new-leather gloss), fine 0.15 mm grain."""
    m = make_material(role, lin(hexa), 0.42)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value, b.inputs["Coat Weight"].default_value = 0.15, 0.12
    t.links.new(_color_variation(t, b, hexa, 0.03, 60.0), b.inputs["Base Color"])
    _bump(t, b, _noise(t, 3200.0, 5.0, 0.65).outputs["Fac"], 0.18, 0.00015)
    return _mark(m, role, hexa)


def tpu(role, hexa):
    """Molded TPU (badge, heel tab): roughness 0.22 + coat 0.4, almost no texture."""
    m = make_material(role, lin(hexa), 0.22)
    b = bsdf(m)
    b.inputs["Coat Weight"].default_value, b.inputs["Coat Roughness"].default_value = 0.4, 0.15
    return _mark(m, role, hexa)


def _rib(m, pitch_mm, strong):
    """Horizontal ribs (grooves parallel to the ground) via a Wave BANDS bump along object Z, period pitch_mm."""
    t, b = m.node_tree, bsdf(m)
    w = t.nodes.new("ShaderNodeTexWave")
    w.wave_type, w.bands_direction, w.wave_profile = "BANDS", "Z", "SIN"
    w.inputs["Scale"].default_value = 1000.0 / pitch_mm  # object coordinates in meters
    t.links.new(_coord(t), w.inputs["Vector"])
    _bump(t, b, w.outputs["Fac"], strong, 0.0004)
    return m


def photo_rubber(role, hexa, tread="waffle"):
    """Outsole rubber + tread from the sole photo GROOVE MAP (derived data, extraction/tread.py): bump only on down-facing
    faces, grooves slightly darker. Non-default tread (plain/wave/voronoi) = AM1 recipe (negative test AM-07)."""
    if tread != "waffle" or data.TREAD is None:
        return rubber(role, hexa, tread)
    m = make_material(role, lin(hexa), 0.8)
    t, b = m.node_tree, bsdf(m)
    info = data.TREAD["grooves"]
    img = bpy.data.images.load(data.path_data("tread_grooves"), check_existing=True)
    img.colorspace_settings.name = "Non-Color"
    tex = t.nodes.new("ShaderNodeTexImage")
    tex.image, tex.extension, tex.interpolation = img, "CLIP", "Linear"
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(_coord(t), xyz.inputs[0])
    p = np.array(data.DATA["sole_plan_profile"], float)
    c = (p[:, 1].min() + p[:, 2].max() + data.PX) / 2  # plan_y convention: model Y = c - photo y
    u = math_node(t, "DIVIDE", math_node(t, "MULTIPLY", xyz.outputs[0], 1000.0), info["width_mm"])
    y_photo = math_node(t, "SUBTRACT", c, math_node(t, "MULTIPLY", xyz.outputs[1], 1000.0))
    v = math_node(t, "SUBTRACT", 1.0, math_node(t, "DIVIDE", y_photo, info["height_mm"]))
    combined = t.nodes.new("ShaderNodeCombineXYZ")
    t.links.new(u, combined.inputs[0])
    t.links.new(v, combined.inputs[1])
    t.links.new(combined.outputs[0], tex.inputs["Vector"])
    bw = t.nodes.new("ShaderNodeRGBToBW")
    t.links.new(tex.outputs["Color"], bw.inputs[0])
    grooves = math_node(t, "MULTIPLY", bw.outputs[0], _facing_down(t))
    _bump(t, b, math_node(t, "SUBTRACT", 1.0, grooves), 1.0, 0.0012)
    color = t.nodes.new("ShaderNodeMix")
    color.data_type = "RGBA"
    t.links.new(grooves, color.inputs["Factor"])
    color.inputs["A"].default_value = (*lin(hexa), 1)
    color.inputs["B"].default_value = (*[c_ * 0.45 for c_ in lin(hexa)], 1)
    t.links.new(color.outputs["Result"], b.inputs["Base Color"])
    return _mark(m, role, hexa)


KIND = {
    "leather": leather, "tpu": tpu, "foam": foam, "mesh": knit_mesh, "lace": woven_lace, "soft": soft, "suede": suede,
    "striped_leather": lambda p, h: _rib(leather(p, h), *RIB["striped_leather"]),
    "striped_foam": lambda p, h: _rib(foam(p, h), *RIB["striped_foam"]),
}


def colorway_material(tread="waffle", capsule_mode="translucent", wrong_hex=None, capsule_ior=1.5):
    """{role: material} from a typed project palette. Non-default parameters exist only for QC negative tests."""
    m = {}
    for role, v in data.palette().items():
        hexa = (wrong_hex or {}).get(role, v[0])
        kind = v[2] if len(v) > 2 else "leather"
        if kind == "rubber":
            m[role] = rubber(role, hexa, tread)
        elif kind == "photo_rubber":
            m[role] = photo_rubber(role, hexa, tread)
        elif kind == "capsule":
            # the photo hex = what is SEEN through the window (cavity contents + the opposite window), not the film tint;
            # film tint [D] = hex lightened 70 % toward white (AM90-C12: tint = photo hex -> dark capsule, AM-17 0.0083 < 0.01)
            r, g, b = (int(hexa[i:i + 2], 16) for i in (1, 3, 5))
            tint = "#" + "".join("%02X" % round(c + (255 - c) * CAPSULE_TINT) for c in (r, g, b))
            m[role] = capsule(role, tint, capsule_ior, opaque=(capsule_mode == "opaque"))
            m[role]["hex_p3"] = hexa
        else:
            m[role] = KIND[kind](role, hexa)
        m[role].name = role
    m["upper"] = m["upper_mesh"]
    return m
