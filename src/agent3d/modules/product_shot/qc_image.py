"""Product shot numeric QC, image part (from render PNG): QC-05 dark/empty frame, QC-10 color, QC-12 metal."""
import colorsys
import os
import tempfile

import bpy
import numpy as np
from mathutils import Vector

from ...core.io import read_png, resize
from ...core.camera import projection
from ...core.qc import check
from ...core.scene import control, product_object, root as product_root
from .threshold import THRESHOLD
from .framing import frame_fill, use_camera
from .verbs import product_size


_PLAT = {}
VIS = ("camera", "diffuse", "glossy", "transmission", "volume_scatter", "shadow")


def clean_plate(cam):
    """Clean plate: small render (25%, 4 samples) of the scene WITHOUT the product, per camera + light preset + intensity.
    Used by QC-05 to separate the product from the backdrop gradient."""
    sc, c = bpy.context.scene, control()
    key = (cam.name, c["light_preset"], float(c["light_intensity"]), sc.render.resolution_x, sc.render.resolution_y)
    if key in _PLAT:
        return _PLAT[key]
    save = dict(path=sc.render.filepath, pct=sc.render.resolution_percentage, spp=sc.cycles.samples, cam=sc.camera)
    vis = {o.name: [getattr(o, "visible_" + k) for k in VIS] for o in product_object()}
    for o in product_object():
        for k in VIS:
            setattr(o, "visible_" + k, False)
    path = os.path.join(tempfile.gettempdir(), "hegemoni_plat", "_".join(str(x) for x in key) + ".png")
    sc.camera, sc.render.filepath = cam, path
    sc.render.resolution_percentage, sc.cycles.samples = 25, 4
    bpy.ops.render.render(write_still=True)
    for o in product_object():
        for k, v in zip(VIS, vis[o.name]):
            setattr(o, "visible_" + k, v)
    sc.render.filepath, sc.render.resolution_percentage, sc.cycles.samples, sc.camera = (
        save["path"], save["pct"], save["spp"], save["cam"])
    _PLAT[key] = read_png(path) @ np.array([0.2126, 0.7152, 0.0722], "f")
    return _PLAT[key]


def qc_histogram(path, cam):
    """QC-05: frame is not dark/empty. Luminance from the PNG; product contrast = difference from the clean plate
    in the product's projected box (the backdrop gradient does not count as product)."""
    rgb = read_png(path)
    L = rgb @ np.array([0.2126, 0.7152, 0.0722], "f")
    use_camera(cam)
    plat = clean_plate(cam)
    ph, pw = plat.shape
    Lk = resize(L, ph, pw)
    _, (u0, u1, v0, v1) = frame_fill(cam)
    box = Lk[max(0, int(v0 * ph)):int(np.ceil(v1 * ph)), max(0, int(u0 * pw)):int(np.ceil(u1 * pw))]
    plate_crop = plat[max(0, int(v0 * ph)):int(np.ceil(v1 * ph)), max(0, int(u0 * pw)):int(np.ceil(u1 * pw))]
    contrast = float(np.abs(box - plate_crop).mean()) if box.size else 0.0
    m = dict(mean_luma=float(L.mean()), black_fraction=float((L < 0.02).mean()), white_fraction=float((L > 0.98).mean()),
             product_contrast=contrast,
             histogram_8=[round(float(x), 4) for x in np.histogram(L, 8, (0, 1))[0] / L.size])
    A = THRESHOLD
    reason = []
    if not A["luma_min"] <= m["mean_luma"] <= A["luma_max"]:
        reason.append("mean luma out of range")
    if m["black_fraction"] > A["black_fraction_max"]:
        reason.append("too much black")
    if m["white_fraction"] > A["white_fraction_max"]:
        reason.append("too much clipped white")
    if m["product_contrast"] < A["product_contrast_min"]:
        reason.append("product not visible/blends into background (empty)")
    m = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in m.items()}
    return check("QC-05", "frame_not_dark_empty", m, not reason,
               f"luma {A['luma_min']}..{A['luma_max']}, black/white <= {A['black_fraction_max']}, "
               f"contrast >= {A['product_contrast_min']}", "; ".join(reason) or "ok")


