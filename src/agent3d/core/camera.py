"""Camera: azimuth/elevation direction, look-at, projecting points into the frame, fixed cameras, per-pixel rays."""
import math

import bpy
import numpy as np
from mathutils import Vector

from .scene import collection


def direction(az, el):
    """Unit vector: az degrees from -Y (camera direction) toward +X, el degrees of elevation."""
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def look_at(ob, target):
    ob.rotation_euler = (target - ob.location).to_track_quat("-Z", "Y").to_euler()


def projection(cam, pts):
    """Project world points to camera frame coordinates (0..1, y up) + depth. Same as world_to_camera_view."""
    sc = bpy.context.scene
    Mi = np.array(cam.matrix_world.normalized().inverted())
    loc = pts @ Mi[:3, :3].T + Mi[:3, 3]
    fr = cam.data.view_frame(scene=sc)
    fz = -fr[0].z
    z = -loc[:, 2]
    zs = np.where(np.abs(z) < 1e-9, 1e-9, z)
    x, y = loc[:, 0] * fz / zs, loc[:, 1] * fz / zs
    u = (x - fr[2].x) / (fr[1].x - fr[2].x)
    v = (y - fr[1].y) / (fr[0].y - fr[1].y)
    return u, v, z


def camera(name, hit_loc, rot, ortho=None, lens=50.0):
    """Camera in the CAMERAS collection (reused if it already exists): orthographic (ortho = width in m) or perspective."""
    kc = collection("CAMERAS")
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        kc.objects.link(cam)
    cam.location, cam.rotation_euler = hit_loc, rot
    if ortho:
        cam.data.type, cam.data.ortho_scale = "ORTHO", ortho
    else:
        cam.data.type, cam.data.lens = "PERSP", lens
    cam.data.clip_start, cam.data.clip_end = 0.001, 10.0
    return cam


def ray(cam, w, h, step):
    """Camera ray per pixel (perspective and orthographic). (x, y) pixel, row 0 = bottom (Blender PNG convention)."""
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = w, h
    fr = cam.data.view_frame(scene=sc)  # 0 right-top, 1 right-bottom, 2 left-bottom, 3 left-top
    Mw = cam.matrix_world.normalized()
    R = Mw.to_3x3()
    for y in range(0, h, step):
        for x in range(0, w, step):
            p = fr[2] + (fr[1] - fr[2]) * ((x + 0.5) / w) + (fr[3] - fr[2]) * ((y + 0.5) / h)
            if cam.data.type == "ORTHO":
                yield x, y, Mw @ Vector((p.x, p.y, 0.0)), (R @ Vector((0, 0, -1))).normalized()
            else:
                yield x, y, Mw.translation.copy(), (R @ p).normalized()


def uv_to_local(cam, u, v, distance):
    """Frame coordinates (u, v) -> point in camera local space at depth `distance` (view_frame already includes shift).
    Returns (point, frame width at that depth)."""
    fr = cam.data.view_frame(scene=bpy.context.scene)  # right-top, right-bottom, left-bottom, left-top
    s = distance / -fr[0].z
    x0, x1, y0, y1 = fr[2].x * s, fr[0].x * s, fr[2].y * s, fr[0].y * s
    return Vector((x0 + u * (x1 - x0), y0 + v * (y1 - y0), -distance)), (x1 - x0)
