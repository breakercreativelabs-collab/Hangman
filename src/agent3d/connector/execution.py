"""Runs INSIDE Blender via the single CLI (meta commands, not listed in `help`):

  blender -b [file.blend] --factory-startup -P blender_cli.py -- __run_code__ <folder_job>
  blender -b --factory-startup -P blender_cli.py -- __diagnose__ <file.json>

__run_code__ runs `code.py` in the job folder (MCP tool `run_code`: FREE-FORM Blender Python), then writes
`result.json`: ok, error (traceback), stdout, HASIL (optional variable set by the code), scene summary, saved file,
preview. The code has full access to Blender and the user's computer: the user approves every call in the Claude
app, and every code is saved in its job folder (audit trail + feedback material: frequently used code becomes a
tested verb).
"""
import contextlib
import io as _io
import json
import math
import os
import sys
import time
import traceback

import bpy
from mathutils import Vector

from ..core.io import write_json
from ..core.render import select_device, render_image
from .. import telemetry

MAX_STDOUT = 20000


def summarize_scene():
    sc = bpy.context.scene
    obs = list(sc.objects)
    kind = {}
    for o in obs:
        kind[o.type] = kind.get(o.type, 0) + 1
    example = [dict(name=o.name, kind=o.type, dimension_m=[round(x, 4) for x in o.dimensions],
                   location_m=[round(x, 4) for x in o.location]) for o in obs[:30]]
    return dict(file=bpy.data.filepath or "(not saved yet)", entity=len(obs), per_kind=kind, example=example,
                camera=sc.camera.name if sc.camera else None, frame=[sc.frame_start, sc.frame_end],
                engine=sc.render.engine, material=len(bpy.data.materials))


def _preview_camera():
    """The scene's active camera; if there is none, a temporary 3/4 camera framing all objects with geometry."""
    sc = bpy.context.scene
    if sc.camera:
        return sc.camera
    pts = [o.matrix_world @ Vector(c) for o in sc.objects if o.type in ("MESH", "CURVE", "SURFACE", "META", "FONT")
           for c in o.bound_box]
    if not pts:
        pts = [Vector((0, 0, 0))]
    lo = Vector([min(p[i] for p in pts) for i in range(3)])
    hi = Vector([max(p[i] for p in pts) for i in range(3)])
    center, r = (lo + hi) / 2, max((hi - lo).length / 2, 0.05)
    data = bpy.data.cameras.new("_PREVIEW")
    cam = bpy.data.objects.new("_PREVIEW", data)
    sc.collection.objects.link(cam)
    distance = r / math.tan(data.angle / 2) * 1.15
    direction = Vector((math.cos(math.radians(35)) * math.cos(math.radians(-50)),
                   math.cos(math.radians(35)) * math.sin(math.radians(-50)), math.sin(math.radians(25))))
    cam.location = center + direction.normalized() * distance
    cam.rotation_euler = (center - cam.location).to_track_quat("-Z", "Y").to_euler()
    data.clip_end = max(100.0, distance * 4)
    return cam


def render_preview(path, width=640):
    """Fast 640 px Cycles render (GPU if available); does not change the .blend file (called after saving)."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    select_device()
    sc.cycles.use_denoising = True
    if not any(o.type == "LIGHT" for o in sc.objects) and sc.world is None:
        sc.world = bpy.data.worlds.new("_PREVIEW")
    if sc.world and sc.world.use_nodes is False:
        sc.world.use_nodes = True
    cam = _preview_camera()
    rx, ry = max(sc.render.resolution_x, 1), max(sc.render.resolution_y, 1)
    height = max(int(width * ry / rx), 16)
    return render_image(cam, path, width, height, 16, False)


def run_code(argv):
    folder = os.path.abspath(argv[0])
    with open(os.path.join(folder, "permintaan.json"), encoding="utf-8") as f:
        req = json.load(f)
    with open(os.path.join(folder, "code.py"), encoding="utf-8") as f:
        source = f.read()
    t0, buf = time.time(), _io.StringIO()
    result = dict(ok=False)
    ns = {"__name__": "__main__", "__file__": os.path.join(folder, "code.py"), "bpy": bpy}
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(source, ns["__file__"], "exec"), ns)  # noqa: S102 - the whole point of run_code (approved by the user)
        result["ok"] = True
    except SystemExit as e:  # sys.exit(0)/sys.exit() in the code = normal finish; any other code = failed
        result["ok"] = e.code in (0, None)
        if not result["ok"]:
            result["error"] = f"SystemExit({e.code!r})"
    except BaseException:  # noqa: BLE001 - KeyboardInterrupt etc. are also reported as code errors
        result["error"] = traceback.format_exc()[-6000:]
    result["stdout"] = buf.getvalue()[-MAX_STDOUT:]
    if "HASIL" in ns:
        try:
            json.dumps(ns["HASIL"])
            result["HASIL"] = ns["HASIL"]
        except (TypeError, ValueError):
            result["HASIL"] = repr(ns["HASIL"])[:5000]
    if result["ok"] and req.get("save"):
        target = os.path.abspath(req["save"])  # C-10
        os.makedirs(os.path.dirname(target), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=target, compress=True)
        result["saved"] = target if os.path.isfile(target) else None
    result["scene"] = summarize_scene()
    if req.get("preview"):
        try:
            result["preview"] = render_preview(os.path.join(folder, "preview.png"))
        except Exception:  # noqa: BLE001 - preview is optional; its error is reported
            result["preview_error"] = traceback.format_exc()[-2000:]
    result["seconds"] = round(time.time() - t0, 2)
    write_json(os.path.join(folder, "result.json"), result)
    print("CODE", "OK" if result["ok"] else "FAIL", result["seconds"], "s")
    return 0 if result["ok"] else 1


def diagnose(argv):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    gpu = {}
    for t in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = t
        except TypeError:
            continue
        prefs.get_devices()
        name = [d.name for d in prefs.devices if d.type == t]
        if name:
            gpu[t] = name
    import numpy
    write_json(os.path.abspath(argv[0]), dict(blender=bpy.app.version_string, python=sys.version.split()[0],
                                          numpy=numpy.__version__, gpu=gpu, selected_device=next(iter(gpu), "CPU"),
                                          telemetry=telemetry.health()))
    return 0
