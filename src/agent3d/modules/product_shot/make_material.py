"""Test product materials: procedural label (logo + line + COLOR_VARIANT driven by CONTROL) + materials per product."""
import math

from ...core.material import make_material, transmission_shadow, clear_material, bsdf, math_node, new_node
from ...core.scene import drive
from . import specification


def label_material(name, z_logo, z_line, metal=0.0, coarse=0.35, **other_input):
    """Procedural label in UV: variant color (COLOR_VARIANT node, driven by CONTROL) + white logo on the front
    + dark wrap-around line. The logo is only on the front, so product orientation reads by eye on the contact sheet."""
    m = make_material(name, (0.5, 0.5, 0.5), coarse, metal, **other_input)
    t = m.node_tree
    b = bsdf(m)
    xyz = new_node(t, "ShaderNodeSeparateXYZ")
    t.links.new(new_node(t, "ShaderNodeTexCoord").outputs["UV"], xyz.inputs[0])
    u, z, _ = xyz.outputs  # label UV: u = 0.5 at front, v = height (m)
    in_front = math_node(t, "LESS_THAN", math_node(t, "ABSOLUTE", math_node(t, "SUBTRACT", u, 0.5)),
                          0.42 / (2 * math.pi))
    band = lambda z0, z1: math_node(t, "MULTIPLY", math_node(t, "GREATER_THAN", z, z0),
                                     math_node(t, "LESS_THAN", z, z1))
    logo = math_node(t, "MULTIPLY", in_front, band(*z_logo))
    line = band(*z_line)
    rgb = new_node(t, "ShaderNodeRGB", name="COLOR_VARIANT", label="COLOR_VARIANT")
    rgb.outputs[0].default_value = (0.5, 0.5, 0.5, 1)
    dark = new_node(t, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    dark.inputs["Factor"].default_value = 1.0
    t.links.new(line, dark.inputs["Factor"])
    t.links.new(rgb.outputs[0], dark.inputs["A"])
    dark.inputs["B"].default_value = (0.3, 0.3, 0.3, 1)
    white = new_node(t, "ShaderNodeMix", data_type="RGBA")
    t.links.new(logo, white.inputs["Factor"])
    t.links.new(dark.outputs["Result"], white.inputs["A"])
    white.inputs["B"].default_value = (0.85, 0.85, 0.85, 1)
    paper = new_node(t, "ShaderNodeMix", data_type="RGBA")  # C-11: label back side = paper, not print
    t.links.new(new_node(t, "ShaderNodeNewGeometry").outputs["Backfacing"], paper.inputs["Factor"])
    t.links.new(white.outputs["Result"], paper.inputs["A"])
    paper.inputs["B"].default_value = (0.78, 0.76, 0.70, 1)
    t.links.new(paper.outputs["Result"], b.inputs["Base Color"])
    for i in range(3):
        drive(t, 'nodes["COLOR_VARIANT"].outputs[0].default_value', "variant_color", index=i)
    return m


def product_material(name):
    s = specification.SPEC[name]
    mm = lambda k: tuple(v / 1000 for v in s[k])
    label = lambda **kw: label_material("LABEL_" + name, mm("logo_mm"), mm("line_mm"), **kw)
    if name in ("can", "slim_can"):
        # C-14: can paint = opaque ink + clearcoat over aluminium. Metallic 0.7 reflects the dark studio
        # (dramatic) so white renders grey (QC-10 0.36); 0.3 + coat 1.0 -> <= 0.13 in all presets
        return {"LABEL": label(metal=0.3, coarse=0.28, **{"Coat Weight": 1.0}),
                "metal": make_material("aluminium_metal", (0.80, 0.80, 0.82), 0.22, 1.0)}
    if name == "milk_carton":
        return {"LABEL": label(coarse=0.5),  # printed carton (whole box)
                "foil": make_material("straw_foil", (0.85, 0.85, 0.86), 0.3, 1.0)}
    if name == "tube":
        return {"LABEL": label(coarse=0.3),  # printed PE tube (whole body)
                "cap": make_material("white_cap", (0.85, 0.85, 0.83), 0.35)}
    if name == "jam_jar":
        return {"LABEL": label(coarse=0.45),
                "glass": clear_material("flint_glass", (0.95, 0.98, 0.96), 1.52),
                "contents": make_material("jam_fill", (0.30, 0.02, 0.04), 0.25),
                "cap": make_material("lug_cap", (0.72, 0.58, 0.30), 0.3, 1.0)}
    if name == "pet_bottle":
        return {"LABEL": label(coarse=0.25),
                "pet": clear_material("pet_plastic", (0.96, 0.98, 1.0), 1.57, 0.03),
                "water": clear_material("water", (0.97, 0.99, 1.0), 1.33, 0.0),
                "cap": make_material("pp_cap", (0.88, 0.88, 0.88), 0.4)}
    return {"LABEL": label(),
            # C-11: hollow glass is crossed at 4 interfaces (not 2), so the color per interface is brighter
            "glass": transmission_shadow(make_material("brown_glass", (0.70, 0.40, 0.12), 0.02, 0.0,
                                          **{"Transmission Weight": 1.0, "IOR": 1.52})),
            "liquid": transmission_shadow(make_material("beer_liquid", (0.92, 0.58, 0.16), 0.0, 0.0,
                                            **{"Transmission Weight": 1.0, "IOR": 1.33})),
            "cap": make_material("metal_cap", (0.78, 0.62, 0.28), 0.3, 1.0)}
