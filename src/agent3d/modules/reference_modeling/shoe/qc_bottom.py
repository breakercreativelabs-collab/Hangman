"""Shoe recipe QC M1 (bottom part): AM-01 side_view silhouette, AM-02 plan, AM-03 midsole line, AM-04 Air window,
AM-05 size, AM-06 medial silhouette (independent), AM-07 tread/banding, AM-08 midsole wall notch.
Each check = one row of the project QC_RULES.md (AM-xx). Axis convention: data.py."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ....core.io import read_rgba
from ....core.camera import camera
from ....core.qc import check
from ....core.render import render_image
from ....core.scene import product_object
from ..geometry import mm
from ..filters import opening, moving_average
from ..qc_silhouette import polygon_mask
from . import data
from .threshold import THRESHOLD, WINDOW_SEARCH, COLUMN_MIN, PIX, RAY, VIEW


# ---------------- orthographic render -> mask ----------------
def mask(view, folder):
    """Orthographic Cycles render (16 samples, transparent film), mask = alpha > 0.5. Row 0 = image bottom.
    Axes: side_view -> (x, z), camera at -Y; bottom -> (x, y), camera below, image top = -Y."""
    v = VIEW[view]
    (h0, h1), (v0, v1) = v["h"], v["v"]
    W, H = round((h1 - h0) / PIX), round((v1 - v0) / PIX)
    hc, vc = (h0 + h1) / 2, (v0 + v1) / 2
    if view == "side_view":
        cam = camera("CAM_ortho_side", (mm(hc), -0.6, mm(vc)), (math.pi / 2, 0, 0), mm(h1 - h0))
    else:
        cam = camera("CAM_ortho_bottom", (mm(hc), mm(vc), -0.6), (math.pi, 0, 0), mm(h1 - h0))
    path = render_image(cam, os.path.join(folder, f"mask_{view}.png"), W, H, 16, True)
    m = read_rgba(path)[..., 3] > 0.5
    hs = h0 + (np.arange(W) + 0.5) * PIX
    vs = v0 + (np.arange(H) + 0.5) * PIX
    if view == "bottom":
        vs = v1 - (np.arange(H) + 0.5) * PIX  # image top = -Y -> bottom row = +Y
    return m, hs, vs


def mask_data(view, hs, vs):
    """Data polygon rasterized on the same grid (x-monotone: bottom(x) <= v <= top(x))."""
    if view == "side_view":
        x, lo, hi = data.side_profile("lateral")
    elif view == "side_medial":
        x, lo, hi = data.side_profile("medial")
    else:
        x, lo, hi = data.plan_data_y()
    return polygon_mask(hs, vs, x, lo, hi)


# ---------------- side rays ----------------
def _ray(dg, x, z, side=1, y0=300.0):
    """Horizontal ray from the lateral (+Y, side=1) or medial (-Y) side. Returns the name of the first object hit, or None."""
    hit, _, _, _, ob, _ = bpy.context.scene.ray_cast(dg, Vector((mm(x), mm(side * y0), mm(z))),
                                                       Vector((0, -side, 0)))
    return ob.name if hit else None


def side_map(x0, x1, z0, z1, side=1, step=RAY):
    dg = bpy.context.evaluated_depsgraph_get()
    xs = np.arange(x0, x1, step) + step / 2
    zs = np.arange(z0, z1, step) + step / 2
    code = {"midsole": 1, "outsole": 2, "air_capsule": 4}
    mapping = np.zeros((len(zs), len(xs)), np.int8)
    for i, z in enumerate(zs):
        for j, x in enumerate(xs):
            name = _ray(dg, x, z, side)
            mapping[i, j] = 0 if name is None else code.get(name, 3)  # 3 = any upper/panel (AM-C07)
    return mapping, xs, zs


def measure_window(mapping, xs, zs):
    """Window column = first ray hit is the capsule or nothing, only inside WINDOW_SEARCH. A column counts when its height >= 3 mm."""
    x0, x1, z0, z1 = WINDOW_SEARCH
    window_mask = ((mapping == 4) | (mapping == 0)) & (zs[:, None] >= z0) & (zs[:, None] <= z1)
    coll = []
    for j, x in enumerate(xs):
        if not x0 <= x <= x1:
            continue
        z = zs[window_mask[:, j]]
        if len(z) * RAY >= COLUMN_MIN:
            coll.append((float(x), float(z.min()), float(z.max())))
    if not coll:
        return None, []
    k = np.array(coll)
    return (float(k[:, 0].min()), float(k[:, 0].max()), float(k[:, 1].min()), float(k[:, 2].max())), coll


def qc_window(mapping, xs, zs, side_name):
    d = data.data_window_bbox()
    m, coll = measure_window(mapping, xs, zs)
    a = THRESHOLD["window_mm"]
    if m is None:
        return check("AM-04", f"window_air_error_mm_{side_name}", 99.0, False, f"<= {a} mm", "window not found")
    g = dict(center_x=(m[0] + m[1]) / 2 - (d[0] + d[1]) / 2, center_z=(m[2] + m[3]) / 2 - (d[2] + d[3]) / 2,
             width=(m[1] - m[0]) - (d[1] - d[0]), height=(m[3] - m[2]) - (d[3] - d[2]))
    value = max(abs(v) for v in g.values())
    return check("AM-04", f"window_air_error_mm_{side_name}", value, value <= a, f"<= {a} mm (center x/z, width, height)",
               f"model x {m[0]:.1f}-{m[1]:.1f} z {m[2]:.1f}-{m[3]:.1f} vs data x {d[0]:.1f}-{d[1]:.1f} "
               f"z {d[2]:.1f}-{d[3]:.1f}; " + ", ".join(f"{k} {v:+.2f}" for k, v in g.items()))


def model_midsole_line(xs_data, z_data):
    """Top midsole line as SEEN from the lateral side: highest z where the first ray hit is the midsole (0.5 mm scan, then
    0.01 mm bisection). This is what the camera sees, so an upper bulging over the midsole lip is caught too."""
    dg = bpy.context.evaluated_depsgraph_get()
    result = []
    for x, zd in zip(xs_data, z_data):
        zs = np.arange(zd - 15.0, zd + 15.0, 0.5)
        is_hit = [_ray(dg, x, z) == "midsole" for z in zs]
        idx = [i for i in range(len(zs) - 1) if is_hit[i] and not is_hit[i + 1]]
        if not idx:
            result.append(np.nan)
            continue
        lo, hi = zs[idx[-1]], zs[idx[-1] + 1]
        while hi - lo > 0.01:
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _ray(dg, x, mid) == "midsole" else (lo, mid)
        result.append((lo + hi) / 2)
    return np.array(result)


def qc_midsole():
    mid, drop = data.midsole_line()
    zm = model_midsole_line(mid[:, 0], mid[:, 1])
    ok = ~np.isnan(zm)
    g = np.abs(zm[ok] - mid[ok, 1])
    value = float(g.mean()) if ok.any() else 99.0
    a = THRESHOLD["midsole_mm"]
    return check("AM-03", "midsole_top_line_mean_error_mm", value, ok.all() and value <= a, f"<= {a} mm",
               f"{ok.sum()}/{len(ok)} points, max {g.max():.2f} mm, median {np.median(g):.2f}; "
               f"{len(drop)} data outliers dropped (fixed rule |z - neighbor median| > 5 mm: "
               + ", ".join(f"x {p[0]:.1f} z {p[1]:.1f}" for p in drop) + ")"), (mid, zm)


def qc_size():
    dg = bpy.context.evaluated_depsgraph_get()
    p = []
    for ob in product_object():
        e = ob.evaluated_get(dg)
        v = np.empty(len(e.data.vertices) * 3)
        e.data.vertices.foreach_get("co", v)
        v = v.reshape(-1, 3) @ np.array(e.matrix_world)[:3, :3].T + np.array(e.matrix_world)[:3, 3]
        p.append(v)
    p = np.vstack(p) * 1000
    length = float(p[:, 0].max() - p[:, 0].min())
    front = p[p[:, 0] < p[:, 0].min() + length / 2]
    width = float(front[:, 1].max() - front[:, 1].min())
    sp, sl = data.LENGTH, data.LAB["forefoot_width_mm"]
    gp, gl = length - sp, width - sl
    return [check("AM-05", "length_error_mm", gp, abs(gp) <= THRESHOLD["length_mm"], f"|g| <= {THRESHOLD['length_mm']} mm",
                f"{length:.2f} vs {sp} mm [D] (calibration)"),
            check("AM-05", "forefoot_width_error_mm", gl, abs(gl) <= THRESHOLD["width_mm"], f"|g| <= {THRESHOLD['width_mm']} mm",
                f"{width:.2f} vs {sl} mm [F] lab RunRepeat")]


def model_midsole_base(xs):
    """BOTTOM midsole edge as visible from the lateral side: lowest z where the first ray hit is the midsole (0.5 mm scan,
    then 0.01 mm bisection). Notches in the sole base (C-A2) show up as upward spikes in this line."""
    dg = bpy.context.evaluated_depsgraph_get()
    result = []
    for x in xs:
        zs = np.arange(0.0, 60.0, 0.5)
        idx = next((i for i, z in enumerate(zs) if _ray(dg, x, z) == "midsole"), None)
        if not idx:
            result.append(np.nan)
            continue
        lo, hi = zs[idx - 1], zs[idx]
        while hi - lo > 0.01:
            mid = (lo + hi) / 2
            lo, hi = (lo, mid) if _ray(dg, x, mid) == "midsole" else (mid, hi)
        result.append((lo + hi) / 2)
    return np.array(result)


def qc_notch():
    """AM-08 (C-A2): notch in the midsole side wall = bottom midsole edge minus its lower hull
    (21 mm opening: narrow peaks removed, toe spring & heel bevel kept). Maximum depth."""
    mid, _ = data.midsole_line()
    xs = np.arange(mid[0, 0] + 3.0, mid[-1, 0] - 3.0, 1.0)
    z = model_midsole_base(xs)
    ok = ~np.isnan(z)
    a = THRESHOLD["notch_mm"]
    if ok.sum() < 10:
        return check("AM-08", "midsole_wall_notch_mm", 99.0, False, f"<= {a} mm", "midsole base not measurable")
    d = z[ok] - opening(xs[ok], z[ok])
    i = int(np.argmax(d))
    return check("AM-08", "midsole_wall_notch_mm", float(d[i]), d[i] <= a and ok.all(), f"<= {a} mm",
               f"{ok.sum()}/{len(ok)} x measured (1 mm), deepest at x {xs[ok][i]:.0f} mm; "
               f"{int((d > 0.5).sum())} x with notch > 0.5 mm")


def bottom_render_shaded(folder, floor):
    """Shaded bottom view on the same grid as the AM-02 mask (0.5 mm/px), floor hidden."""
    sc = bpy.context.scene
    v = VIEW["bottom"]
    (h0, h1), (v0, v1) = v["h"], v["v"]
    cam = camera("CAM_ortho_bottom", (mm((h0 + h1) / 2), mm((v0 + v1) / 2), -0.6), (math.pi, 0, 0), mm(h1 - h0))
    denoise, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    floor.hide_render = True
    path = render_image(cam, os.path.join(folder, "bottom_qc.png"), round((h1 - h0) / PIX), round((v1 - v0) / PIX), 24, False)
    floor.hide_render = False
    sc.cycles.use_denoising = denoise
    return path


def qc_tread(folder, m_bottom, floor):
    """AM-07 (C-A1) on the outsole in the bottom view (AM-02 mask eroded 10 mm, x 20-275 mm):
    banding = std of the per-column mean luma after subtracting a 15 mm moving average (vertical lines between
    stations / X-directional tread); tread = high-frequency luma std (luma - 2.5 mm blur), must be high enough for the
    pattern to read."""
    path = bottom_render_shaded(folder, floor)
    L = read_rgba(path)[..., :3] @ np.array([0.2126, 0.7152, 0.0722], "f")
    r = int(10 / PIX)
    inner = m_bottom.copy()
    for _ in range(r):
        inner = inner & np.roll(inner, 1, 0) & np.roll(inner, -1, 0) & np.roll(inner, 1, 1) & np.roll(inner, -1, 1)
    hs = VIEW["bottom"]["h"][0] + (np.arange(L.shape[1]) + 0.5) * PIX
    inner &= ((hs >= 20) & (hs <= 275))[None]
    # banding = sqrt(covariance) of column means, top half vs bottom half: lines between loft stations run across the
    # whole sole width (coherent), random tread texture does not (covariance ~0). Plain std mixes both (Voronoi 0.024 vs plain 0.009).
    coll = np.nonzero(inner.sum(0) >= 40)[0]
    hp = lambda c: c - moving_average(c, int(15 / PIX) | 1, 0)
    top, bottom = [], []
    for j in coll:
        i = np.nonzero(inner[:, j])[0]
        middle = (i.min() + i.max()) // 2
        top.append(L[i[i > middle], j].mean())
        bottom.append(L[i[i <= middle], j].mean())
    cov = float(np.mean(hp(np.array(top)) * hp(np.array(bottom))))
    compare = math.sqrt(max(cov, 0.0))
    blur = moving_average(moving_average(L, 5, 0), 5, 1)
    tread = float(np.std((L - blur)[inner]))
    return [check("AM-07", "bottom_column_banding", compare, compare <= THRESHOLD["banding_max"], f"<= {THRESHOLD['banding_max']}",
                f"{len(coll)} columns, mean outsole luma {float(L[inner].mean()):.3f}"),
            check("AM-07", "bottom_tread_contrast", tread, tread >= THRESHOLD["tread_min"], f">= {THRESHOLD['tread_min']}",
                f"{int(inner.sum())} px outsole")], path
