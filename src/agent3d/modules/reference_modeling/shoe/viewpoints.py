"""Eye-check renders of the shoe recipe (views, P3 studio), role swatches, data vs model overlays (heel, mudguard)."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ....core.io import save_image
from ....core.camera import look_at, camera
from ....core.render import render_image
from ....core.color import hex_rgb
from ..qc_silhouette import ray_ob
from . import data
from .threshold import RAY
from .qc_bottom import measure_window
from .qc_upper import find_object
from .studio import use_studio


def render_p3(folder):
    """Eye-check renders in the P3 studio: hero 3/4, side left/right, capsule macro, mesh/suede macro. Exposure -0.5
    (AM-C02: bright pastels blend together/flatten in Khronos PBR Neutral at exposure 0)."""
    sc = bpy.context.scene
    use_studio("p3")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", -0.5
    denoise, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    center = Vector((0.147, 0.0, 0.06))
    cams = {
        "p3_hero": (camera("CAM_p3_hero", (-0.16, 0.36, 0.17), (0, 0, 0), lens=50), center, 720, 480),
        "p3_lateral": (camera("CAM_p3_lat", (0.147, 0.55, 0.075), (0, 0, 0), lens=50), Vector((0.147, 0, 0.06)), 640, 360),
        "p3_medial": (camera("CAM_p3_med", (0.147, -0.55, 0.075), (0, 0, 0), lens=50), Vector((0.147, 0, 0.06)), 640, 360),
        "p3_macro_capsule": (camera("CAM_p3_cap", (0.235, 0.15, 0.04), (0, 0, 0), lens=70), Vector((0.2163, 0.045, 0.02)), 480, 320),
        "p3_macro_mesh": (camera("CAM_p3_mesh", (0.035, 0.12, 0.085), (0, 0, 0), lens=70), Vector((0.07, 0.04, 0.045)), 480, 320),
    }
    out = {}
    lamp = [o for o in bpy.data.objects if o.name.startswith("P3_") and o.type == "LIGHT"]
    origin = {o.name: o.location.copy() for o in lamp}
    for name, (cam, t, w, h) in cams.items():
        look_at(cam, t)
        for o in lamp:  # key always on the camera side, rim opposite (medial = mirrored Y)
            p = origin[o.name]
            o.location = (p.x, p.y if cam.location.y >= 0 else -p.y, p.z)
            look_at(o, Vector((0.147, 0.0, 0.05)))
        out[name] = render_image(cam, os.path.join(folder, f"{name}.png"), w, h, 32, False)
    for o in lamp:
        o.location = origin[o.name]
        look_at(o, Vector((0.147, 0.0, 0.05)))
    sc.cycles.use_denoising = denoise
    use_studio("review")
    return out


def swatch_png(folder, swatch):
    """One PNG per role: left = target P3 hex, right = neutral render median (AM-15)."""
    out = {}
    for role, (hexa, med, _) in swatch.items():
        rgb = np.zeros((60, 120, 3), "f")  # display values (sRGB) directly, same as read_png returns
        rgb[:, :60] = hex_rgb(hexa)
        rgb[:, 60:] = med
        out[role] = save_image(os.path.join(folder, f"swatch_{role}.png"), rgb, "ovl")
    return out


# ---------------- overlay images ----------------
def heel_overlay(art, path):
    """Lateral object map (heel) + data top midsole line (red) + data window columns (yellow) + model bbox (cyan)."""
    mapping, xs, zs = art["mapping"]
    color = np.array([(0.10, 0.10, 0.10), (0.88, 0.88, 0.86), (0.35, 0.35, 0.36), (0.55, 0.55, 0.58),
                      (0.45, 0.70, 1.00)], "f")
    rgb = color[mapping]
    ij = lambda x, z: (int((z - zs[0]) / RAY + 0.5), int((x - xs[0]) / RAY + 0.5))

    def points(x, z, c, r=1):
        i, j = ij(x, z)
        if 0 <= i < rgb.shape[0] and 0 <= j < rgb.shape[1]:
            rgb[max(i - r, 0):i + r + 1, max(j - r, 0):j + r + 1] = c
    mid, _ = art["midsole"]
    for x, z in mid:
        points(x, z, (0.95, 0.15, 0.15))
    jx, jb, jt = data.data_window()
    for x, b, t in zip(jx, jb, jt):
        points(x, b, (1.0, 0.85, 0.1))
        points(x, t, (1.0, 0.85, 0.1))
    m, _ = measure_window(mapping, xs, zs)
    if m:
        for x in np.arange(m[0], m[1], RAY):
            points(x, m[2], (0.1, 0.9, 0.9), 0)
            points(x, m[3], (0.1, 0.9, 0.9), 0)
        for z in np.arange(m[2], m[3], RAY):
            points(m[0], z, (0.1, 0.9, 0.9), 0)
            points(m[1], z, (0.1, 0.9, 0.9), 0)
    return save_image(path, rgb, "ovl")


def render_views(folder, only=None):
    """Eye-check views (Cycles CPU test). Exposure -1 only here (AM-C02: a white model blends into the background);
    the AM-07 QC render stays at exposure 0."""
    sc = bpy.context.scene
    use_studio("review")
    sc.cycles.samples, sc.cycles.use_denoising = 24, True
    sc.view_settings.view_transform = "Khronos PBR Neutral"
    exp_prev, sc.view_settings.exposure = sc.view_settings.exposure, -1.0
    out = {}
    px = data.model("viewpoints", "center_x_mm", 147.0) / 1000  # middle of the shoe length (AM1 0.147 m)
    jx, jz = (v / 1000 for v in data.model("viewpoints", "window_xz_mm", [216.3, 19.0]))  # window macro center
    center = Vector((px, 0.0, 0.06))
    cams = {  # name: (camera, w, h, target); positions relative to the shoe middle (AM1 values stay identical)
        "side_lateral": (camera("CAM_side", (px, 0.6, 0.068), (math.pi / 2, 0, math.pi), 0.32), 640, 340, None),
        "side_medial": (camera("CAM_side_m", (px, -0.6, 0.068), (math.pi / 2, 0, 0), 0.32), 640, 340, None),
        "three_quarter": (camera("CAM_34", (px - 0.317, 0.33, 0.23), (0, 0, 0), lens=50), 640, 420, center),
        "three_quarter_back": (camera("CAM_34b", (px + 0.313, -0.26, 0.24), (0, 0, 0), lens=50), 640, 420, center),
        "top": (camera("CAM_top", (px, 0.0, 0.6), (0, 0, 0), 0.32), 640, 300, None),
        "macro_swoosh": (camera("CAM_m_sw", (0.205, 0.20, 0.10), (0, 0, 0), lens=60), 640, 420,
                         Vector((0.205, 0.04, 0.078))),
        "macro_lace": (camera("CAM_m_lace", (0.10, 0.16, 0.22), (0, 0, 0), lens=60), 640, 420,
                       Vector((0.145, 0.0, 0.112))),
        "macro_window": (camera("CAM_macro", (jx - 0.0113, 0.17, jz + 0.026), (0, 0, 0), lens=60), 640, 420,
                          Vector((jx, 0.045, jz))),
    }
    for name, (cam, w, h, t) in cams.items():
        if only and name not in only:
            continue
        if t is not None:
            look_at(cam, t)
        out[name] = render_image(cam, os.path.join(folder, f"{name}.png"), w, h, 24, False)
    sc.view_settings.exposure = exp_prev
    return out


def overlay_mudguard(art_m, path):
    """Lateral projection of the mudguard object (grey) + data top line (red) + measured model top line (cyan), x 0-296."""
    ob = find_object("mudguard")
    xs = np.arange(0.0, 296.0, 0.5) + 0.25
    zs = np.arange(0.0, 100.0, 0.5) + 0.25
    rgb = np.full((len(zs), len(xs), 3), 0.10, "f")
    if ob is not None:
        for i, z in enumerate(zs):
            for j, x in enumerate(xs):
                if ray_ob(ob, (x, 300.0, z), (0, -1, 0)) is not None:
                    rgb[i, j] = (0.55, 0.55, 0.57)

    def points(x, z, c):
        i, j = int(z / 0.5), int(x / 0.5)
        if 0 <= i < rgb.shape[0] and 0 <= j < rgb.shape[1]:
            rgb[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2] = c
    mg = np.array(data.DATA["mudguard_top_line_lateral"], float)
    for x in np.arange(mg[0, 0], mg[-1, 0], 0.25):
        points(x, float(np.interp(x, mg[:, 0], mg[:, 1])), (0.95, 0.15, 0.15))
    if art_m is not None:
        for x, _, z in zip(*art_m):
            if not np.isnan(z):
                points(x, z, (0.1, 0.9, 0.9))
    return save_image(path, rgb, "ovl")
