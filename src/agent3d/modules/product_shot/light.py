"""VERB 3 studio_lighting: area lights + cyclorama backdrop, scaled to product height."""
import math

import bpy
import numpy as np
from mathutils import Vector

from ...core.camera import direction, look_at
from ...core.material import make_material
from ...core.scene import control, drive, collection
from .verbs import product_size

# az: degrees from -Y (camera direction) toward +X; el: elevation degrees; distance & size in multiples of product height.
LIGHT_PRESETS = {
    "softbox": dict(background=0.30, world=0.04, lamp=[
        ("key", -40, 28, 4.0, (1.6, 2.4), 1.00),
        ("fill", 55, 12, 5.0, (2.2, 2.2), 0.30),
        ("rim", 155, 35, 3.5, (0.4, 3.0), 0.90)]),
    "high_key": dict(background=0.80, world=0.25, lamp=[
        ("left", -55, 20, 4.0, (2.4, 3.0), 0.55),   # v2: 0.80 -> 0.55, bottle label washed out (QC-10 0.63)
        ("right", 55, 20, 4.0, (2.4, 3.0), 0.55),
        ("top", 0, 75, 4.0, (2.4, 2.4), 0.40)]),
    "dramatic": dict(background=0.06, world=0.0, lamp=[
        ("rim_left", -115, 18, 3.0, (0.35, 3.2), 1.30),
        ("rim_right", 115, 18, 3.0, (0.35, 3.2), 1.30),
        ("key", -30, 50, 4.5, (1.2, 1.2), 1.40)],  # v2: 0.45 -> 1.40, white label rendered grey (QC-10)
        # C-15: upright metal (slim can neck) reflects the dark front-lower direction -> pitch black.
        # Reflection card behind the camera, visible to glossy rays only (adds no diffuse light).
        reflection=[("front_card", 0, 10, 4.5, (6.0, 1.5), 0.10)]),
}
BASE_POWER = 12.0  # W per m^2 of distance (calibrated 2026-10-13, QC-10); lamp power = factor x BASE_POWER x distance^2 (constant irradiance across product sizes)


def backdrop(h, brightness):
    """Cyclorama: floor curving into the wall (no horizon line). Size relative to product height."""
    kb = collection("BACKDROP")
    for o in list(kb.objects):
        bpy.data.objects.remove(o)
    W, F, B, R, H = 30 * h, 12 * h, 3 * h, 5 * h, 18 * h
    prof = [(-F, 0.0), (B, 0.0)] + [(B + R * math.sin(t), R - R * math.cos(t))
                                     for t in np.linspace(0, math.pi / 2, 17)[1:]] + [(B + R, H)]
    vs = [(x, y, z) for y, z in prof for x in (-W / 2, W / 2)]
    fs = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(prof) - 1)]
    me = bpy.data.meshes.new("backdrop")
    me.from_pydata(vs, [], fs)
    me.shade_smooth()
    ob = bpy.data.objects.new("backdrop", me)
    kb.objects.link(ob)
    me.materials.append(make_material("backdrop", (brightness,) * 3, 0.6))
    return ob


def studio_lighting(preset="softbox"):
    """Area lights (softbox/strip) + cyclorama backdrop, scaled to product height.
    All lamp energies are driven by CONTROL['light_intensity']."""
    p = LIGHT_PRESETS[preset]
    h, _ = product_size()
    center = Vector((0, 0, h * 0.5))
    kl = collection("LIGHTS")
    for o in list(kl.objects):
        bpy.data.objects.remove(o)
    reflection = {r[0] for r in p.get("reflection", [])}
    for name, az, el, distance, (sx, sy), f in p["lamp"] + p.get("reflection", []):
        d = bpy.data.lights.new(f"L_{name}", "AREA")
        d.shape, d.size, d.size_y = "RECTANGLE", sx * h, sy * h
        energy = f * BASE_POWER * (distance * h) ** 2
        d.energy = energy
        ob = bpy.data.objects.new(f"L_{name}", d)
        ob.location = center + direction(az, el) * distance * h
        look_at(ob, center)
        kl.objects.link(ob)
        if name in reflection:  # reflection card: glossy rays only (highlights on metal/glass), no diffuse light
            ob.visible_diffuse = ob.visible_transmission = ob.visible_volume_scatter = False
        drive(d, "energy", "light_intensity", f"var*{energy:.5f}")
    backdrop(h, p["background"])
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    bg = next(n for n in w.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value = (1, 1, 1, 1)
    bg.inputs[1].default_value = p["world"]
    control()["light_preset"] = preset
    return [o.name for o in kl.objects]
