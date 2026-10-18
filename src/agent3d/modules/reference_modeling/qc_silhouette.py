"""Generic QC for modeling from reference: mask IoU, data polygon rasterization, data vs model overlay, ray against a
single object, point-inside-mesh test, normal ripple, circular mean hue."""
import math

import numpy as np
from mathutils import Vector

from ...core import color
from ...core.io import save_image


def polygon_mask(hs, vs, x, lo, hi):
    """Rasterize an x-monotone data polygon (bottom(x) <= v <= top(x)) on a grid (hs columns, vs rows)."""
    LO, HI = np.interp(hs, x, lo), np.interp(hs, x, hi)
    inner_x = (hs >= x[0]) & (hs <= x[-1])
    V = vs[:, None]
    return (V >= LO[None]) & (V <= HI[None]) & inner_x[None]


def mask_overlay(m, d, path):
    """Light grey = model & data; blue = model only; red = data only (data contour vs model silhouette)."""
    rgb = np.full(m.shape + (3,), 0.10, "f")
    rgb[m & d] = (0.78, 0.78, 0.78)
    rgb[m & ~d] = (0.20, 0.45, 0.95)
    rgb[~m & d] = (0.95, 0.20, 0.15)
    edge = d & ~(np.roll(d, 1, 0) & np.roll(d, -1, 0) & np.roll(d, 1, 1) & np.roll(d, -1, 1))
    rgb[edge] = (0.95, 0.20, 0.15)  # data contour line
    return save_image(path, rgb, "ovl")


def ray_ob(ob, origin_mm, direction, smoothness=False):
    """Ray against ONE object (other objects ignored). Returns (world location in mm, world normal) or None.
    smoothness=True: shading normal (vertex normals interpolated, weight 1/distance), which is what the render shows; raw
    face normals contain facet jumps between loft rings (~3-6 degrees) that are not waves."""
    mw = ob.matrix_world
    inv = mw.inverted()
    o = inv @ (Vector(origin_mm) / 1000.0)
    d = (inv.to_3x3() @ Vector(direction)).normalized()
    ok, loc, nrm, fi = ob.ray_cast(o, d)
    if not ok:
        return None
    if smoothness:
        me = ob.data
        vs = me.polygons[fi].vertices
        w = [1.0 / ((me.vertices[i].co - loc).length + 1e-7) for i in vs]
        nrm = sum((me.vertices[i].normal * wi for i, wi in zip(vs, w)), Vector()) / sum(w)
    return (mw @ loc) * 1000.0, (inv.to_3x3().transposed() @ nrm).normalized()


def is_inside(bvh, q):
    """Point inside a closed mesh: parity of +Z ray hits (and -Z as a cross-check; both must be odd)."""
    result = []
    for direction in (Vector((0, 0, 1)), Vector((0.0123, 0.0071, -1)).normalized()):
        n, o = 0, q.copy()
        for _ in range(64):
            loc, _, _, _ = bvh.ray_cast(o, direction)
            if loc is None:
                break
            n += 1
            o = loc + direction * 1e-4
        result.append(n % 2 == 1)
    return all(result)


def ripple_deg(normal, window=15):
    """RMS angle between the normal and its moving average (`window` samples): ripple/waves between stations. Large
    smooth curvature barely contributes; 1-5 mm waves read in full."""
    N = np.array(normal)
    k = np.ones(window) / window
    mean = np.stack([np.convolve(np.pad(N[:, i], window // 2, mode="edge"), k, "valid") for i in range(3)], 1)
    mean /= np.linalg.norm(mean, axis=1, keepdims=True)
    angle = np.degrees(np.arccos(np.clip((N * mean).sum(1), -1, 1)))
    return float(np.sqrt(np.mean(angle[window // 2:-(window // 2)] ** 2)))


def mean_hue(px):
    """Circular mean hue (saturation-weighted) of pixels (n, 3) -> (hue 0..1, count of pixels with saturation >= 0.15)."""
    hsv = np.array([color.hsv(p) for p in px])
    use = hsv[:, 1] >= 0.15
    if use.sum() < 30:
        return float("nan"), int(use.sum())
    a = hsv[use, 0] * 2 * math.pi
    wgt = hsv[use, 1]
    return (math.atan2((np.sin(a) * wgt).sum(), (np.cos(a) * wgt).sum()) / (2 * math.pi)) % 1.0, int(use.sum())
