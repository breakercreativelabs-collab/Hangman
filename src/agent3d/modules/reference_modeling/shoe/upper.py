"""Shoe recipe M2: the UPPER from data (reference + project panels), non-generative.

Called by sole.build_shoe() (upper="m2"). All numbers in mm; convention in data.py (X length from the toe tip, +Y lateral,
Z from the ground). Base shape S: shape.py; laces + stitching: lace.py.

Structure (C-A3: wavy M1 upper -> smooth base surface S):
- S = outer base surface: superellipse section loft per 1 mm station from the top silhouette, plan and midsole line,
  all SMOOTHED (Gauss). Raw data is stepped (photo quantization 0.23 mm/px) -> normals bend per station = waves.
- Layers = offsets of S along the normal (no two coincident surfaces, AM-13):
    upper (body + lining)  : solid, outer S-2.0
    panel_mesh (toe box/quarter/heel): shell S-1.5..S-1.0
    overlay (mudguard, eyestay, heel_overlay): shell S-0.7..S
    swoosh                   : shell S-0.7..S+0.3 (on top of the mesh; does not overlap the overlays)
  Panel = shell  ∩  region prism (xz polygon from data, extruded along Y per side).
- Collar opening (dark lining) + tongue gap cut from the top; collar edge cut to the data top silhouette (AM-01).
- Tongue, 7 lace hole pairs + eyelets, laces (2.5 mm tube, crossing over the tongue), dashed stitching.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from ..geometry import bevel_panel, boolean, loft_rings, grid_loft, loft_box, mesh_obj, normal_vertex, copy, torus
from ..filters import smoothstep
from . import data
from .shape import (OPENING_X, TONGUE_GAP, PANEL_GAP, GAP_DEPTH, HOLE_DEPTH, COLLAR_WALL, COLLAR_DROP, STEP,
                     OPENING_FLOOR, LAYERS, EYESTAY_WIDTH, TONGUE_DROP, N_PAIRS, R_HOLE, GAP_EDGE_DROP, LAST,
                     Shape, collar_line)
from .lace import build_stitching, build_lace


# ---------------- build upper M2 ----------------
def build_upper(ctx, mat, pk, smoothness=True, swoosh_shift_mm=0.0, swoosh_medial_from_lateral=False,
                 mudguard_shift_mm=0.0, lace_drop_mm=0.0, n_pairs=None, hole_shift_mm=0.0,
                 layer_gap=True, panel_param=None):
    """Build all M2 upper parts. Non-default parameters exist only for QC negative tests."""
    B = Shape(ctx, smoothness)
    L = data.LENGTH
    xs = list(np.arange(0.0, ctx["x_last"], STEP)) + [ctx["x_last"]] + list(np.linspace(ctx["x_last"], L, 4)[1:])
    if not smoothness:  # C-A3 negative: raw 1 mm stations (same as the M1 block)
        xs = list(np.unique(np.r_[np.arange(0.0, ctx["x_last"], 1.0), ctx["x_last"], np.linspace(ctx["x_last"], L, 4)]))
    rings = [[(x, y, z) for y, z in B.ring(x)] for x in xs]
    V0, F0 = grid_loft(rings)
    N0, F0 = normal_vertex(V0, F0)
    tmp = bpy.data.collections.new("_tmp_m2")
    bpy.context.scene.collection.children.link(tmp)

    def surface(d):
        return V0 + N0 * d

    def shell(name, d_in, d_out, collection):
        n = len(V0)
        V = np.vstack([surface(d_out), surface(d_in)])
        F = list(F0) + [tuple(i + n for i in f[::-1]) for f in F0]
        return mesh_obj(name, V / 1000.0, F, collection, recalc=False)

    def solid(name, d, collection):
        return mesh_obj(name, surface(d) / 1000.0, F0, collection)

    # ---- shared cutters ----
    x_t0 = B.x_t0
    x_b0, x_b1 = (data.map_x(v) for v in OPENING_X)
    w200 = B.w(x_b0)

    def h_opening(x):
        cy = B.plan(x)[0]
        y = B.y_side(x, B.zt(x), "lateral")
        if y is None:
            return 0.5
        hw = abs(y - cy) - COLLAR_WALL
        f = float(smoothstep(x_b0, x_b0 + 14.0, x))
        h = w200 + (hw - w200) * f
        R = 22.0
        if x > x_b1 - R:
            h *= math.sqrt(max(0.0, 1 - ((x - (x_b1 - R)) / R) ** 2))
        return max(h, 0.3)

    def floor(x):
        if x < x_b0:
            return B.zt(x) - GAP_DEPTH
        return B.mt(x) + OPENING_FLOOR

    xs_cut = list(np.arange(x_t0, x_b0, 0.5)) + [x_b0 - 0.01] + list(np.arange(x_b0, x_b1 - 0.2, 0.5)) + [x_b1 - 0.2]

    def fy_cut(x):
        cy, _ = B.plan(x)
        h = B.w(x) if x < x_b0 else h_opening(x)
        h = max(h, 0.3)
        return cy - h, cy + h

    cut_top = loft_box("_cut_top", xs_cut, fy_cut, lambda x: (floor(x), 400.0), tmp, mat["lining"])
    xs_full = list(np.arange(-5.0, L + 5.0, 0.5))

    xs0, xs1 = ctx["xs0"], ctx["xs1"]

    def clip(down):
        def fz(x):
            k = B.k_collar(x)
            # bottom: layers are cut 3 mm below the midsole line (hidden) within the sole span; this removes the dome
            # base where the inward offset folds (AM-13). Outside the sole (toe, heel back) nothing is cut.
            end = xs1 + data.model("upper", "end_clip_mm", -1.5)  # AM90: sole runs to the heel end -> cut up to the end
            bottom = B.mt(min(max(x, xs0), xs1)) - 3.0 if xs0 + 3 <= x <= end else -50.0
            return bottom, B.zt(min(max(x, 0.0), L)) + 0.3 * (1 - k) - down * k
        return loft_box("_clip", xs_full, lambda x: (-200.0, 200.0), fz, tmp, mat["lining"])

    obs = {}
    # ---- body upper (lining) ----
    up = solid("upper", LAYERS["upper"][1], pk)
    up["fold"] = True  # the 1.8 mm offset still folds slightly at the toe/heel base (hidden in the midsole): self-intersection
    up.data.materials.append(mat["lining"])
    boolean(up, cut_top, "DIFFERENCE", transfer=True)
    boolean(up, clip(0.0), "INTERSECT", delete=True)
    obs["upper"] = up

    # ---- panel mesh (A) ----
    d_in, d_out = LAYERS["panel_mesh"]
    if not layer_gap:  # negative AM-13: mesh layer coincides with the overlay
        d_in, d_out = -0.7, 0.0
    pm = shell("panel_mesh", d_in, d_out, pk)
    pm["fold"] = True
    pm.data.materials.append(mat["upper_mesh"])
    boolean(pm, cut_top, "DIFFERENCE", transfer=True)
    clip_l = clip(COLLAR_DROP)
    boolean(pm, clip_l, "INTERSECT")
    obs["panel_mesh"] = pm

    hole = {s: B.hole_position(s, n_pairs, hole_shift_mm) for s in ("lateral", "medial")}
    LAST["hole"] = {s: [tuple(p) for p, _ in hole[s]] for s in hole}
    LAST["hole_data"] = {s: B.hole[s]["data"] for s in hole}

    def e_bottom(x, side):
        cy = B.plan(x)[0]
        y = cy + (1 if side == "lateral" else -1) * (B.w(x) + EYESTAY_WIDTH)
        z = B.z_top(x, y)
        return z if z is not None else B.param(x)[3]

    def eyestay_region(side, dilate=0.0):
        xl = [p.x for p, _ in hole[side]]
        x0, x1 = max(min(xl) - 9.0, x_t0 + 1.0) - dilate, max(xl) + 9.0 + dilate
        R = 5.0
        xe = list(np.arange(x0, x1, 0.5)) + [x1]

        def fz(x):
            z = e_bottom(x, side) - dilate
            for xc, d in ((x0 + R, x0 + R - x), (x1 - R, x - (x1 - R))):
                if d > 0:
                    z += R * (1 - math.sqrt(max(0.0, 1 - (d / R) ** 2)))
            return z, 400.0
        sgn = 1 if side == "lateral" else -1
        return loft_box(f"_eyestay_region_{side}", xe,
                          lambda x: tuple(sorted((B.plan(x)[0], B.plan(x)[0] + sgn * 200.0))), fz, tmp)

    # lace holes: cylinders along the normal
    def cylinder(p, n, r, z0, z1, seg=20):
        a = Vector((1, 0, 0)) if abs(n.x) < 0.9 else Vector((0, 1, 0))
        u = n.cross(a).normalized()
        v = n.cross(u)
        V, F = [], []
        for z in (z0, z1):
            for j in range(seg):
                ang = 2 * math.pi * j / seg
                V.append(tuple(p + n * z + (u * math.cos(ang) + v * math.sin(ang)) * r))
        F = [(j, (j + 1) % seg, seg + (j + 1) % seg, seg + j) for j in range(seg)]
        F += [tuple(range(seg))[::-1], tuple(range(seg, 2 * seg))]
        return V, F

    Vh, Fh = [], []
    for side in hole:
        for p, n in hole[side]:
            V, F = cylinder(p, n, R_HOLE, -HOLE_DEPTH, 2.0)
            o = len(Vh)
            Vh += V
            Fh += [tuple(i + o for i in f) for f in F]
    holes = mesh_obj("_hole", np.array(Vh) / 1000.0, Fh, tmp, mat["lining"])

    if data.CLASS is not None:  # Task 11: panels from color-class data polygons (project.toml [[model.panel]])
        from .panel_data import build_panel_data
        obs.update(build_panel_data(B, shell, cut_top, clip_l, holes, pk, tmp, mat, **(panel_param or {})))
        boolean(pm, holes, "DIFFERENCE", transfer=True)
        boolean(up, holes, "DIFFERENCE", transfer=True)
    else:  # AM1 recipe: panels from luma data lines (mudguard, eyestay, heel overlay, swoosh)
        # ---- shared overlay shell (B) ----
        ov = shell("_overlay", *LAYERS["overlay"], tmp)
        ov.data.materials.append(mat["overlay_suede"])
        boolean(ov, cut_top, "DIFFERENCE", transfer=True)
        boolean(ov, clip_l, "INTERSECT")

        xs_mid = ctx["mid"][:, 0]

        def panel_bottom(x):
            """Panel bottom limit: 2 mm inside the midsole (embedded, not visible); in front of the sole = the whole toe."""
            if x < xs_mid[0] + 2:
                return -20.0 + (B.mt(xs_mid[0]) - 2 + 20.0) * float(smoothstep(xs_mid[0] - 2, xs_mid[0] + 2, x))
            return B.mt(min(x, xs_mid[-1])) - 2.0

        # mudguard: z <= lateral top mudguard line (medial assumed equal [D], as in extract_panel)
        mg = np.array(data.DATA["mudguard_top_line_lateral"], float)
        mud = lambda x: float(np.interp(x, mg[:, 0], mg[:, 1])) + mudguard_shift_mm
        mud_cut = loft_box("_mudguard_region", xs_full, lambda x: (-200.0, 200.0),
                                lambda x: (panel_bottom(x), mud(x)), tmp)
        mud_ob = copy(ov, "mudguard", pk)
        mud_ob.data.materials.clear()
        mud_ob.data.materials.append(mat["mudguard"])
        mud_ob.data.materials.append(mat["lining"])
        boolean(mud_ob, mud_cut, "INTERSECT", delete=True)
        obs["mudguard"] = mud_ob

        # eyestay per side
        for side in ("lateral", "medial"):
            es = copy(ov, f"eyestay_{side}", pk)
            boolean(es, eyestay_region(side), "INTERSECT", delete=True)
            boolean(es, holes, "DIFFERENCE", transfer=True)
            obs[f"eyestay_{side}"] = es
        boolean(pm, holes, "DIFFERENCE", transfer=True)
        boolean(up, holes, "DIFFERENCE", transfer=True)

        # heel/collar overlay: z >= line C per side (edge_line), minus the eyestay region (+ 0.4 mm gap)
        C = {s: collar_line(ctx["panel"][s]) for s in ("lateral", "medial")}
        c0 = max(C["lateral"][0][0], C["medial"][0][0])
        cyh = B.plan(285.0)[0]

        def fcin_collar(x):
            zl = float(np.interp(x, *C["lateral"]))
            zm = float(np.interp(x, *C["medial"]))
            return [(-200.0, zm), (cyh - 2.0, zm), (cyh + 2.0, zl), (200.0, zl), (200.0, 400.0), (-200.0, 400.0)]

        wk = loft_rings("_collar_region", list(np.arange(c0, L + 5.0, 0.5)), fcin_collar, tmp)
        ot = copy(ov, "heel_overlay", pk)
        boolean(ot, wk, "INTERSECT", delete=True)
        for side in ("lateral", "medial"):
            boolean(ot, eyestay_region(side, PANEL_GAP), "DIFFERENCE", delete=True)
        obs["heel_overlay"] = ot

        # ---- swoosh per side ----
        swc = shell("_swoosh", *LAYERS["swoosh"], tmp)
        swc.data.materials.append(mat["swoosh"])
        for side in ("lateral", "medial"):
            sw = np.array(ctx["panel"]["medial" if side == "medial" and not swoosh_medial_from_lateral else "lateral"]
                          ["swoosh"], float)
            xsw = sw[:, 0] + swoosh_shift_mm
            g = list(np.arange(xsw[0], xsw[-1], 0.25)) + [xsw[-1]]
            sgn = 1 if side == "lateral" else -1

            def fz(x, xsw=xsw, sw=sw):
                z0, z1 = float(np.interp(x, xsw, sw[:, 1])), float(np.interp(x, xsw, sw[:, 2]))
                if z1 - z0 < 0.1:
                    m = (z0 + z1) / 2
                    z0, z1 = m - 0.05, m + 0.05
                return z0, z1
            wsw = loft_box(f"_wil_swoosh_{side}", g, lambda x, sgn=sgn: tuple(sorted((B.plan(x)[0], B.plan(x)[0] + sgn * 200.0))),
                             fz, tmp)
            s_ob = copy(swc, f"swoosh_{side}", pk)
            boolean(s_ob, wsw, "INTERSECT", delete=True)
            obs[f"swoosh_{side}"] = s_ob
            s_ob["polygon_data_x"] = [float(v) for v in xsw]

    # ---- tongue ----
    def tongue_top(x):
        f = float(smoothstep(data.map_x(178.0), data.map_x(192.0), x))
        return (B.zt(x) - GAP_EDGE_DROP - TONGUE_DROP) * (1 - f) + B.zt(x) * f

    xl0 = x_t0 + 0.8
    xs_l = list(np.arange(xl0, x_b0 + 3.0, 0.5)) + [x_b0 + 3.0]
    z_gap_floor = lambda x: B.zt(min(x, x_b0 - 0.01)) - GAP_DEPTH

    def fcin_tongue(x):
        cy, _ = B.plan(min(x, x_b0))
        hw = max(B.w(min(x, x_b0 - 0.01)) - TONGUE_GAP, 0.3)
        zb, zt = z_gap_floor(x) + 0.5, tongue_top(x)
        R_tip = 0.45 * (zt - zb)  # rounded tongue back (not a slab)
        x_end = xs_l[-1]
        if x > x_end - R_tip:
            t = min((x - (x_end - R_tip)) / R_tip, 0.999)
            m_ = (zt + zb) / 2
            f = math.sqrt(1 - t * t)
            zt, zb = m_ + (zt - m_) * f, m_ - (m_ - zb) * f
        pts = []
        k = 1.5 / max(hw, 1.0) ** 2
        R = min(2.0, hw * 0.4, (zt - zb) * 0.3)
        for t in np.linspace(-1, 1, 15):  # curved top
            y = t * (hw - R)
            pts.append((cy - y, zt - k * y * y))
        for t in np.linspace(0, math.pi / 2, 5)[1:]:
            pts.append((cy - (hw - R) - R * math.sin(t), zt - k * (hw - R) ** 2 - R + R * math.cos(t)))
        pts.append((cy - hw, zb))
        pts.append((cy + hw, zb))
        for t in np.linspace(math.pi / 2, 0, 5)[:-1]:
            pts.append((cy + (hw - R) + R * math.sin(t), zt - k * (hw - R) ** 2 - R + R * math.cos(t)))
        return pts[::-1]

    li = loft_rings("tongue", xs_l, fcin_tongue, pk, mat["upper_mesh"])
    obs["tongue"] = li

    # ---- eyelets (chrome accent; [model.hole] eyelet = false: lace holes without metal rings, e.g. AM90) ----
    Ve, Fe = [], []
    for side in hole:
        for p, n in hole[side]:
            V, F = torus(p + n * 0.55, n, R_HOLE + 0.45, 0.45)
            o = len(Ve)
            Ve += V
            Fe += [tuple(i + o for i in f) for f in F]
    if data.model("hole", "eyelet", True):
        obs["eyelet"] = mesh_obj("eyelet", np.array(Ve) / 1000.0, Fe, pk, mat["chrome_accent"])

    # remove cutters
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)
    bpy.context.view_layer.update()

    # ---- lace ----
    obs["lace"], lace_info = build_lace(B, hole, obs, mat, pk, lace_drop_mm)
    # ---- stitching ----
    if data.CLASS is not None:
        from .panel_data import build_stitching_data
        jh = build_stitching_data(B, obs, mat, pk)
        panel = [o for o in obs.values() if o.get("panel")]
        if jh is not None:
            obs["stitching"] = jh
    else:
        obs["stitching"] = build_stitching(B, obs, mud, ctx, mat, pk)
        panel = [obs[k] for k in ("mudguard", "eyestay_lateral", "eyestay_medial", "heel_overlay", "swoosh_lateral",
                                  "swoosh_medial")]
    bevel_panel(panel)
    for name, ob in obs.items():
        for p in ob.data.polygons:
            p.use_smooth = name not in ("stitching",)
        # sharp boolean cut edges (90 degrees): smooth normals do not bleed into panel faces (lines/stripes)
        ob.data.set_sharp_from_angle(angle=math.radians(35))
    info = dict(hole={s: [[round(v, 2) for v in p] for p, _ in hole[s]] for s in hole},
                hole_data={s: B.hole[s]["data"] for s in hole}, x_gap=round(x_t0, 1),
                w_ref={k: round(v, 2) for k, v in B.w_ref.items()}, lace=lace_info,
                collar_line={s: [[float(a), round(float(b), 1)] for a, b in zip(*C[s])][::4] for s in C}
                if data.CLASS is None else {})
    return obs, B, info
