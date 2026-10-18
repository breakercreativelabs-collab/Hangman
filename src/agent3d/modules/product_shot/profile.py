"""Test product geometry: lathe (lathe_profile), per-product profiles, plates, non-circular sections.
All profiles in mm (r, z) from specification.SPEC."""
import math

import bpy

def lathe_profile(name, profile, seg=96, modulation=None, section=None, uv_arc=True):
    """Lathe: profile (r_mm, z_mm) revolved around the Z axis. A point with r=0 becomes a single vertex on the axis.
    section(t, r, z) -> (x_mm, y_mm): non-circular section (rounded box, flat tube); default is a circle.
    C-13: on non-circular sections, label u = arc length from the front / perimeter (not angle), so the logo
    keeps a constant width on the surface (a flattening tube does not make the logo trapezoidal)."""
    vs, ring, arc = [], [], {}
    for r, z in profile:
        if r == 0:
            ring.append([len(vs)])
            vs.append((0.0, 0.0, z / 1000))
            continue
        idx = []
        for k in range(seg):
            t = 2 * math.pi * k / seg
            if section:
                x, y = section(t, r, z)
            else:
                rr = r * (modulation(t, z) if modulation else 1.0)
                x, y = rr * math.cos(t), rr * math.sin(t)
            idx.append(len(vs))
            vs.append((x / 1000, y / 1000, z / 1000))
        ring.append(idx)
        if section and uv_arc:  # apparent angle = 2 pi x (arc from front, t = 270 degrees) / perimeter
            L = [0.0]
            for k in range(1, seg + 1):
                (x0, y0, _), (x1, y1, _) = vs[idx[k - 1]], vs[idx[k % seg]]
                L.append(L[-1] + math.hypot(x1 - x0, y1 - y0))
            P, kf = L[-1], 3 * seg // 4
            for k in range(seg):
                d = (L[k] - L[kf]) / P
                arc[idx[k]] = 2 * math.pi * (d - round(d))
    fs = []
    for a, b in zip(ring, ring[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            fs += [(a[0], b[(k + 1) % seg], b[k]) for k in range(seg)]  # reversed order: normal points outward (bottom)
        elif len(b) == 1:
            fs += [(a[k], a[(k + 1) % seg], b[0]) for k in range(seg)]
        else:
            fs += [(a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k]) for k in range(seg)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.validate()
    # label UV: u = 0.5 + angle/(2 pi) with angle 0 at front (-Y), v = height (m). The logo travels with the mesh on export/import.
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        pc = poly.center
        sc_ = math.atan2(pc.x, -pc.y)
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            vi = me.loops[li].vertex_index
            a = sc_ if math.hypot(co.x, co.y) < 1e-9 else arc.get(vi, math.atan2(co.x, -co.y))
            a += 2 * math.pi * round((sc_ - a) / (2 * math.pi))  # open the seam at the back
            uv.data[li].uv = (0.5 + a / (2 * math.pi), co.z)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35))
    return me


def can_profile(s):
    H, R = s["height_mm"], s["diameter_mm"] / 2
    rc, rp, k = s["base_ring_mm"] / 2, s["plug_mm"] / 2, s["dome_mm"]
    zb = H - s["neck_mm"]  # end of straight body
    # neck: standard can narrows 6.9 mm (2 points); slim can 202 only 1.7 mm (1 point, still descending)
    neck = [(R - 1.2, zb + 4), (rp + 3.5, zb + 9.5)] if R - rp > 5 else [(R - 0.6, zb + 4)]
    return [(0, k), (rc - 5, 3.0), (rc - 1.2, 0.5), (rc, 0), (rc + 1.4, 0.6), (R - 3.5, 4.5), (R - 0.8, 8.5),
            (R, 11.0), (R, zb)] + neck + [(rp + 0.9, H - 4.2),
            (rp + 0.8, H - 2.2), (rp + 1.6, H - 0.6), (rp + 1.4, H), (rp + 0.2, H),  # lid seam rim [D]
            (rp - 0.4, H - 5.8), (rp - 1.6, H - 6.3), (0, H - 6.0)]  # recessed lid panel [D]


def bottle_profile(s):
    H, R, rf = s["height_mm"], s["diameter_mm"] / 2, s["crown_mm"] / 2
    zb, zl = s["body_height_mm"], s["neck_height_mm"]
    rl = rf - 0.6  # neck slightly smaller than the crown finish
    return [(0, 3.0), (R - 7, 0.9), (R - 4, 0), (R - 1.2, 1.2), (R, 4.5), (R, zb),
            (R - 1.5, zb + 10), (R - 6.5, zb + 24), (rl + 6.5, zb + 38), (rl + 1.5, zl - 4), (rl, zl),
            (rl, H - 12), (rf + 0.3, H - 10.5), (rf + 0.3, H - 7.5), (rf - 0.2, H - 6.5),
            (rf, H - 3), (rf - 0.6, H), (0, H)]


