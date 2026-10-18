"""Shoe recipe M3: procedural MATERIALS from the project palette (P3 Aqua Holo for AM1, experiment/taste.md), non-generative.

One function per role (M2 slot, data.ROLE). Each material stores `role` and `hex_p3` (read by QC AM-15/AM-18).
Hex + source per role live in project.toml [palette.role] ([F] user decision in taste.md; [D] assumption).

Variants for QC negative tests (not for real use):
  swoosh="plain"        plain diffuse swoosh (AM-16)
  capsule="opaque"         capsule without transmission (AM-17)
  wrong_hex={role: hex} wrong role color (AM-15)
  tread="voronoi|wave|plain" old/negative tread (AM-07); default "waffle"
Called by sole.build_shoe(palette="p3").
"""
import math

from ....core.material import make_material, transmission_shadow, bsdf, math_node
from ....core.color import lin
from . import data


def P3():
    """{role: (hex, source)} of the active project palette."""
    return data.palette()


# Waffle tread [D] (no photo): 6.5 mm forefoot boxes, elongated 13 x 6.5 mm heel cells, 1.2 mm grooves, grid rotated
# 15 deg. C-A7: an axis-aligned grid (0 deg) = transverse grooves across the whole sole = exactly the coherent lines AM-07
# looks for (0.077 > 0.010); 10-30 deg -> 0.000; 45 deg -> 0.021 (a diagonal grid is periodic the same way in both halves again).
WAFFLE = dict(x_heel=168.0, box=6.5, heel=(13.0, 6.5), grooves=1.2, angle=15.0, edge=0.35)
# Holo swoosh [D]: hue sequence vs viewing angle (facing 0 = perpendicular = P3 hex). Like Y2K holographic foil.
HOLO_RAMP = ((0.00, "#2FD0B6"), (0.12, "#2FD0B6"), (0.40, "#3FA9F5"), (0.62, "#9A7BFF"), (0.80, "#FF8AD8"),
             (1.00, "#C8F56A"))


def _mark(m, role, hexa):
    m["role"], m["hex_p3"] = role, hexa
    return m


def _bump(t, b, height, strength, distance):
    bump = t.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = strength, distance
    t.links.new(height, bump.inputs["Height"])
    if b.inputs["Normal"].links:  # bump chain: the previous normal becomes the input
        t.links.new(b.inputs["Normal"].links[0].from_socket, bump.inputs["Normal"])
    t.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return bump


def _coord(t):
    return t.nodes.new("ShaderNodeTexCoord").outputs["Object"]


def _noise(t, scale, detail=4.0, coarse=0.6):
    n = t.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value, n.inputs["Detail"].default_value = scale, detail
    n.inputs["Roughness"].default_value = coarse
    t.links.new(_coord(t), n.inputs["Vector"])
    return n


def _color_variation(t, b, hexa, amp, scale):
    """Base color x (1 +- amp) from soft noise: subtle imperfection (taste.md: sterile pastel = dated)."""
    n = _noise(t, scale, 2.0, 0.5)
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1 - amp, 1 + amp
    t.links.new(n.outputs["Fac"], mr.inputs["Value"])
    times = t.nodes.new("ShaderNodeMix")
    times.data_type, times.blend_type = "RGBA", "MULTIPLY"
    times.inputs["Factor"].default_value = 1.0
    times.inputs["A"].default_value = (*lin(hexa), 1)
    t.links.new(mr.outputs["Result"], times.inputs["B"])
    return times.outputs["Result"]


def suede(role, hexa):
    """Suede/nubuck: very rough + sheen (fine nap catches grazing light), 0.3 mm nap bump, faint mottling."""
    m = make_material(role, lin(hexa), 0.92)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value, b.inputs["Sheen Roughness"].default_value = 0.6, 0.35
    b.inputs["Sheen Tint"].default_value = (1.0, 1.0, 1.0, 1)
    b.inputs["Specular IOR Level"].default_value = 0.3
    t.links.new(_color_variation(t, b, hexa, 0.05, 90.0), b.inputs["Base Color"])
    _bump(t, b, _noise(t, 2500.0, 6.0, 0.7).outputs["Fac"], 0.25, 0.0003)
    return _mark(m, role, hexa)


