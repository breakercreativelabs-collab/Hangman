"""Neutral M1/M2 materials (before the M3 palette): treaded outsole, knit mesh, other roles plain."""
from ....core.material import make_material, transmission_shadow, bsdf

CAPSULE_IOR = 1.50       # [D] polyurethane/TPU


def outsole_material(tread="voronoi"):
    """Outsole rubber + procedural tread (bump, not geometry: silhouette & QC unchanged).
    C-A1: v1 used Wave (bands along X) = vertical lines in the bottom view. Now 2D Voronoi cells (~6 mm lugs,
    cell edges = grooves) with no dominant direction, so per-column means show no stripes. tread: voronoi | wave | plain."""
    m = make_material("outsole", (0.32, 0.32, 0.33), 0.85)
    if tread == "plain":
        return m
    t = m.node_tree
    b = bsdf(m)
    coord = t.nodes.new("ShaderNodeTexCoord")
    bump = t.nodes.new("ShaderNodeBump")
    if tread == "wave":  # v1 (negative test C-A1)
        tex = t.nodes.new("ShaderNodeTexWave")
        tex.inputs["Scale"].default_value = 25.0
        bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.3, 0.0008
        t.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        t.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    else:
        tex = t.nodes.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        tex.inputs["Scale"].default_value = 160.0  # 1/160 m ~ 6 mm per cell
        grooves = t.nodes.new("ShaderNodeMapRange")  # cell edge (< 0.08) = 1 mm groove, cell interior = flat lug
        grooves.inputs["From Min"].default_value, grooves.inputs["From Max"].default_value = 0.0, 0.08
        bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 1.0, 0.001
        t.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        t.links.new(tex.outputs["Distance"], grooves.inputs["Value"])
        t.links.new(grooves.outputs["Result"], bump.inputs["Height"])
        color = t.nodes.new("ShaderNodeMix")  # grooves slightly darker (dirt/cheap AO)
        color.data_type = "RGBA"
        color.inputs["A"].default_value, color.inputs["B"].default_value = (0.12, 0.12, 0.13, 1), (0.32, 0.32, 0.33, 1)
        t.links.new(grooves.outputs["Result"], color.inputs["Factor"])
        t.links.new(color.outputs["Result"], b.inputs["Base Color"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mesh_material(name, color):
    """Knit mesh for toe box/quarter: small bump cells (~1.3 mm) so it reads as mesh, color stays neutral."""
    m = make_material(name, color, 0.8)
    t = m.node_tree
    coord = t.nodes.new("ShaderNodeTexCoord")
    tex = t.nodes.new("ShaderNodeTexVoronoi")
    tex.inputs["Scale"].default_value = 750.0
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.6, 0.0003
    t.links.new(coord.outputs["Object"], tex.inputs["Vector"])
    t.links.new(tex.outputs["Distance"], bump.inputs["Height"])
    t.links.new(bump.outputs["Normal"], bsdf(m).inputs["Normal"])
    return m


def neutral_material(tread="voronoi"):
    m = {
        "midsole": make_material("midsole", (0.86, 0.86, 0.84), 0.55),
        "outsole": outsole_material(tread),
        "air_capsule": transmission_shadow(make_material("air_capsule", (0.93, 0.96, 1.0), 0.04, 0.0,
                                                        **{"Transmission Weight": 1.0, "IOR": CAPSULE_IOR})),
        "upper_mesh": mesh_material("upper_mesh", (0.62, 0.62, 0.63)),
        "mudguard": make_material("mudguard", (0.30, 0.30, 0.31), 0.9),
        "overlay_suede": make_material("overlay_suede", (0.42, 0.42, 0.43), 0.95),
        "swoosh": make_material("swoosh", (0.12, 0.12, 0.13), 0.5),
        "lining": make_material("lining", (0.05, 0.05, 0.055), 0.9),
        "lace": make_material("lace", (0.80, 0.80, 0.78), 0.85),
        "chrome_accent": make_material("chrome_accent", (0.83, 0.86, 0.91), 0.2, 1.0),
    }
    m["outsole"].name = "outsole"
    m["upper"] = m["upper_mesh"]  # M1 block (negative test C-A3)
    return m
