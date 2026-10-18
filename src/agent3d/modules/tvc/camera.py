"""TVC cameras: one rig per shot (empty at the target + child camera facing it), distance found by bisecting frame fill,
a marker on each shot's first frame bound to its camera (cuts land on the beat). Per-shot plan: tvc.toml [camera.<shot>]."""
import math

import bpy
import numpy as np

from ...core.camera import projection
from ...core.scene import collection, product_points
from . import config
from .key import key


def camera_rig(name, target, lens):
    """Rig: empty RIG_<name> at the target, rotation (elevation, 0, azimuth); child camera at (0, distance, 0) facing local -Y
    (always looking at the target). az 0 = lateral side (+Y), positive az = toward the toe (-X)."""
    kc = collection("CAMERAS")
    rig = bpy.data.objects.new("RIG_" + name, None)
    kc.objects.link(rig)
    rig.location, rig.rotation_mode = target, "XYZ"
    cam = bpy.data.objects.new("CAM_" + name, bpy.data.cameras.new("CAM_" + name))
    kc.objects.link(cam)
    cam.parent = rig
    cam.rotation_euler = (math.radians(90), 0, math.radians(180))
    cam.data.lens, cam.data.sensor_width, cam.data.sensor_fit = lens, 36.0, "AUTO"
    cam.data.clip_start, cam.data.clip_end = 0.005, 20.0
    return rig, cam


def camera_pose(rig, cam, az, el, distance):
    rig.rotation_euler = (math.radians(el), 0.0, math.radians(az))
    cam.location = (0.0, distance, 0.0)
    bpy.context.view_layer.update()


def subject_points(step=7):
    """World-space product vertices (evaluated, every `step`-th vertex; enough for a projected bbox)."""
    return product_points()[::step]


def shot_frame(rig, cam, f_sample, az, el, contents, uv_center=(0.5, 0.5)):
    """Bisect the distance so the product fill, max(span u, span v) over the sample frames, equals `contents`; camera shift
    puts the product bbox center at `uv_center`. Used for the midpoint pose of the camera move."""
    sc = bpy.context.scene
    pts = []
    for f in f_sample:
        sc.frame_set(f)
        pts.append(subject_points(11))
    pts = np.concatenate(pts)
    cam.data.shift_x = cam.data.shift_y = 0.0
    lo, hi = 0.03, 6.0
    for _ in range(36):
        d = (lo + hi) / 2
        camera_pose(rig, cam, az, el, d)
        u, v, _ = projection(cam, pts)
        if max(u.max() - u.min(), v.max() - v.min()) > contents:
            lo = d
        else:
            hi = d
    u, v, _ = projection(cam, pts)
    w, h = sc.render.resolution_x, sc.render.resolution_y
    cam.data.shift_x = ((u.min() + u.max()) / 2 - uv_center[0]) * w / max(w, h)
    cam.data.shift_y = ((v.min() + v.max()) / 2 - uv_center[1]) * h / max(w, h)
    return d


def camera_plan(ratio):
    """Per-shot plan from the config, with per-ratio values already resolved."""
    out = {}
    for name, r in config.K["camera"].items():
        p = dict(target=config.target(r), lens=r["lens"], az=tuple(r["az"]), el=tuple(r["el"]))
        for k in ("distance", "k", "contents", "framing", "k_middle", "uv_center"):
            if k in r:
                p[k] = tuple(config.per_ratio(r[k], ratio)) if k != "contents" else config.per_ratio(r[k], ratio)
        out[name] = p
    return out


def place_camera(ratio):
    """One rig + camera per shot; a marker on each shot's first frame is bound to its camera (cuts land on the beat)."""
    sc = bpy.context.scene
    sc.timeline_markers.clear()
    rk, cams = camera_plan(ratio), {}
    for name, f0, f1 in config.shot_span():
        r = rk[name]
        rig, cam = camera_rig(name, r["target"], r["lens"])
        if "distance" in r:
            d0, d1 = r["distance"]
        else:
            d = shot_frame(rig, cam, r["framing"], sum(r["az"]) / 2, sum(r["el"]) / 2, r["contents"],
                             r.get("uv_center", (0.5, 0.5)))
            d0, d1 = d * r["k"][0], d * r["k"][1]
        for f, az, el, dd in ((f0, r["az"][0], r["el"][0], d0), (f1, r["az"][1], r["el"][1], d1)):
            key(rig, "rotation_euler", f, math.radians(el), "BEZIER", "AUTO", 0)
            key(rig, "rotation_euler", f, math.radians(az), "BEZIER", "AUTO", 2)
            key(cam, "location", f, dd, "BEZIER", "AUTO", 1)
        if "k_middle" in r:
            key(cam, "location", r["k_middle"][0], d * r["k_middle"][1], "BEZIER", "AUTO", 1)
        m = sc.timeline_markers.new(name, frame=f0)
        m.camera = cam
        cam["shot"], cam["ratio"] = name, ratio
        cams[name] = cam
    sc.camera = cams[config.K["shot"][0]["id"]]
    return cams