def knit_mesh(role, hexa):
    """Toe box/quarter mesh: ~2 mm hole grid (Voronoi without randomness = regular grid), holes darker (lining
    underneath) + recessed; fine knit yarn between the holes."""
    m = make_material(role, lin(hexa), 0.85)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value, b.inputs["Sheen Roughness"].default_value = 0.3, 0.5
    vor = t.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value, vor.inputs["Randomness"].default_value = 650.0, 0.0  # 1/650 m ~ 1.5 mm
    t.links.new(_coord(t), vor.inputs["Vector"])
    hole = t.nodes.new("ShaderNodeMapRange")  # cell center (distance < 0.22) = hole
    hole.interpolation_type = "SMOOTHSTEP"
    hole.inputs["From Min"].default_value, hole.inputs["From Max"].default_value = 0.26, 0.19
    t.links.new(vor.outputs["Distance"], hole.inputs["Value"])
    color = t.nodes.new("ShaderNodeMix")
    color.data_type = "RGBA"
    t.links.new(hole.outputs["Result"], color.inputs["Factor"])
    t.links.new(_color_variation(t, b, hexa, 0.03, 120.0), color.inputs["A"])
    color.inputs["B"].default_value = (*[c * 0.45 for c in lin(hexa)], 1)
    t.links.new(color.outputs["Result"], b.inputs["Base Color"])
    inv = t.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    t.links.new(hole.outputs["Result"], inv.inputs[1])
    _bump(t, b, inv.outputs[0], 0.7, 0.0004)
    wav = t.nodes.new("ShaderNodeTexWave")  # knit yarn
    wav.inputs["Scale"].default_value, wav.inputs["Distortion"].default_value = 2200.0, 3.0
    t.links.new(_coord(t), wav.inputs["Vector"])
    _bump(t, b, wav.outputs["Fac"], 0.15, 0.0001)
    return _mark(m, role, hexa)


def holo(role, hexa, plain=False):
    """Iridescent swoosh: base color hue shifts with viewing angle (Layer Weight facing -> holo ramp; perpendicular
    = P3 hex), plus thin-film on the specular layer (real Principled interference) and clearcoat.
    plain=True: plain teal diffuse (negative test AM-16)."""
    m = make_material(role, lin(hexa), 0.5 if plain else 0.28, 0.0)
    if plain:
        return _mark(m, role, hexa)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Coat Weight"].default_value, b.inputs["Coat Roughness"].default_value = 0.6, 0.08
    b.inputs["Thin Film Thickness"].default_value, b.inputs["Thin Film IOR"].default_value = 520.0, 1.45
    lw = t.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    ramp = t.nodes.new("ShaderNodeValToRGB")
    el = ramp.color_ramp.elements
    for i, (pos, h) in enumerate(HOLO_RAMP):
        h = hexa if h == P3()["swoosh"][0] else h  # facing ~0 = role color (wrong_hex follows, negative test AM-15)
        e = el[i] if i < len(el) else el.new(pos)
        e.position, e.color = pos, (*lin(h), 1)
    t.links.new(lw.outputs["Facing"], ramp.inputs["Fac"])
    t.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return _mark(m, role, hexa)


def chrome(role, hexa):
    """Cool silver chrome accent: metal, roughness 0.12, thin thin-film (subtle hologram shift in highlights)."""
    m = make_material(role, lin(hexa), 0.12, 1.0)
    b = bsdf(m)
    b.inputs["Thin Film Thickness"].default_value, b.inputs["Thin Film IOR"].default_value = 300.0, 1.33
    return _mark(m, role, hexa)


