"""Live mode: the open Blender watches the live folder (written by `builder build --live 1`) and shows the
model step by step with a grow effect. No sockets/network: it only reads files.
Used by the extension's __init__.py (panel + preferences). License: GPL-3.0-or-later.
"""
import json
import os
import time

import bpy
import numpy as np

PAUSE = 0.35        # seconds between watcher ticks
GROW = 0.6       # seconds of grow effect per step
OBJ_NAME = "TONTON"
_state = dict(active=False, root="", since=0.0, folder="", job=None, obj=None, show=-1, grow_start=0.0)


def read_manifest(folder):
    """Manifest dict or None (missing, being written, corrupt); never raises."""
    try:
        with open(os.path.join(folder, "live.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d.get("step"), list) else None
    except (OSError, ValueError, AttributeError):
        return None


def latest_folder(root, since=0.0):
    """Subfolder of root (or root itself) whose manifest was modified most recently (and not before `since`);
    None if there is none."""
    candidate = [root] + [os.path.join(root, d) for d in sorted(os.listdir(root))] if os.path.isdir(root) else []
    candidate = [c for c in candidate if os.path.isfile(os.path.join(c, "live.json")) and
             os.path.getmtime(os.path.join(c, "live.json")) >= since]
    return max(candidate, key=lambda c: os.path.getmtime(os.path.join(c, "live.json")), default=None)


def mesh_npz(path, name):
    """Blender mesh from step_NN.npz (points in mm, quads), or None if the file is incomplete."""
    try:
        d = np.load(path)
        points, quad = d["points"].astype(np.float32) * 0.001, d["quad"].astype(np.int32)
    except Exception:  # noqa: BLE001 - half-written npz (BadZipFile, EOFError, ...): retry next tick
        return None
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(points))
    me.vertices.foreach_set("co", points.ravel())
    me.loops.add(quad.size)
    me.loops.foreach_set("vertex_index", quad.ravel())
    me.polygons.add(len(quad))
    me.polygons.foreach_set("loop_start", np.arange(0, quad.size, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(quad), 4, np.int32))
    me.update()
    me.validate()
    return me


def mesh_glb(path, name):
    """Mesh from model.glb (final step = handover mesh, identical to the headless result)."""
    if not os.path.isfile(path):
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    ob = next((o for o in new if o.type == "MESH"), None)
    me = None
    if ob:
        me = ob.data.copy()
        me.transform(ob.matrix_world)
        me.name = name
    for o in new:
        bpy.data.objects.remove(o)
    return me


def load_step(folder, item):
    path = os.path.join(folder, item["file"])
    return mesh_glb(path, item["name"]) if item["file"].endswith(".glb") else mesh_npz(path, item["name"])


def _free_slot(width):
    """Free X position to the right of all visible objects (a new model doesn't overlap older ones)."""
    xs = [max((o.matrix_world @ v.co).x for v in o.data.vertices) for o in bpy.context.view_layer.objects
          if o.type == "MESH" and o.visible_get() and len(o.data.vertices)]
    return (max(xs) + 0.25 * width + width / 2) if xs else 0.0


def display(me, name=None):
    """New job (name given): a NEW object next to the previous model. Later steps of the same job replace that object's
    mesh. Starts the grow effect. (Windows test 2026-10-17: a single TONTON object used to be overwritten by every job.)"""
    ob = bpy.data.objects.get(_state.get("obj") or "") if name is None else None
    if ob is None:
        xs = [v.co.x for v in me.vertices]
        width = (max(xs) - min(xs)) if xs else 0.0
        x = _free_slot(width)
        ob = bpy.data.objects.new(name or OBJ_NAME, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location.x = x
        _state["obj"] = ob.name
    else:
        old = ob.data
        ob.data = me
        if old.users == 0:
            bpy.data.meshes.remove(old)
    for p in me.polygons:
        p.use_smooth = True
    ob.scale = (1.0, 1.0, 0.05)
    _state["grow_start"] = time.time()
    return ob


def grow(ob, now):
    """Scale Z 0.05 -> 1 with ease-out over GROW seconds (the base sits at z = 0, so it grows from the bottom)."""
    t = min((now - _state["grow_start"]) / GROW, 1.0)
    ob.scale = (1.0, 1.0, 0.05 + 0.95 * (1 - (1 - t) ** 3))
    return t >= 1.0


def _frame(ob):
    """Show the model in Local View (only this model, zoomed in) without changing the user's scene.
    First Windows test 2026-10-17: a 53 mm pawn (real size) was hidden inside the default 2 m cube."""
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.clip_start = min(space.clip_start, 0.0005)  # millimeter-sized objects don't get clipped when zoomed in close
            region = next(r for r in area.regions if r.type == "WINDOW")
            with bpy.context.temp_override(window=win, area=area, region=region):
                if space.local_view is not None:  # local view from the previous job: exit first, then re-enter with the new model
                    bpy.ops.view3d.localview(frame_selected=False)
                bpy.ops.view3d.localview(frame_selected=True)
            return


def tick():
    """One watcher step (called by bpy.app.timers). One model step per tick so the process is visible."""
    if not _state["active"]:
        return None
    ob = bpy.data.objects.get(_state.get("obj") or "")
    if ob and not grow(ob, time.time()):
        return 0.03  # grow animation still running
    folder = latest_folder(_state["root"], _state["since"])
    if folder is None:
        return PAUSE
    d = read_manifest(folder)
    job = (folder, (d or {}).get("start"))
    if d is not None and job != _state.get("job"):  # new job (another project OR the same project rebuilt)
        _state.update(folder=folder, job=job, show=-1, obj=None)
    if d is None or _state["show"] + 1 >= len(d["step"]):
        return PAUSE
    i = _state["show"] + 1
    me = load_step(folder, d["step"][i])
    if me is None:
        return PAUSE  # file not ready: retry next tick
    ob = display(me, d.get("name", "model") if i == 0 else None)
    _state["show"] = i
    if i == 0:
        try:
            _frame(ob)
        except Exception:  # noqa: BLE001 - a framing failure must not stop the watcher
            pass
    print(f"[live] {os.path.basename(folder)} step {i + 1}/{len(d['step'])}: {d['step'][i]['name']}")
    return 0.03


def start(root, new_only=False):
    """Start watching `root` (the output/live folder in the workspace). new_only: ignore existing jobs
    (used on Blender startup so old jobs are not replayed)."""
    _state.update(active=True, root=root, since=time.time() if new_only else 0.0, folder="", job=None, show=-1)
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=0.1, persistent=True)


def stop():
    _state["active"] = False


def status():
    """Status text for the panel."""
    if not _state["active"]:
        return "live preview off"
    if not _state["folder"]:
        return "waiting for a model from Claude..."
    d = read_manifest(_state["folder"]) or {}
    n = len(d.get("step", []))
    return f"{d.get('name', '?')}: step {_state['show'] + 1}/{n}" + (" (done)" if d.get("done") else "")