def inner_bottle_profile(s):
    """Inner glass wall (down from mouth to base). C-11: hollow bottle, not solid glass."""
    H, R, rl = s["height_mm"], s["diameter_mm"] / 2, s["crown_mm"] / 2 - 0.6
    zb, zl, t = s["body_height_mm"], s["neck_height_mm"], s["wall_mm"]
    bore = s["crown_mm"] / 2 - 4.2  # mouth bore [D]
    return [(bore, H), (bore, H - 9.0), (rl - t, H - 12), (rl - t, zl), (rl + 1.5 - t, zl - 4),
            (rl + 6.5 - t, zb + 38), (R - 6.5 - t, zb + 24), (R - 1.5 - t, zb + 10), (R - t, zb),
            (R - t, 9.0), (R - 5.0, 6.6), (R - 10.0, 6.0), (0, 6.2)]


def liquid_from(inner, zi, gap=0.15, z_base=10.0):
    """Fill (liquid/jam) following the inner wall `inner` (downward, ending at base (0, z)) with a thin gap
    up to height `zi`. The surface radius is interpolated on the wall segment that crosses `zi`."""
    up = [(r, z) for r, z in reversed(inner) if 0 < r]
    z0 = inner[-1][1]
    p = [(0, z0 + gap)] + [(r - gap, z + (gap if z < z_base else 0)) for r, z in up if z < zi]
    (ra, za), (rb, zb) = next((a, b) for a, b in zip(up, up[1:]) if a[1] < zi <= b[1])
    r_fill = ra + (rb - ra) * (zi - za) / (zb - za)
    return p + [(r_fill - gap, zi), (0, zi)]


def liquid_profile(s, gap=0.15):
    """Bottle liquid following the inner wall (thin gap) up to `fill_mm`."""
    return liquid_from(inner_bottle_profile(s), s["fill_mm"], gap)