def foam(role, hexa):
    """Semi-matte PU/EVA midsole foam: roughness 0.5, fine pores (0.2 mm noise bump)."""
    m = make_material(role, lin(hexa), 0.5)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Specular IOR Level"].default_value = 0.4
    _bump(t, b, _noise(t, 1800.0, 3.0, 0.5).outputs["Fac"], 0.12, 0.0002)
    return _mark(m, role, hexa)


def capsule(role, hexa, ior, opaque=False):
    """Translucent pink Air capsule: full transmission (hollow, QC-11) + slight frosting (roughness 0.08) + transmission
    shadow (C-11). opaque=True: no transmission (negative test AM-17)."""
    if opaque:
        return _mark(make_material(role, lin(hexa), 0.3), role, hexa)
    m = make_material(role, lin(hexa), 0.08, 0.0, **{"Transmission Weight": 1.0, "IOR": ior})
    return _mark(transmission_shadow(m), role, hexa)


def _groove(t, a, pitch, width, edge):
    """1 in grooves (near grid lines spaced `pitch` mm along coordinate a in mm), 0 on lugs; smoothstep edges."""
    d = math_node(t, "ABSOLUTE", math_node(t, "SUBTRACT",
                                                  math_node(t, "FRACT", math_node(t, "DIVIDE", a, pitch)), 0.5))
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    limit = pitch / 2 - width / 2
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = limit - edge, limit + edge
    t.links.new(math_node(t, "MULTIPLY", d, pitch), mr.inputs["Value"])
    return mr.outputs["Result"]


def _waffle(t, p=WAFFLE):
    """Waffle groove mask [D] in the object XY plane (mm), grid rotated by `angle`: forefoot boxes, heel (x' >= x_heel)
    cells elongated along x'. Returns a 0..1 socket (1 = groove)."""
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(_coord(t), xyz.inputs[0])
    x, y = (math_node(t, "MULTIPLY", xyz.outputs[i], 1000.0) for i in (0, 1))
    c, s = math.cos(math.radians(p["angle"])), math.sin(math.radians(p["angle"]))
    xr = math_node(t, "SUBTRACT", math_node(t, "MULTIPLY", x, c), math_node(t, "MULTIPLY", y, s))
    yr = math_node(t, "ADD", math_node(t, "MULTIPLY", x, s), math_node(t, "MULTIPLY", y, c))
    g, e = p["grooves"], p["edge"]
    front = math_node(t, "MAXIMUM", _groove(t, xr, p["box"], g, e), _groove(t, yr, p["box"], g, e))
    back = math_node(t, "MAXIMUM", _groove(t, xr, p["heel"][0], g, e), _groove(t, yr, p["heel"][1], g, e))
    at_heel = math_node(t, "GREATER_THAN", xr, p["x_heel"])
    mix = t.nodes.new("ShaderNodeMix")
    t.links.new(at_heel, mix.inputs["Factor"])
    t.links.new(front, mix.inputs["A"])
    t.links.new(back, mix.inputs["B"])
    return mix.outputs["Result"]


def _facing_down(t):
    """0..1: surface faces down (world normal z < -0.35 .. -0.6). Tread only on the base, outsole walls plain
    (M2 observation: 3D Voronoi also showed on the side walls)."""
    xyz = t.nodes.new("ShaderNodeSeparateXYZ")
    t.links.new(t.nodes.new("ShaderNodeNewGeometry").outputs["Normal"], xyz.inputs[0])
    mr = t.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.35, 0.6
    t.links.new(math_node(t, "MULTIPLY", xyz.outputs[2], -1.0), mr.inputs["Value"])
    return mr.outputs["Result"]


