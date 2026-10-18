"""Shoe recipe studios: neutral review (color QC, shape check) and the project palette studio (P3: aqua -> violet gradient)."""
import bpy
from mathutils import Vector

from ....core.camera import look_at
from ....core.material import make_material, math_node
from ....core.scene import collection
from ....core.color import lin
from ..geometry import mesh_obj
from . import data


# ---------------- studio ----------------
def use_studio(name):
    """review = neutral QC lighting (studio_review); p3 = P3 review studio (aqua -> violet gradient, softbox + rim)."""
    sc = bpy.context.scene
    floor = None
    if name == "review":
        w = bpy.data.worlds.get("world_review") or bpy.data.worlds.new("world_review")
        sc.world = w
        floor = studio_review()
    else:
        studio_p3()
    for ob in bpy.data.objects:
        if ob.name in ("L_key", "L_fill", "L_rim", "L_bottom", "floor"):
            ob.hide_render = name != "review"
        elif ob.name.startswith("P3_"):
            ob.hide_render = name != "p3"
    return floor


def studio_p3():
    """Project palette review studio (eye check, not color QC): project.toml background gradient (P3: aqua -> violet) (camera rays only, screen diagonal),
    very dim violet-tinted ambient, white key softbox, aqua rim + violet kicker from behind (Y2K glow),
    shadow-catcher floor."""
    sc = bpy.context.scene
    w = bpy.data.worlds.get("world_p3")
    if w is None:
        gradient = data.CONFIG["palette"]["gradient"]  # taste.md P3: aqua -> violet background
        w = bpy.data.worlds.new("world_p3")
        w.use_nodes = True
        t = w.node_tree
        bg = next(n for n in t.nodes if n.type == "BACKGROUND")
        out = next(n for n in t.nodes if n.type == "OUTPUT_WORLD")
        coord = t.nodes.new("ShaderNodeTexCoord")
        xyz = t.nodes.new("ShaderNodeSeparateXYZ")
        t.links.new(coord.outputs["Window"], xyz.inputs[0])
        diag = math_node(t, "MULTIPLY", math_node(t, "ADD", xyz.outputs[0], math_node(t, "SUBTRACT", 1.0, xyz.outputs[1])), 0.5)
        ramp = t.nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (*lin(gradient[0]), 1)
        ramp.color_ramp.elements[1].color = (*lin(gradient[1]), 1)
        t.links.new(diag, ramp.inputs["Fac"])
        background = t.nodes.new("ShaderNodeBackground")
        background.inputs["Strength"].default_value = 1.41  # P3 render exposure -0.5: background stays at the taste.md hex
        t.links.new(ramp.outputs["Color"], background.inputs["Color"])
        bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.80, 0.78, 0.95, 1), 0.03
        mix = t.nodes.new("ShaderNodeMixShader")
        t.links.new(t.nodes.new("ShaderNodeLightPath").outputs["Is Camera Ray"], mix.inputs[0])
        t.links.new(bg.outputs[0], mix.inputs[1])
        t.links.new(background.outputs[0], mix.inputs[2])
        t.links.new(mix.outputs[0], out.inputs["Surface"])
        kl = collection("LIGHTS")
        center = Vector((0.147, 0.0, 0.05))
        for name, hit_loc, energy, size, color in (
                ("P3_softbox", (-0.05, 0.40, 0.45), 11.0, 0.7, (1, 1, 1)),
                # rim from BEHIND (opposite the hero camera): a rim on the camera side flattens the shape (see QC_RULES M3)
                ("P3_rim_aqua", (0.42, -0.30, 0.32), 6.0, 0.25, tuple(lin(gradient[0]))),
                ("P3_rim_violet", (-0.12, -0.38, 0.20), 3.0, 0.25, tuple(lin(gradient[1])))):
            d = bpy.data.lights.new(name, "AREA")
            d.energy, d.size, d.color = energy, size, color
            ob = bpy.data.objects.new(name, d)
            kl.objects.link(ob)
            ob.location = hit_loc
            look_at(ob, center)
        lt = mesh_obj("P3_floor", [(-1, -1, 0), (1.5, -1, 0), (1.5, 1, 0), (-1, 1, 0)], [(0, 1, 2, 3)],
                     collection("BACKDROP"), validation=False)
        lt.is_shadow_catcher = True
    sc.world = w


# ---------------- view renders (eye check) ----------------
def studio_review():
    """Neutral review lighting (not the product-shot preset: the model is not normalized, M1 is a shape check only)."""
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("world")
    sc.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value, bg.inputs["Strength"].default_value = (0.55, 0.57, 0.60, 1), 0.35
    if bpy.data.objects.get("floor"):
        return bpy.data.objects["floor"]
    kl = collection("LIGHTS")
    # L_bottom: lights the sole from below at a grazing angle (tread grooves read); blocked by the floor in other views
    for name, hit_loc, energy, size in (("L_key", (0.05, 0.45, 0.55), 18.0, 0.5), ("L_fill", (0.25, -0.5, 0.25), 6.0, 0.8),
                                      ("L_rim", (0.55, 0.1, 0.35), 8.0, 0.3), ("L_bottom", (-0.15, 0.25, -0.30), 5.0, 0.5)):
        d = bpy.data.lights.new(name, "AREA")
        d.energy, d.size = energy, size
        ob = bpy.data.objects.new(name, d)
        kl.objects.link(ob)
        ob.location = hit_loc
        look_at(ob, Vector((0.147, 0.0, 0.05)))
    floor = mesh_obj("floor", [(-1, -1, 0), (1.5, -1, 0), (1.5, 1, 0), (-1, 1, 0)], [(0, 1, 2, 3)],
                     collection("BACKDROP"), validation=False)
    floor.data.materials.append(make_material("floor", (0.16, 0.16, 0.17), 0.6))
    return floor
