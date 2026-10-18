"""Shoe recipe M2: crossed laces (criss-cross) + dashed stitching from data panel edges."""
import math

import numpy as np
from mathutils import Vector

from ..geometry import world_bvh, catmull, mesh_obj, tube
from .shape import TONGUE_GAP, STITCH, R_LACE, LAST

# ---------------- lace ----------------
def _surface_top(bvh, x, y):
    hit = bvh.ray_cast(Vector((x, y, 400.0)), Vector((0, 0, -1)))
    return hit[0].z if hit[0] is not None else None


def _top_hull(s, z):
    """Upper convex hull (a taut lace over obstacles): monotone chain, then interpolated at s."""
    h = []
    for p in zip(s, z):
        while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) >= 0:
            h.pop()
        h.append(p)
    h = np.array(h)
    return np.interp(s, h[:, 0], h[:, 1])


def build_lace(B, hole, obs, mat, pk, down=0.0):
    """Crossed laces (criss-cross) like the original shoe: each hole is used ONCE. Front bar L0 -> R0 (both
    ends go into holes). Cross segments emerge from the tongue gap (below the eyestay edge, near hole k on side A),
    run taut over the tongue (upper convex hull of the surface + r + 0.5 mm), then enter hole k+1 on side B along
    its normal (2.2 mm). 'top' segments pass over 'bottom' segments (circular obstacle 2r + 0.4 mm)."""
    bvh = world_bvh(list(obs.values()))[0]
    Lp, Rp = hole["lateral"], hole["medial"]
    n = min(len(Lp), len(Rp))

    def gap(side, k):
        # a lace entering hole k runs under the eyestay to the gap and emerges ~4.5 mm toward the next hole
        # (not exactly at hole k's x: another bar/segment passes over that point)
        p = (Lp if side == "lateral" else Rp)[k][0].copy()
        p.x += 0.35 * B.hole[side]["distance"]
        cy, _ = B.plan(p.x)
        sg = 1 if side == "lateral" else -1
        y = cy + sg * (B.w(p.x) - TONGUE_GAP / 2)
        z_edge = B.z_top(p.x, cy + sg * B.w(p.x))
        return [Vector((p.x, y, z_edge - 3.5)), Vector((p.x, y, z_edge - 1.0)), Vector((p.x, y, z_edge + R_LACE + 0.6))]

    seg = [(None, Lp[0], Rp[0], "bar")]
    for k in range(n - 1):
        seg.append((gap("lateral", k), None, Rp[k + 1], "bottom"))
    for k in range(n - 1):
        seg.append((gap("medial", k), None, Lp[k + 1], "top"))
    path, bottom = [], []
    V, F = [], []
    for initial, la, (pb, nb), kind in seg:
        if initial is None:
            pa, na = la
            initial = [pa - na * 2.2, pa - na * 0.8, pa + na * 0.6, pa + na * (R_LACE + 0.9)]
        a_top, b_top = initial[-1], pb + nb * (R_LACE + 2.2)  # enter the hole straight along its axis (through the eyelet)
        d = b_top - a_top
        dxy = Vector((d.x, d.y, 0)).length
        ss = np.linspace(0.0, 1.0, max(int(dxy / 0.5), 16))
        z = np.empty(len(ss))
        for i, s_ in enumerate(ss):
            p = a_top + d * s_
            zs = _surface_top(bvh, p.x, p.y)
            z[i] = (zs if zs is not None else -1e3) + R_LACE + 0.8
            if kind == "top":
                for xyb, zb_ in bottom:
                    dist = np.hypot(xyb[:, 0] - p.x, xyb[:, 1] - p.y)
                    j = int(np.argmin(dist))
                    rr = 2 * R_LACE + 0.4
                    if dist[j] < rr:
                        z[i] = max(z[i], zb_[j] + math.sqrt(rr * rr - dist[j] ** 2))
        z[0], z[-1] = a_top.z, b_top.z
        z = _top_hull(ss, z) - down
        middle = [Vector(((a_top + d * s_).x, (a_top + d * s_).y, zi)) for s_, zi in zip(ss, z)]
        if kind in ("bottom", "bar"):
            bottom.append((np.array([(p.x, p.y) for p in middle]), np.array([p.z for p in middle])))
        control = initial[:-1] + middle + \
            [pb + nb * 2.0, pb + nb * 0.8, pb - nb * 0.6, pb - nb * 2.2]
        points = catmull(control, 2)
        path.append([tuple(p) for p in points])
        Vt, Ft = tube(points, R_LACE)
        o = len(V)
        V += Vt
        F += [tuple(i + o for i in f) for f in Ft]
    ob = mesh_obj("lace", np.array(V) / 1000.0, F, pk, mat["lace"])
    LAST["lace_path"] = path  # center line (mm) for QC AM-12
    return ob, dict(segment=len(seg), install=n)


