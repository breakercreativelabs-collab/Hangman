"""GENERIC panel QC (color-class data panel projects, Task 11): AM-10g projected IoU of each panel per side vs the data polygon.

AM1's AM-10 (swoosh) extended to all `[[model.panel]]` panels with base_width upper. Projection = rays along Y against that
side's panel object only (other objects ignored), 0.25 mm grid (panels < 1500 mm2) or 0.5 mm. Per-panel threshold = data
floor: IoU of the data polygon vs itself shifted (0.5; 0.5) mm (AM1 AM-10 rule: error <= half the data column spacing),
computed from data, not chosen. Tautological (the same data builds it): a build consistency check. Independent = AM-06 + eye.
"""
import bpy
import numpy as np

from ....core.qc import check, iou
from ..qc_silhouette import polygon_mask, ray_ob
from . import data
from .panel_data import specification


def polygon_raster(hs, vs, poly_list, shift=(0.0, 0.0)):
    """Polygons {outer, hole} (mm) -> grid mask (rows = vs, columns = hs), even-odd scanline (holes subtracted)."""
    m = np.zeros((len(vs), len(hs)), bool)
    for pg in poly_list:
        for loop in [pg["outer"]] + list(pg["hole"]):
            P = np.array(loop, float) + np.array(shift)
            A, B = P, np.roll(P, -1, 0)
            for i, v in enumerate(vs):
                crossing = ((A[:, 1] <= v) & (B[:, 1] > v)) | ((B[:, 1] <= v) & (A[:, 1] > v))
                if not crossing.any():
                    continue
                a, b = A[crossing], B[crossing]
                xs = np.sort(a[:, 0] + (v - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1]))
                for x0, x1 in zip(xs[0::2], xs[1::2]):
                    m[i] ^= (hs >= x0) & (hs < x1)
    return m


def qc_panel_iou():
    """Returns (AM-10 check list, artifacts {name_side: (model mask, data mask)})."""
    result, art = [], {}
    for sp in specification():
        if sp.get("base_width", "upper") != "upper":
            continue
        name = sp["name"]
        for side, sg in (("lateral", 1), ("medial", -1)):
            poly_list = data.class_panels(name, side)
            if not poly_list:
                continue
            P = np.vstack([np.array(pg["outer"], float) for pg in poly_list])
            area = sum(abs(0.5 * float(np.dot(Q[:, 0], np.roll(Q[:, 1], -1)) - np.dot(np.roll(Q[:, 0], -1), Q[:, 1])))
                       for Q in (np.array(pg["outer"], float) for pg in poly_list))
            r = 0.25 if area < 1500 else 0.5
            hs = np.arange(P[:, 0].min() - 2, P[:, 0].max() + 2, r) + r / 2
            vs = np.arange(P[:, 1].min() - 2, P[:, 1].max() + 2, r) + r / 2
            # data clipped to that side's silhouette: polygons deliberately extend past the silhouette edge (outer_mm) so
            # curved edges are covered; parts outside the silhouette have no surface to project onto
            sx, slo, shi = data.side_profile(side)
            crossing = polygon_mask(hs, vs, sx, slo, shi)
            d = polygon_raster(hs, vs, poly_list) & crossing
            floor = iou(d, polygon_raster(hs, vs, poly_list, (0.5, 0.5)) & crossing)
            obs = [o for o in bpy.context.scene.objects if o.get("panel") == name]
            m = np.zeros_like(d)
            for o in obs:  # panel object = L + M pieces; only hits on this half side count
                for i, z in enumerate(vs):
                    for j, x in enumerate(hs):
                        if m[i, j]:
                            continue
                        h = ray_ob(o, (x, sg * 300.0, z), (0, -sg, 0))
                        if h is not None and sg * (h[0].y - data.plan_y(min(max(x, 0.0), data.LENGTH))[0]) >= 0.0:
                            m[i, j] = True
            v = iou(m, d)
            result.append(check("AM-10", f"iou_{name}_{side}", v, v >= floor, f">= {floor:.4f} (data floor)",
                             f"{int(m.sum())} px model, {int(d.sum())} px data, {r} mm/px; floor = IoU of data vs data "
                             f"shifted (0.5; 0.5) mm" + ("" if obs else "; panel object missing")))
            art[f"{name}_{side}"] = (m, d)
    return result, art