def plate(name, outer, inner, z0, thickness):
    """Flat plate (mm) from an outer loop & a hole loop (same point count), thickness upward from z0."""
    n = len(outer)
    vs = [(x / 1000, y / 1000, (z0 + dz) / 1000) for dz in (thickness, 0.0) for x, y in outer + inner]
    lt, li, bt, bi = 0, n, 2 * n, 3 * n  # outer-top, inner-top, outer-bottom, inner-bottom
    fs = []
    for k in range(n):
        j = (k + 1) % n
        fs += [(lt + k, lt + j, li + j, li + k), (bt + k, bi + k, bi + j, bt + j),
               (bt + k, bt + j, lt + j, lt + k), (bi + k, li + k, li + j, bi + j)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.validate()
    return me


def can_tab_mesh(s, n=48):
    """Pull-tab + rivet on the lid panel (C-12: a can without a tab reads like an open cup). Sizes [D]."""
    H = s["height_mm"]
    sg = lambda v, e: math.copysign(abs(v) ** e, v)
    outer = [(6.0 * sg(math.cos(t), 0.5), 1.0 + 9.5 * sg(math.sin(t), 0.5))
            for t in (2 * math.pi * k / n for k in range(n))]
    inner = [(3.6 * math.cos(t), 5.6 + 3.2 * math.sin(t)) for t in (2 * math.pi * k / n for k in range(n))]
    z0 = H - 5.95  # just above the recessed panel (panel H-6.0 at center to H-6.3 at edge)
    tab = plate("can_tab", outer, inner, z0, 0.6)
    rivet = lathe_profile("can_rivet", [(1.9, z0 + 0.6), (1.8, z0 + 0.9), (1.0, z0 + 1.25), (0, z0 + 1.3)], seg=32)
    return tab, rivet


def cap_profile(s):
    H, rt = s["height_mm"], s["cap_mm"] / 2
    return [(0, H + 0.6), (rt - 1.2, H + 0.6), (rt - 0.2, H - 0.3), (rt, H - 6.0), (rt - 2.3, H - 6.0), (0, H - 6.0)]


def _sg(v, e):
    return math.copysign(abs(v) ** e, v)


def superellipse(a, b, n=10.0):
    """Rounded box section |x/a|^n + |y/b|^n = 1 (mm), scaled by r (0..1). Flat sides, rounded corners."""
    return lambda t, r, z: (r * a * _sg(math.cos(t), 2 / n), r * b * _sg(math.sin(t), 2 / n))


def box_profile(s):
    """Carton box: section scale (0..1) per height; bottom/top edges beveled 1 mm. Seal fin sits on top."""
    H = s["height_mm"] - s["fin_mm"]
    return [(0, 0), (0.96, 0), (1.0, 1.0), (1.0, H - 1.0), (0.96, H), (0, H)]


def tube_ab(s, z):
    """Tube section semi-axes (a in X, b in Y; mm) at height z: round near the cap, flattening to the seal at the top.
    Perimeter is preserved (a -> half the seal width = pi R / 2, b -> half the seal thickness)."""
    R, Hc, H = s["diameter_mm"] / 2, s["cap_height_mm"], s["height_mm"]
    z1, z2 = Hc + 25.0, H - s["seal_mm"]
    t = min(1.0, max(0.0, (z - z1) / (z2 - z1)))
    f = t * t * (3 - 2 * t)
    return R + (s["width_mm"] / 2 - R) * f, R + (s["seal_thickness_mm"] / 2 - R) * f


def tube_profile(s):
    """Tube body (r mm = round section radius; flattened by tube_ab) from the shoulder above the cap up to the seal."""
    R, Hc, H = s["diameter_mm"] / 2, s["cap_height_mm"], s["height_mm"]
    body = [(R, Hc + 4.0 + k * (H - Hc - 4.0) / 40) for k in range(41)]
    return [(0, Hc), (R - 6.0, Hc), (R - 1.5, Hc + 1.2)] + body + [(0, H)]


def tube_section(s):
    R = s["diameter_mm"] / 2

    def f(t, r, z):
        a, b = tube_ab(s, z)
        return r / R * a * math.cos(t), r / R * b * math.sin(t)
    return f


def flip_top_profile(s):
    R, Hc = s["cap_mm"] / 2, s["cap_height_mm"]
    return [(0, 0), (R - 1.5, 0), (R - 0.3, 0.6), (R, 2.0), (R, Hc - 1.0), (R - 0.6, Hc), (0, Hc)]


def jar_profile(s):
    """Glass jar: outer wall upward (base -> rim), then inner wall downward. Hollow (C-11/QC-11)."""
    H, R, rf, t = s["height_mm"], s["diameter_mm"] / 2, s["finish_mm"] / 2, s["wall_mm"]
    zb = H - 22.0  # end of straight body [D]
    outer = [(0, 2.5), (R - 7.0, 0.8), (R - 3.5, 0), (R - 0.8, 1.5), (R, 5.0), (R, zb), (R - 2.5, zb + 6.0),
            (rf + 2.0, zb + 11.0), (rf, zb + 12.5), (rf, H - 1.0), (rf - 0.6, H)]
    inner = [(rf - t, H), (rf - t, zb + 12.5), (R - 2.5 - t, zb + 6.0), (R - t, zb), (R - t, 5.0 + t),
             (R - 4.0, t + 1.5), (R - 9.0, t + 1.0), (0, t + 2.0)]
    return outer, inner


def lug_cap_profile(s):
    H, rt, ht, up = s["height_mm"], s["cap_mm"] / 2, s["cap_height_mm"], s["cap_rise_mm"]
    za, zb = H + up, H + up - ht
    return [(0, za), (rt - 1.5, za), (rt - 0.3, za - 0.5), (rt, za - 1.5), (rt, zb), (rt - 1.5, zb), (0, zb)]


def pet_profile(s):
    """PET bottle: thin body wall (0.35 mm), thick preform neck; decorative grooves + support ring. Hollow."""
    H, R, rf, t = s["height_mm"], s["diameter_mm"] / 2, s["finish_mm"] / 2, s["wall_mm"]
    rn = rf - 0.2  # neck below the thread [D]
    body = [(R, 6.0), (R, 130.0), (R - 1.8, 133.0), (R, 136.0), (R - 1.8, 139.0), (R, 142.0), (R - 3.0, 150.0),
             (R - 12.0, 163.0), (rn + 3.0, 174.0), (rn, 177.0)]
    neck = [(rn, 178.5), (rf + 3.1, 179.0), (rf + 3.1, 180.5), (rf, 181.0), (rf, H - 0.6), (rf - 0.6, H)]
    bore = rf - 2.9  # [D] preform neck is not blown
    outer = [(0, 3.5), (R - 8.0, 1.2), (R - 5.0, 0), (R - 1.5, 1.5)] + body + neck
    inner = [(bore, H), (bore, 177.0)] + [(r - t, z) for r, z in reversed(body[1:-1])] + [
        (R - t, 6.0), (R - 1.8, 1.5 + t), (R - 5.0, t), (R - 8.0, 1.2 + t), (0, 3.5 + t)]
    return outer, inner


def pet_cap_profile(s):
    H, rt, ht, up = s["height_mm"], s["cap_mm"] / 2, s["cap_height_mm"], s["cap_rise_mm"]
    za, zb = H + up, H + up - ht
    return [(0, za), (rt - 1.0, za), (rt - 0.2, za - 0.6), (rt, za - 2.0), (rt, zb), (rt - 1.2, zb), (0, zb)]
