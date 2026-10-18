"""SYNTHETIC reference photos for the extraction smoke test (runner suite `cli`, Task 10 C-B3). Non-generative: an
orthographic Blender render of the project model with a flat color per role mimicking the original photo colorway
(white/black: dark mudguard, swoosh, overlay; white midsole; grey capsule = window). Not measurement data: it only lets
extract_contour / extract_panel / alpha_analysis run without client photos (the originals never enter the repo).

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- reference_modeling test_photo --out <folder>
Output: <folder>/{lateral,medial,top,heel,sole}.png (RGBA, alpha = silhouette). The top/heel views show a PAIR of
shoes (right + mirror), like the product photos (contour.split_pair).
"""
import math
import os

import bpy
from mathutils import Vector

from ....core.camera import look_at, camera
from ....core.render import render_image
from ....core.scene import product_object, root
from ....core.color import lin

# flat luma per role (mimics FD9082-107: dark panels luma < 0.45, bright midsole > 0.6, window < 0.6)
COLOR = dict(mudguard="#262626", overlay_suede="#2E2E2E", swoosh="#1A1A1A", outsole="#3A3A3A", midsole="#F4F4F4",
             air_capsule="#8C8C8C", upper_mesh="#E8E8E8", lining="#E0E0E0", lace="#F0F0F0", chrome_accent="#B0B0B0")
PX_M = 2500                   # pixels per meter (0.4 mm/px; shoe length ~730 px)


def _test_emission_material(hexa):
    m = bpy.data.materials.new("_test_" + hexa)
    t = m.node_tree
    for n in list(t.nodes):
        if n.type != "OUTPUT_MATERIAL":
            t.nodes.remove(n)
    em = t.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*lin(hexa), 1)
    t.links.new(em.outputs[0], next(n for n in t.nodes if n.type == "OUTPUT_MATERIAL").inputs["Surface"])
    return m


def test_photo(out):
    os.makedirs(out, exist_ok=True)
    sc = bpy.context.scene
    sc.view_settings.view_transform, sc.view_settings.exposure = "Standard", 0.0
    sc.world = bpy.data.worlds.new("_test_world")
    sc.cycles.use_denoising = False
    mat = {k: _test_emission_material(v) for k, v in COLOR.items()}
    for ob in product_object():
        for i, m in enumerate(ob.data.materials):
            ob.data.materials[i] = mat.get(m.name if m else "", mat["midsole"])
    r0 = root()
    install = r0.copy()  # left shoe (mirrored Y) for the top/heel views
    bpy.context.scene.collection.objects.link(install)
    for ob in product_object():
        c = ob.copy()
        bpy.context.scene.collection.objects.link(c)
        c.parent = install
    install.scale.y = -1
    install.location.y = 0.14
    c0 = Vector((0.147, 0.0, 0.065))
    result = []
    for name, direction, w, h, two in (("lateral", (0, -1, 0), 800, 400, False), ("medial", (0, 1, 0), 800, 400, False),
                                  ("sole", (0, 0, -1), 800, 400, False), ("top", (0, 0, 1), 800, 800, True),
                                  ("heel", (1, 0, 0), 800, 400, True)):
        install.hide_render = not two
        for c in install.children:
            c.hide_render = not two
        center = c0 + (Vector((0, 0.07, 0)) if two else Vector())
        cam = camera("CAM_test_" + name, center + Vector(direction) * 1.0, (0, 0, 0), ortho=w / PX_M)
        look_at(cam, center)
        if name == "sole":  # toe on the image left
            cam.rotation_euler.z += math.pi
        result.append(render_image(cam, os.path.join(out, name + ".png"), w, h, 1, True))
    return result
