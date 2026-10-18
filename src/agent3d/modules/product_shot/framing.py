"""VERB 6 render_variants + camera framing per ratio (target frame fill, product centered)."""
import os

import bpy
from mathutils import Vector

from ...core.camera import direction, look_at, projection
from ...core.render import QUALITY
from ...core.scene import control, collection, product_points
from .verbs import RATIO


def frame_fill(cam, pts=None):
    u, v, _ = projection(cam, product_points() if pts is None else pts)
    return max(u.max() - u.min(), v.max() - v.min()), (u.min(), u.max(), v.min(), v.max())


def use_camera(cam):
    sc = bpy.context.scene
    q = QUALITY[sc.get("quality", "test")]
    w, h = RATIO[cam["ratio"]]
    sc.render.resolution_x, sc.render.resolution_y = round(w * q["scale"]), round(h * q["scale"])
    sc.camera = cam
    bpy.context.view_layer.update()


def framing(ratio, fill_target=0.70, elevation=8.0, lens=70.0):
    """Create/configure the camera for a ratio: distance is searched (bisection) so the product fills `fill_target`
    of the frame, then camera shift centers the product exactly."""
    name = "CAM_" + ratio.replace(":", "x")
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
        collection("CAMERAS").objects.link(cam)
    cam["ratio"] = ratio
    cd = cam.data
    cd.lens, cd.sensor_width, cd.sensor_fit = lens, 36.0, "AUTO"
    cd.shift_x = cd.shift_y = 0.0
    use_camera(cam)
    sc = bpy.context.scene
    sc.frame_set(sc.frame_start)
    pts = product_points()
    h = float(pts[:, 2].max())
    center = Vector((0, 0, h / 2))
    a = direction(0, elevation)
    lo, hi = 0.3 * h, 60 * h
    for _ in range(40):
        d = (lo + hi) / 2
        cam.location = center + a * d
        look_at(cam, center)
        bpy.context.view_layer.update()
        if frame_fill(cam, pts)[0] > fill_target:
            lo = d
        else:
            hi = d
    cd.clip_start, cd.clip_end = d * 0.05, d * 100
    _, (u0, u1, v0, v1) = frame_fill(cam, pts)
    w, hh = sc.render.resolution_x, sc.render.resolution_y
    cd.shift_x = ((u0 + u1) / 2 - 0.5) * w / max(w, hh)
    cd.shift_y = ((v0 + v1) / 2 - 0.5) * hh / max(w, hh)
    bpy.context.view_layer.update()
    control()["fill_target"] = fill_target
    return cam


def ratio_camera(ratio, fill_target):
    """Camera is framed once per ratio and reused across color/light variants (geometry does not change)."""
    cam = bpy.data.objects.get("CAM_" + ratio.replace(":", "x"))
    if cam is None or abs(cam.get("framed_fill", -1) - fill_target) > 1e-9:
        cam = framing(ratio, fill_target)
        cam["framed_fill"] = fill_target
    return cam


def render_variants(folder, prefix, ratio=("16:9", "9:16", "1:1"), frame=None, fill_target=0.70):
    """Render one still per ratio (camera CAM_16x9 / CAM_9x16 / CAM_1x1). Returns a list of render entries."""
    os.makedirs(folder, exist_ok=True)
    sc, result = bpy.context.scene, []
    for r in ratio:
        cam = ratio_camera(r, fill_target)
        use_camera(cam)
        f = sc.frame_start if frame is None else frame
        sc.frame_set(f)
        path = os.path.join(folder, f"{prefix}_{r.replace(':', 'x')}_f{f:03d}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        result.append(dict(file=path, ratio=r, camera=cam.name, frame=f, color=control()["hex_color"],
                          preset=control()["light_preset"]))
    return result