def qc_color(path, cam, hexa):
    """QC-10: variant color is readable (not washed out/overexposed). 5x5 pixel sample at the front label point
    (hero frame), compared with the target hex in HSV."""
    root = product_root()
    if "color_points" not in root:
        return check("QC-10", "variant_color_readable", "n/a", True, "-", "product without color_points (import)")
    use_camera(cam)
    p = np.array(root.matrix_world @ Vector(root["color_points"]))[None]
    u, v, _ = projection(cam, p)
    rgb = read_png(path)
    h, w = rgb.shape[:2]
    x, y = int(u[0] * w), int(v[0] * h)
    pix = rgb[max(0, y - 2):y + 3, max(0, x - 2):x + 3].reshape(-1, 3).mean(0)
    hp, sp, vp = colorsys.rgb_to_hsv(*pix)
    ht, st, vt = colorsys.rgb_to_hsv(*[int(hexa.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    A = THRESHOLD
    if st < 0.2:
        d = abs(vp - vt)
        return check("QC-10", "variant_color_value_delta", float(d), d <= A["value_delta_max"],
                   f"<= {A['value_delta_max']} (neutral color)", f"{hexa} vs pixel {pix.round(3).tolist()}")
    ratio = sp / st
    dh = abs((hp - ht + 0.5) % 1.0 - 0.5) * 360
    return check("QC-10", "variant_color_saturation_ratio", float(ratio),
               ratio >= A["saturation_ratio_min"] and dh <= A["hue_delta_max"],
               f">= {A['saturation_ratio_min']} and hue delta <= {A['hue_delta_max']} deg",
               f"{hexa}: hue delta {dh:.1f} deg, pixel {pix.round(3).tolist()}")


def is_metal(m):
    """Product metal material (not label): Principled Metallic >= 0.5."""
    if not (m and m.node_tree) or m.name.startswith("LABEL"):
        return False
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    return bool(b) and b.inputs["Metallic"].default_value >= 0.5


def metal_pixels(path, cam, step=None):
    """Luminance of render pixels whose camera ray hits a product metal material (one ray per pixel in the product box).
    Returns (luma, relative hit height 0..1, normal z component) as arrays (may be empty).
    step=None: automatic, ~360 sample rows at any resolution (stays fast on final renders)."""
    sc = bpy.context.scene
    use_camera(cam)
    L = read_png(path) @ np.array([0.2126, 0.7152, 0.0722], "f")
    h, w = L.shape
    step = step or max(1, round(max(h, w) / 360))
    _, (u0, u1, v0, v1) = frame_fill(cam)
    fr = cam.data.view_frame(scene=sc)  # 0 right-top, 1 right-bottom, 2 left-bottom, 3 left-top (camera space)
    M, origin = cam.matrix_world.normalized(), cam.location
    dg = bpy.context.evaluated_depsgraph_get()
    product = {o.name for o in product_object()}
    result, height, nz = [], [], []
    H, _ = product_size()
    for y in range(max(0, int(v0 * h)), min(h, int(np.ceil(v1 * h))), step):
        for x in range(max(0, int(u0 * w)), min(w, int(np.ceil(u1 * w))), step):
            u, v = (x + 0.5) / w, (y + 0.5) / h
            p = fr[2] + (fr[1] - fr[2]) * u + (fr[3] - fr[2]) * v
            direction = (M.to_3x3() @ p).normalized()
            is_hit, loc, nor, idx, ob, _ = sc.ray_cast(dg, origin, direction)
            if not (is_hit and ob and ob.name in product):
                continue
            slot = ob.material_slots[ob.data.polygons[idx].material_index] if ob.material_slots else None
            if slot and is_metal(slot.material):
                result.append(L[y, x])
                height.append(loc.z / H)
                nz.append(nor.z)
    return np.array(result, "f"), np.array(height, "f"), np.array(nz, "f")


def qc_metal(path, cam):
    """QC-12 (C-15): product metal is not pitch black. Pixels whose camera ray hits a metal material
    (Metallic >= 0.5, not LABEL) and not the underside (normal z > -0.3; a can base is dark anyway):
    fraction with luma < 0.02. Upright metal with no reflection source in a dark preset = pitch-black band."""
    L, _, nz = metal_pixels(path, cam)
    L = L[nz > -0.3]
    if L.size < 30:
        return check("QC-12", "metal_dense_black", "n/a", True, "-", f"{L.size} metal pixels (< 30)")
    fr = float((L < 0.02).mean())
    a = THRESHOLD["metal_black_max"]
    return check("QC-12", "metal_black_fraction", fr, fr <= a, f"<= {a}",
               f"{L.size} metal pixels, median luma {float(np.median(L)):.3f}")
