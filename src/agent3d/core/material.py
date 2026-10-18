"""Material: the ONLY place for node helpers (bsdf, make_material, new_node, math_node, ramp, transmission_shadow).
Other modules must use these helpers (structure test c: no duplicate helpers)."""
import bpy


def bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def make_material(name, color, coarse=0.4, metal=0.0, **other_input):
    """New Principled material: linear color (r, g, b), roughness, metallic, other Principled inputs by name."""
    m = bpy.data.materials.new(name)
    b = bsdf(m)
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = coarse
    b.inputs["Metallic"].default_value = metal
    for k, v in other_input.items():
        b.inputs[k].default_value = v
    return m


def new_node(t, value_type, **kw):
    """New node in node tree `t`, with node attributes set."""
    n = t.nodes.new(value_type)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def math_node(t, op, a=None, b=None):
    """Math node: number input = default_value, socket input = linked. Returns the output socket."""
    n = new_node(t, "ShaderNodeMath", operation=op)
    for i, x in enumerate((a, b)):
        if isinstance(x, (int, float)):
            n.inputs[i].default_value = x
        elif x is not None:
            t.links.new(x, n.inputs[i])
    return n.outputs[0]


def ramp(t, fac, c0, c1):
    """Two-color (linear) color ramp driven by socket fac. Returns the color socket."""
    cr = new_node(t, "ShaderNodeValToRGB")
    cr.color_ramp.elements[0].color, cr.color_ramp.elements[1].color = (*c0, 1), (*c1, 1)
    t.links.new(fac, cr.inputs[0])
    return cr.outputs[0]


def transmission_shadow(m):
    """C-11: caustics are off, so shadow rays are blocked by glass/liquid and bottle contents + inner label side go black.
    For shadow rays the clear material becomes a tinted Transparent BSDF (standard product-render technique)."""
    t = m.node_tree
    out = next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL")
    original = out.inputs["Surface"].links[0].from_socket
    transmission = new_node(t, "ShaderNodeBsdfTransparent")
    transmission.inputs["Color"].default_value = bsdf(m).inputs["Base Color"].default_value
    mix = new_node(t, "ShaderNodeMixShader")
    t.links.new(new_node(t, "ShaderNodeLightPath").outputs["Is Shadow Ray"], mix.inputs[0])
    t.links.new(original, mix.inputs[1])
    t.links.new(transmission.outputs[0], mix.inputs[2])
    t.links.new(mix.outputs[0], out.inputs["Surface"])
    return m


def clear_material(name, color, ior, coarse=0.02):
    """Clear glass/plastic/liquid material + transmission shadow (C-11)."""
    return transmission_shadow(make_material(name, color, coarse, 0.0, **{"Transmission Weight": 1.0, "IOR": ior}))