# ---------------- stitching ----------------
def _offset_xz(poly, d, closed):
    """Offset an (x, z) polyline by d (positive = left of the travel direction). Points closer than 0.85 d to the original
    line (folds at notches/sharp tips) are dropped (None = break)."""
    P = np.array(poly, float)
    n = len(P)
    nrm = np.zeros_like(P)
    for i in range(n):
        a = P[i - 1] if (i or closed) else P[i]
        b = P[(i + 1) % n] if (i < n - 1 or closed) else P[i]
        t = b - a
        L = np.hypot(*t)
        nrm[i] = (-t[1] / L, t[0] / L) if L > 1e-9 else (0, 0)
    Q = P + nrm * d
    seg = np.stack([P, np.roll(P, -1, 0)], 1)
    if not closed:
        seg = seg[:-1]
    out = []
    for q in Q:
        ab = seg[:, 1] - seg[:, 0]
        t = np.clip(((q - seg[:, 0]) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-12), 0, 1)
        dist = np.hypot(*(seg[:, 0] + ab * t[:, None] - q).T).min()
        out.append(tuple(q) if dist >= 0.85 * abs(d) else None)
    return out


def _resample_xz(poly, step=0.25):
    out = [poly[0]]
    for a, b in zip(poly, poly[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        for k in range(1, max(int(L / step), 1) + 1):
            f = k / max(int(L / step), 1)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def build_stitching(B, obs, mud, ctx, mat, pk):
    """Dashed stitching 1.5 mm inside the mudguard edge (top) and around the swoosh. C-A6: the data edge line is
    offset 1.5 mm in the xz plane (the side wall is nearly vertical: xz offset ~ surface offset), folds at notches /
    sharp tips are dropped, then each point is mapped onto the analytic S on its side (y from height z) with the S
    normal (finite differences). The BVH version (queries right at the panel edge) gave random dashes along the mudguard edge."""
    J = STITCH
    V, F = [], []

    def points_S(x, z, side, lift):
        y = B.y_side(x, z, side)
        if y is None:
            return None
        p = Vector((x, y, z))
        ya, yb = B.y_side(x + 0.3, z, side), B.y_side(x, z + 0.3, side)
        if ya is None or yb is None:
            return None
        n = (Vector((0.3, ya - y, 0.0))).cross(Vector((0.0, yb - y, 0.3))).normalized()
        if (n.y > 0) != (side == "lateral"):
            n = -n
        return p + n * lift, n

    def dash(points):
        seg, acc, on, start, prev = [], 0.0, True, None, None
        for g in points:
            if g is None:
                prev = None
                continue
            if prev is None:
                start, on, acc = g, True, 0.0
            else:
                acc += (g[0] - prev[0]).length
                if on and acc >= J["dash"]:
                    seg.append((start, g))
                    on, acc = False, 0.0
                elif not on and acc >= J["pause"]:
                    on, acc, start = True, 0.0, g
            prev = g
        for (p0, n0), (p1, n1) in seg:
            t = (p1 - p0).normalized()
            n = (n0 + n1).normalized()
            u = n.cross(t).normalized()
            h, w = J["thickness"] / 2, J["width"] / 2
            corners = [c + u * su * w + n * sn * h for c in (p0, p1) for su, sn in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            o = len(V)
            V.extend(tuple(k) for k in corners)
            F.extend([(o, o + 1, o + 2, o + 3), (o + 7, o + 6, o + 5, o + 4), (o, o + 4, o + 5, o + 1),
                      (o + 1, o + 5, o + 6, o + 2), (o + 2, o + 6, o + 7, o + 3), (o + 3, o + 7, o + 4, o)])
        return len(seg)

    # mudguard: top line (toe -> heel), offset downward (right of travel direction = -d)
    mg = np.array(M_DATA_MUD(ctx, mud))
    line = _offset_xz(_resample_xz([tuple(p) for p in mg], 0.5), -J["offset"], False)
    n_mud = 0
    for side in ("lateral", "medial"):
        n_mud += dash([None if q is None else points_S(q[0], q[1], side, 0.1) for q in line])
    # swoosh: closed polygon (bottom toe->heel, top heel->toe = counterclockwise) -> inside = left
    n_sw = 0
    for side in ("lateral", "medial"):
        ob = obs[f"swoosh_{side}"]
        sw = np.array(ctx["panel"][side]["swoosh"], float)
        xsw = np.array(ob["polygon_data_x"])
        poly = [(x, z) for x, z in zip(xsw, sw[:, 1])] + [(x, z) for x, z in zip(xsw[::-1], sw[::-1, 2])]
        poly = _resample_xz(poly + [poly[0]], 0.25)[:-1]
        line = _offset_xz(poly, J["offset"], True)
        n_sw += dash([None if q is None else points_S(q[0], q[1], side, 0.3 + 0.1) for q in line])
    ob = mesh_obj("stitching", np.array(V) / 1000.0, F, pk, mat["lace"])
    ob["dash_mudguard"], ob["dash_swoosh"] = n_mud, n_sw
    return ob


def M_DATA_MUD(ctx, mud):
    """Top mudguard line (x, z) from toe to heel at the data x."""
    return [(x, mud(x)) for x in np.arange(12.36, 292.0, 0.5)]
