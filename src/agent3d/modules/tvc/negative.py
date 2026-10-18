"""TV QC negative tests: generic scene corruptors (selected and parameterized by tvc.toml [[negative]]) and file-based
negatives (black frame, unlisted flash, wrong video, white ink). The `required` checks MUST fail."""
import math
import os

import bpy
import numpy as np

from ...core.camera import uv_to_local
from ...core.qc import caught
from ...core.scene import fcurves
from . import config
from .key import key
from .production import build_tvc, encode_mp4
from .qc_image import qc_frame, qc_contrast, qc_video, render_contrast, test_res
from .qc_scene import qc_scene_tv
from .text import ink_material


# ---------------- scene corruptors (n = a [[negative]] entry in tvc.toml) ----------------
def marker_shift(n):
    """Shift the shot marker by `value` frames (wrong shot duration)."""
    m = next(m for m in bpy.context.scene.timeline_markers if m.name == n["shot"])
    m.frame += n["value"]


def dolly(n):
    """Multiply the shot camera distance by `value` (too close: product clipped)."""
    cam = bpy.data.objects["CAM_" + n["shot"]]
    for fc in fcurves(cam):
        if fc.data_path == "location":
            for k in fc.keyframe_points:
                k.co.y *= n["value"]
                k.handle_left.y *= n["value"]
                k.handle_right.y *= n["value"]


def flip(n):
    """Turn the shot camera to face out of the rig (away from the target)."""
    bpy.data.objects["CAM_" + n["shot"]].rotation_euler.z += math.pi


def shake(n):
    """Camera shake: a key every 2 frames in `span`, random +-`value` m (`seed`) on local x (BEZIER, not linear)."""
    cam = bpy.data.objects["CAM_" + n["shot"]]
    rng = np.random.default_rng(n["seed"])
    for f in range(n["span"][0], n["span"][1], 2):
        key(cam, "location", f, float(rng.uniform(-n["value"], n["value"])), "BEZIER", "AUTO", 0)


def wobble(n):
    """Camera rotation wobble: a key every 2 frames in `span`, random +-`value` deg (`seed`) on local z rotation (BEZIER)."""
    cam = bpy.data.objects["CAM_" + n["shot"]]
    rng = np.random.default_rng(n["seed"])
    for f in range(n["span"][0], n["span"][1], 2):
        key(cam, "rotation_euler", f, math.radians(180 + rng.uniform(-n["value"], n["value"])), "BEZIER", "AUTO", 2)


def jump(n):
    """Jump in the middle of a shot (fake cut/glitch): the rig azimuth jumps `value` deg at `frame`."""
    rig = bpy.data.objects["RIG_" + n["shot"]]
    sc = bpy.context.scene
    f = n["frame"]
    sc.frame_set(f - 1)
    az = rig.rotation_euler.z
    key(rig, "rotation_euler", f - 1, az, "CONSTANT", "AUTO", 2)
    sc.frame_set(f)
    key(rig, "rotation_euler", f, rig.rotation_euler.z + math.radians(n["value"]), "BEZIER", "AUTO", 2)


def misaligned_assembly(n):
    """Exploded part does not return: the last z key of the part empty is shifted by `value` m."""
    for fc in fcurves(bpy.data.objects["XP_" + n["part"]]):
        if fc.data_path == "location" and fc.array_index == 2:
            fc.keyframe_points[-1].co.y += n["value"]


def without_assembly(n):
    """All exploded parts stop in the exploded position (last key = previous key)."""
    for b in config.K["exploded"]["part"]:
        for fc in fcurves(bpy.data.objects["XP_" + b["name"]]):
            if fc.data_path == "location":
                kp = fc.keyframe_points
                kp[-1].co.y = kp[-2].co.y  # last key = exploded position
                kp[-1].handle_left.y = kp[-1].handle_right.y = kp[-2].co.y


def text_at_edge(n):
    """Shift the text right by `value` x frame width (leaves title-safe)."""
    ob = bpy.data.objects[n["text"]]
    _, width = uv_to_local(bpy.data.objects["CAM_" + config.K["text"]["shot"]], 0.5, 0.5, config.K["text"]["distance"])
    ob.location.x += n["value"] * width


def linear(n):
    """Set every key of the shot rig + camera to LINEAR."""
    for idb in (bpy.data.objects["RIG_" + n["shot"]], bpy.data.objects["CAM_" + n["shot"]]):
        for fc in fcurves(idb):
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"


def replace_material(n):
    """Replace the main material of a product entity with the text ink material (not a role material)."""
    bpy.data.objects[n["entity"]].data.materials[0] = bpy.data.materials["ink"]


CORRUPTOR = dict(marker_shift=marker_shift, dolly=dolly, flip=flip, shake=shake, wobble=wobble, jump=jump,
               misaligned_assembly=misaligned_assembly, without_assembly=without_assembly, text_at_edge=text_at_edge, linear=linear,
               product_material=replace_material)


def entries(select_text=""):
    """Project [[negative]] entries (filtered to names containing `select_text`)."""
    return [n for n in config.K.get("negative", []) if not select_text or select_text in n["name"]]


def scene_negatives(select, model=None):
    out = []
    for n in select:
        build_tvc("9x16", "test", model)
        CORRUPTOR[n["corruptor"]](n)
        bpy.context.view_layer.update()
        result, _ = qc_scene_tv("9x16")
        ok, failed = caught(result, n["required"])
        out.append(dict(name=n["name"], required_failed=n["required"], failed=failed, caught=ok,
                        value={f"{c['id']} {c['name']}": c["value"] for c in result if not c["passed"]}))
        print(("CAUGHT " if ok else "MISSED(!) ") + f"negative '{n['name']}': failed {failed}")
    return out


def image_negatives(folder, stat, flash, frames, model=None):
    """File-based negatives: black frame, unlisted flash, wrong video duration/fps, white text ink (contrast)."""
    out = []

    def record(name, result, required):
        ok, failed = caught(result, required)
        out.append(dict(name=name, required_failed=required, failed=failed, caught=ok,
                        value={f"{c['id']} {c['name']}": c["value"] for c in result}))
        print(("CAUGHT " if ok else "MISSED(!) ") + f"negative '{name}': failed {failed}")

    s = stat.copy()
    s[199] = (0.0, 0.0)
    record("frame 200 black", [qc_frame(s, flash, "9x16")], ["TV-03"])
    s = stat.copy()
    s[149, 0] = min(1.0, s[149, 0] + 0.45)
    record("unlisted flash at frame 150", [qc_frame(s, flash, "9x16")], ["TV-03"])
    record("listed flash removed from the list", [qc_frame(stat, {}, "9x16")], ["TV-03"])
    # wrong video: first 100 frames, 24 fps
    wrong = os.path.join(folder, "negative_video_24fps_100f.mp4")
    encode_mp4(os.path.dirname(frames[0]), wrong, *test_res("9x16"), fps=24, f0=1, f1=100)
    record("video 100 frames @ 24 fps", [qc_video(wrong, test_res("9x16"), "9x16")], ["TV-07"])
    # white ink: low contrast on the gradient background
    build_tvc("9x16", "test", model)
    ink_material(hexa="#FFFFFF")
    pa, pb = render_contrast(os.path.join(folder, "negative"), "9x16")
    record("white text ink", [qc_contrast(pa, pb, "9x16")], ["TV-06"])
    return out
