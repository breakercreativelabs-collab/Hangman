"""Spike: mimic a reference tree (inverse procedural modeling) via a silhouette score.

The reference tree is built with SECRET parameters + a different seed. The optimizer only
sees the silhouette (Workbench alpha render) and searches for the parameters with the highest IoU.
Claude does not look at an image each round; the IoU number leads.
  blender -b --factory-startup -P blender_cli.py -- procedural match [--out <folder>]   (default output/procedural)
"""
import json
import math
import os
import time

import bpy
import numpy as np

from ...core.material import make_material
from ...core.qc import iou
from ...core.render import select_device
from . import tree


def match(OUT):
    SECRET = dict(tree.PRESET["lush"], crown_radius=2.7, crown_thickness=3.4, crown_height=6.2)
    SEED_REF, CANDIDATE_SEED = 33, 7  # different seed: mimic the character, not a branch-by-branch clone
    FIND = ["crown_radius", "crown_thickness", "crown_height"]
    sc = bpy.context.scene


    def cleanup():
        for o in list(bpy.data.objects):
            if o.type != "CAMERA":
                bpy.data.objects.remove(o)
        for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.images):
            for d in list(coll):
                if d.users == 0:
                    coll.remove(d)


    def silhouette(params, seed, name):
        cleanup()
        tree.PRESET["test"] = params
        tree.build_tree("test", seed, 0.0)
        sc.render.filepath = os.path.join(OUT, f"_mask_{name}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        a = np.array(img.pixels[:], dtype=np.float32).reshape(img.size[1], img.size[0], 4)[:, :, 3] > 0.5
        bpy.data.images.remove(img)
        return a


    # orthographic front camera + transparent Workbench render (alpha = silhouette)
    cam = sc.camera
    cam.location, cam.rotation_euler = (0, -40, 5.5), (math.radians(90), 0, 0)
    cam.data.type, cam.data.ortho_scale = "ORTHO", 15
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.film_transparent = True
    sc.render.resolution_x = sc.render.resolution_y = 220
    sc.render.image_settings.file_format, sc.render.image_settings.color_mode = "PNG", "RGBA"

    t0 = time.time()
    ref = silhouette(SECRET, SEED_REF, "reference")
    guess = dict(tree.PRESET["lush"])  # starting point: the standard preset (not similar yet)
    step = {"crown_radius": 0.8, "crown_thickness": 0.8, "crown_height": 0.8}
    score = iou(ref, silhouette(guess, CANDIDATE_SEED, "candidate"))
    history = [round(score, 3)]
    evaluation = 1
    for turn in range(8):
        improved = False
        for k in FIND:
            for direction in (+1, -1):
                trial = dict(guess, **{k: max(0.5, guess[k] + direction * step[k])})
                s = iou(ref, silhouette(trial, CANDIDATE_SEED, "candidate"))
                evaluation += 1
                if s > score:
                    guess, score, improved = trial, s, True
                    break
        history.append(round(score, 3))
        if not improved:
            step = {k: v / 2 for k, v in step.items()}
            if max(step.values()) < 0.1:
                break

    best = silhouette(guess, CANDIDATE_SEED, "best")
    # silhouette comparison image: red = reference only, blue = guess only, white = match
    h, w = ref.shape
    rgb = np.zeros((h, w, 4), dtype=np.float32)
    rgb[..., 3] = 1
    rgb[ref & best] = (1, 1, 1, 1)
    rgb[ref & ~best] = (0.9, 0.2, 0.2, 1)
    rgb[~ref & best] = (0.2, 0.4, 0.95, 1)
    cmp = bpy.data.images.new("compare", w, h, alpha=True)
    cmp.pixels = rgb.ravel()
    cmp.filepath_raw, cmp.file_format = os.path.join(OUT, "match_silhouette.png"), "PNG"
    cmp.save()

    result = {
        "secret_parameters": {k: SECRET[k] for k in FIND},
        "initial_parameters": {k: tree.PRESET["lush"][k] for k in FIND},
        "guessed_parameters": {k: round(guess[k], 2) for k in FIND},
        "IoU_initial": history[0], "IoU_final": round(score, 3), "history_IoU": history,
        "evaluation_count": evaluation, "seconds": round(time.time() - t0, 1),
    }
    with open(os.path.join(OUT, "match_result.json"), "w") as f:
        json.dump(result, f, indent=1)
    print("RESULT " + json.dumps(result))

    # beauty render: reference (left) vs mimic (right)
    cleanup()
    tree.PRESET["ref"], tree.PRESET["mimic"] = SECRET, guess
    tree.build_tree("ref", SEED_REF, -5.0)
    tree.build_tree("mimic", CANDIDATE_SEED, 5.0)
    bpy.ops.mesh.primitive_plane_add(size=80)
    bpy.context.active_object.data.materials.append(make_material("ground", (0.16, 0.20, 0.10), 0.95))
    sun = bpy.data.objects.new("Matahari", bpy.data.lights.new("Matahari", "SUN"))
    sun.data.energy, sun.rotation_euler = 4.0, (math.radians(50), 0, math.radians(35))
    bpy.context.collection.objects.link(sun)
    bg = next(n for n in sc.world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs[0].default_value, bg.inputs[1].default_value = (0.55, 0.70, 0.95, 1), 0.9
    cam.data.type, cam.data.lens = "PERSP", 35
    cam.location, cam.rotation_euler = (0, -26, 5.5), (math.radians(87), 0, 0)
    sc.render.film_transparent = False
    sc.render.engine, sc.cycles.samples = "CYCLES", 96
    sc.cycles.transparent_max_bounces = 48
    select_device()  # GPU if available, otherwise CPU (the old spike forced OptiX)
    sc.render.resolution_x, sc.render.resolution_y = 1400, 720
    sc.render.image_settings.color_mode = "RGB"
    sc.render.filepath = os.path.join(OUT, "match_render.png")
    bpy.ops.render.render(write_still=True)
    for f in os.listdir(OUT):
        if f.startswith("_mask_"):
            os.remove(os.path.join(OUT, f))