def rubber(role, hexa, tread="waffle"):
    """Tonal outsole rubber: roughness 0.8 + tread. waffle (M3) | voronoi (M2) | wave (v1, negative C-A1) | plain."""
    m = make_material(role, lin(hexa), 0.8)
    t, b = m.node_tree, bsdf(m)
    if tread == "plain":
        return _mark(m, role, hexa)
    if tread == "waffle":
        grooves = math_node(t, "MULTIPLY", _waffle(t), _facing_down(t))
        height = math_node(t, "SUBTRACT", 1.0, grooves)
        _bump(t, b, height, 1.0, 0.0012)
    else:
        coord = _coord(t)
        if tread == "wave":
            tex = t.nodes.new("ShaderNodeTexWave")
            tex.inputs["Scale"].default_value = 25.0
            t.links.new(coord, tex.inputs["Vector"])
            _bump(t, b, tex.outputs["Fac"], 0.3, 0.0008)
            return _mark(m, role, hexa)
        tex = t.nodes.new("ShaderNodeTexVoronoi")
        tex.feature = "DISTANCE_TO_EDGE"
        tex.inputs["Scale"].default_value = 160.0
        t.links.new(coord, tex.inputs["Vector"])
        mr = t.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.08, 0.0
        t.links.new(tex.outputs["Distance"], mr.inputs["Value"])
        grooves = mr.outputs["Result"]
        _bump(t, b, math_node(t, "SUBTRACT", 1.0, grooves), 1.0, 0.001)
    color = t.nodes.new("ShaderNodeMix")  # darker grooves (dirt/cheap AO)
    color.data_type = "RGBA"
    t.links.new(grooves, color.inputs["Factor"])
    color.inputs["A"].default_value = (*lin(hexa), 1)
    color.inputs["B"].default_value = (*[c * 0.4 for c in lin(hexa)], 1)
    t.links.new(color.outputs["Result"], b.inputs["Base Color"])
    return _mark(m, role, hexa)


def woven_lace(role, hexa):
    """Woven lace: fine distorted wave bands (fibers) + light sheen."""
    m = make_material(role, lin(hexa), 0.8)
    t, b = m.node_tree, bsdf(m)
    b.inputs["Sheen Weight"].default_value = 0.4
    wav = t.nodes.new("ShaderNodeTexWave")
    wav.inputs["Scale"].default_value, wav.inputs["Distortion"].default_value = 1400.0, 6.0
    t.links.new(_coord(t), wav.inputs["Vector"])
    _bump(t, b, wav.outputs["Fac"], 0.5, 0.0003)
    return _mark(m, role, hexa)


def soft(role, hexa):
    m = make_material(role, lin(hexa), 0.9)
    b = bsdf(m)
    b.inputs["Sheen Weight"].default_value = 0.3
    return _mark(m, role, hexa)


def p3_material(tread="waffle", swoosh="holo", capsule_mode="translucent", wrong_hex=None, capsule_ior=1.5):
    hx = {k: v[0] for k, v in P3().items()}
    hx.update(wrong_hex or {})
    m = {
        "mudguard": suede("mudguard", hx["mudguard"]),
        "outsole": rubber("outsole", hx["outsole"], tread),
        "upper_mesh": knit_mesh("upper_mesh", hx["upper_mesh"]),
        "swoosh": holo("swoosh", hx["swoosh"], plain=(swoosh == "plain")),
        "midsole": foam("midsole", hx["midsole"]),
        "air_capsule": capsule("air_capsule", hx["air_capsule"], capsule_ior, opaque=(capsule_mode == "opaque")),
        "overlay_suede": suede("overlay_suede", hx["overlay_suede"]),
        "lining": soft("lining", hx["lining"]),
        "lace": woven_lace("lace", hx["lace"]),
        "chrome_accent": chrome("chrome_accent", hx["chrome_accent"]),
    }
    for k, v in m.items():
        v.name = k  # name = role (AM-14); avoid the .001 suffix
    m["upper"] = m["upper_mesh"]  # M1 block (negative test C-A3)
    return m
