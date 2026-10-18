"""TVC compositor (Blender 5.x: scene.compositing_node_group): light glare -> flash on the beat -> vignette -> grain."""
import math

import bpy

from ...core.material import math_node
from ...core.scene import control, fcurves


def compositor(flash):
    """Light glare (bloom on highlights) -> flash on the beat (ADD white, frames from `flash` {frame: strength}, constant
    interpolation) -> vignette (corners -30 %) -> fine grain (per-pixel white noise, changing every frame via the `frame`
    driver, 9 % overlay)."""
    sc = bpy.context.scene
    ng = bpy.data.node_groups.new("TVC_comp", "CompositorNodeTree")
    ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    sc.compositing_node_group = ng
    sc.render.use_compositing = True
    N, L = ng.nodes, ng.links
    rl = N.new("CompositorNodeRLayers")
    gl = N.new("CompositorNodeGlare")
    gl.inputs["Type"].default_value = "Bloom"
    gl.inputs["Threshold"].default_value = 0.85
    gl.inputs["Strength"].default_value = 0.35
    gl.inputs["Size"].default_value = 0.5
    L.new(rl.outputs["Image"], gl.inputs["Image"])
    fl = N.new("ShaderNodeMix")
    fl.name, fl.data_type, fl.blend_type = "flash", "RGBA", "ADD"
    fl.inputs["B"].default_value = (1.0, 0.97, 1.0, 1.0)
    L.new(gl.outputs["Image"], fl.inputs["A"])
    fac_in = fl.inputs[0]
    fac_in.default_value = 0.0
    fac_in.keyframe_insert("default_value", frame=1)
    for f, k in sorted(flash.items()):
        fac_in.default_value = k
        fac_in.keyframe_insert("default_value", frame=f)
        if f + 1 not in flash:
            fac_in.default_value = 0.0
            fac_in.keyframe_insert("default_value", frame=f + 1)
    for fc in fcurves(ng):
        for kp in fc.keyframe_points:
            kp.interpolation = "CONSTANT"
    ko = N.new("CompositorNodeImageCoordinates")
    L.new(rl.outputs["Image"], ko.inputs["Image"])
    sep = N.new("ShaderNodeSeparateXYZ")
    L.new(ko.outputs["Normalized"], sep.inputs[0])
    du = math_node(ng, "MULTIPLY", math_node(ng, "SUBTRACT", sep.outputs[0], 0.5), 2.0)
    dv = math_node(ng, "MULTIPLY", math_node(ng, "SUBTRACT", sep.outputs[1], 0.5), 2.0)
    r = math_node(ng, "MULTIPLY", math_node(ng, "SQRT", math_node(
        ng, "ADD", math_node(ng, "MULTIPLY", du, du), math_node(ng, "MULTIPLY", dv, dv))), 1 / math.sqrt(2))
    mr = N.new("ShaderNodeMapRange")
    mr.interpolation_type = "SMOOTHSTEP"
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.55, 1.0
    mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = 1.0, 0.70
    L.new(r, mr.inputs["Value"])
    vg = N.new("ShaderNodeMix")
    vg.name, vg.data_type, vg.blend_type = "vignette", "RGBA", "MULTIPLY"
    vg.inputs[0].default_value = 1.0
    L.new(fl.outputs["Result"], vg.inputs["A"])
    L.new(mr.outputs["Result"], vg.inputs["B"])
    wn = N.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "4D"
    L.new(ko.outputs["Pixel"], wn.inputs["Vector"])
    drv = wn.inputs["W"].driver_add("default_value")
    drv.driver.type, drv.driver.expression = "SCRIPTED", "frame"
    gr = N.new("ShaderNodeMix")
    gr.name, gr.data_type, gr.blend_type = "grain", "RGBA", "OVERLAY"
    gr.inputs[0].default_value = 0.09
    L.new(vg.outputs["Result"], gr.inputs["A"])
    L.new(wn.outputs["Value"], gr.inputs["B"])
    out = N.new("NodeGroupOutput")
    L.new(gr.outputs["Result"], out.inputs[0])
    control()["flash_frame"] = sorted(flash)
    return ng
