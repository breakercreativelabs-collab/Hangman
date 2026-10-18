"""Shoe recipe from reference DATA, non-generative: M1 bottom part + M2 assembly (upper.py) + M3 (p3_material.py).

M1: outsole (5.7 mm rubber, procedural tread in the material) · midsole (section loft per x station) ·
Air window on both sides (boolean from `air_window_lateral`) · hollow clear Air capsule + internal dividers (QC-11).
M2 (upper.py, panel data): smooth layered upper (body/lining, mesh panels, mudguard, eyestay, heel overlay, swoosh),
collar opening, tongue, 7 hole pairs + eyelets, laces, stitching. upper="block" = coarse M1 block.
Material slot = palette role name (ROLE). M3 (p3_material.py): procedural project palette material per role, waffle tread;
palette="neutral" = neutral M1/M2 materials (neutral_material.py). Axis convention: data.py. Data & palette: projects/<id>/.
"""
import math

import bmesh
import bpy
import numpy as np

from ....core.scene import control, collection, product_object, root, prepare_scene
from ..geometry import boolean, loft, mm, xz_prism, tidy_slot, apply
from ..filters import median5, bottom_hull
from . import data
from .neutral_material import neutral_material
from .p3_material import p3_material

# Shape parameters [D] (modeling choices, not data). All mm.
BULGE = 0.05          # midsole sides bulge: width at the top/bottom edge = (1 - 0.05) x max width (plan)
FILLET_MID = (0.3, 1.0)  # (bottom, top) midsole edge radii
FILLET_OUT = (1.5, 0.2)  # (bottom, top) outsole edges
UPPER_INSET = 1.5       # upper sits 1.5 mm inside the top midsole lip (cupsole look)
MID_WALL = 2.0       # midsole wall thickness beside the capsule cavity
CAPSULE_GAP = 0.4      # cavity = capsule + 0.4 mm
CAPSULE_WALL = 1.0    # PU capsule film [D]
CAPSULE_MARGIN = (3.0, 2.5)  # capsule overhangs the window bbox (x, z)


# ---------------- geometry ----------------
def box_rings(cy, a, zlo, zhi, r_bottom, r_top, n_flat=6, n_fillet=5, n_sides=12):
    """Midsole/outsole cross-section in the YZ plane: bulging sides (width 2a at mid height, (1-BULGE)a at the edges),
    filleted bottom/top corners. Fixed point order (same count for all stations)."""
    h = zhi - zlo
    rb, ra = min(r_bottom, 0.45 * h), min(r_top, 0.45 * h)
    zc, b = (zlo + zhi) / 2, h / 2
    side = lambda z: a * (1 - BULGE * ((z - zc) / b) ** 2)
    right = []
    yb = side(zlo + rb) - rb  # bottom fillet center
    for t in np.linspace(0, 1, n_flat, endpoint=False):
        right.append((t * yb, zlo))
    for f in np.linspace(-math.pi / 2, 0, n_fillet, endpoint=False):
        right.append((yb + rb * math.cos(f), zlo + rb + rb * math.sin(f)))
    for z in np.linspace(zlo + rb, zhi - ra, n_sides, endpoint=False):
        right.append((side(z), z))
    ya = side(zhi - ra) - ra
    for f in np.linspace(0, math.pi / 2, n_fillet, endpoint=False):
        right.append((ya + ra * math.cos(f), zhi - ra + ra * math.sin(f)))
    for t in np.linspace(1, 0, n_flat):
        right.append((t * ya, zhi))
    left = [(-y, z) for y, z in right[-2:0:-1]]
    return [(cy + y, z) for y, z in right + left]


def dome_rings(cy, a, zlo, zw, zhi, n=48, e_bottom=4.0, e_top=2.4):
    """Upper block cross-section: superellipse, widest (2a) at zw, domed up to zhi, base rounded down to zlo."""
    pts = []
    for t in np.linspace(-math.pi / 2, 3 * math.pi / 2, n, endpoint=False):
        c, s = math.cos(t), math.sin(t)
        e = e_top if s > 0 else e_bottom
        y = a * math.copysign(abs(c) ** (2 / e), c)
        z = zw + (zhi - zw if s > 0 else zw - zlo) * math.copysign(abs(s) ** (2 / e), s)
        pts.append((cy + y, z))
    return pts


def super_rings(cy, a, zc, b, n=40, e=6.0):
    pts = []
    for t in np.linspace(-math.pi / 2, 3 * math.pi / 2, n, endpoint=False):
        c, s = math.cos(t), math.sin(t)
        pts.append((cy + a * math.copysign(abs(c) ** (2 / e), c), zc + b * math.copysign(abs(s) ** (2 / e), s)))
    return pts


# ---------------- build ----------------
def build_shoe(window_shift_mm=0.0, scale=1.0, midsole_extra_mm=0.0, solid_capsule=False, without_window=False,
           base="hull", tread=None, upper="m2", missing_role=None, palette="p3", param_material=None,
           swap_role=None, empty_slot=None, default_material=None, **upper_param):
    """Build the model in the PRODUCT collection: M1 bottom part + M2 upper (upper.py) + M3 materials (p3_material.py,
    P3 palette; palette="neutral" = M2 materials). upper="block" = coarse M1 block (negative test C-A3).
    Non-default parameters exist only for QC negative tests: param_material (swoosh/capsule_mode/wrong_hex, p3_material),
    swap_role=(a, b) swaps two roles' materials on their objects, empty_slot=<object> empties its material slot,
    default_material=<role> replaces that role's material with a new default (grey) material of the same name."""
    prepare_scene()
    c = control()
    c["product"], c["project"] = data.CONFIG["project"]["product"], data.CONFIG["project"]["label"]
    pk, r0 = collection("PRODUCT"), root()
    if palette == "p3":
        if any(len(v) > 2 for v in data.palette().values()):  # typed palette (photo colorway, Task 11)
            from .colorway_material import colorway_material
            bp = {k: v for k, v in (param_material or {}).items() if k != "swoosh"}
            mat = colorway_material(tread=tread or "waffle", **bp)
        else:
            mat = p3_material(tread=tread or "waffle", **(param_material or {}))
        c["palette"] = data.CONFIG["palette"]["name"]
    else:
        mat = neutral_material(tread or "voronoi")
    if swap_role:
        a_, b_ = swap_role
        mat[a_], mat[b_] = mat[b_], mat[a_]

    xs_s, zb_raw, zt_raw = data.side_profile("lateral")
    mid, _ = data.midsole_line()
    # hull only over the sole span: the heel end sample (z 46 at x 292.6) = heel counter, not the sole base
    n1 = int(np.nonzero(zb_raw < mid[-1, 1] - data.OUTSOLE)[0].max())
    zb_smooth = zb_raw.copy()
    zb_smooth[:n1 + 1] = bottom_hull(xs_s[:n1 + 1], zb_raw[:n1 + 1])
    if base == "median5":  # v1 (negative test C-A2)
        zb_smooth = median5(zb_raw)
    x_last = xs_s[-1]
    xs = np.unique(np.r_[np.arange(0.0, x_last, 1.0), x_last, np.linspace(x_last, data.LENGTH, 4)])

    def side_view(x):
        zb, zt, zh = (np.interp(x, xs_s, v) for v in (zb_raw, zt_raw, zb_smooth))
        if x > x_last:  # last 1 px tail (pixel edge up to 293.7): tapers toward the middle
            f = 1 - 0.9 * (x - x_last) / (data.LENGTH - x_last)
            m = (zb + zt) / 2
            zb, zt, zh = m - (m - zb) * f, m + (zt - m) * f, m - (m - zh) * f
        return zb, zt, zh

    def plan(x):
        cy, a = data.plan_y(x)
        if x > x_last:
            a *= 1 - 0.9 * (x - x_last) / (data.LENGTH - x_last)
        return cy, a

    # sole span: from the first midsole line point to the last silhouette sample whose base is still below the midsole
    xs0 = mid[0, 0]
    xs1 = max(x for x, zb in zip(xs_s, zb_raw) if zb < mid[-1, 1] - data.OUTSOLE)
    mt = lambda x: float(np.interp(x, mid[:, 0], mid[:, 1])) + midsole_extra_mm
    sole_stations = [x for x in xs if xs0 <= x <= xs1]
    sole_stations = sorted(set(sole_stations) | {xs0, xs1})

    c_out, c_mid = [], []
    for x in sole_stations:
        _, _, zh = side_view(x)
        cy, a = plan(x)
        c_out.append(box_rings(cy, a * (1 - BULGE) - 0.2, zh, zh + data.OUTSOLE, *FILLET_OUT))
        c_mid.append(box_rings(cy, a, zh + data.OUTSOLE, max(mt(x), zh + data.OUTSOLE + 0.4), *FILLET_MID))
    outsole = loft("outsole", sole_stations, c_out, pk)
    midsole = loft("midsole", sole_stations, c_mid, pk)

    if upper == "block":  # M1: closed volume from the top silhouette + plan (wavy, C-A3)
        c_up = []
        for x in xs:
            zb, zt, _ = side_view(x)
            cy, a = plan(x)
            on_sole = xs0 <= x <= xs1
            w = float(np.clip(min(x - xs0, xs1 - x) / 6.0, 0, 1)) if on_sole else 0.0
            if on_sole:
                m = mt(x)
                zlo_s, zw_s, a_s = max(m - 4.0, zb + 1.0), m + 1.5, a * (1 - BULGE) - UPPER_INSET
            else:
                zlo_s, zw_s, a_s = zb, zb, a
            zlo = zb + w * (zlo_s - zb)
            zw = max(zb + 0.3 * (zt - zb) + w * (zw_s - (zb + 0.3 * (zt - zb))), zlo + 0.2)
            aa = a + w * (a_s - a)
            c_up.append(dome_rings(cy, aa, zlo, min(zw, zt - 0.5), zt))
        upper_obs = {"upper_block": loft("upper_block", list(xs), c_up, pk)}
        upper_obs["upper_block"].data.materials.append(mat["upper"])
        info_upper = {}
    else:
        from .upper import build_upper
        ctx = dict(xs_s=xs_s, zb_raw=zb_raw, zt_raw=zt_raw, x_last=x_last, xs0=xs0, xs1=xs1, mid=mid,
                   midsole_extra=midsole_extra_mm,
                   panel=data.PANEL if data.PANEL is not None else data.class_holes())
        upper_obs, B_up, info_upper = build_upper(ctx, mat, pk, smoothness=(upper == "m2"), **upper_param)

    # cavity + Air capsule (heel), from the data window bbox
    jx0, jx1, jz0, jz1 = data.data_window_bbox()
    jx0, jx1 = jx0 + window_shift_mm, jx1 + window_shift_mm
    kx0, kx1 = jx0 - CAPSULE_MARGIN[0], jx1 + CAPSULE_MARGIN[0]
    kz0, kz1 = jz0 - CAPSULE_MARGIN[1], jz1 + CAPSULE_MARGIN[1]
    kzc, kb = (kz0 + kz1) / 2, (kz1 - kz0) / 2
    kxc, kxa = (kx0 + kx1) / 2, (kx1 - kx0) / 2

    def capsule_rings(x, add=0.0, shrink=0.0):
        cy, a = plan(x)
        _, _, zh = side_view(x)
        zlo, zhi = zh + data.OUTSOLE, mt(x)
        zcm, bm = (zlo + zhi) / 2, (zhi - zlo) / 2
        u2 = max(((kz0 - zcm) / bm) ** 2, ((kz1 - zcm) / bm) ** 2)
        hw = a * (1 - BULGE * u2) - MID_WALL - CAPSULE_GAP  # capsule faces 2.4 mm inside the midsole wall
        e = (1 - min(abs((x - kxc) / kxa), 1.0) ** 6) ** (1 / 6)  # rounded ends
        return super_rings(cy, hw * (0.6 + 0.4 * e) + add - shrink, kzc, kb * e + add - shrink)

    u = np.sin(np.linspace(-math.pi / 2, math.pi / 2, 41)) * 0.995
    xk = list(kxc + kxa * u)
    if not without_window:
        xr = list(kxc + (kxa + CAPSULE_GAP) * u)
        cavity = loft("_cavity", xr, [capsule_rings(x, CAPSULE_GAP) for x in xr])
        boolean(midsole, cavity, delete=True)
        boolean(midsole, xz_prism("_window", data.window_polygon(window_shift_mm)), delete=True)
    capsule = loft("air_capsule", xk, [capsule_rings(x) for x in xk], pk)
    if not solid_capsule:
        s = capsule.modifiers.new("wall", "SOLIDIFY")
        s.thickness, s.offset, s.use_even_offset = mm(CAPSULE_WALL), -1.0, True
        apply(capsule)
        # internal dividers [D]: at the notches in the data window top edge (x 201.9 / 221.5 / 227.7 mm) = visible divider walls
        x, _, zt = data.data_window()
        hit_loc = [x[i] for i in range(1, len(x) - 1) if zt[i] < zt[i - 1] and zt[i] <= zt[i + 1]]
        add_divider(capsule, [xi + window_shift_mm for xi in hit_loc], capsule_rings, CAPSULE_WALL + 0.1)

    for ob, k in ((outsole, "outsole"), (midsole, "midsole"), (capsule, "air_capsule")):
        ob.data.materials.append(mat[k])
    if upper != "block" and data.CLASS is not None:  # painted midsole regions (cassette) from data: after the midsole boolean
        from .panel_data import build_base_panel
        build_base_panel(B_up, mat)
        for p in ob.data.polygons:
            p.use_smooth = True
    for ob in [outsole, midsole, capsule] + list(upper_obs.values()):
        ob.parent = r0
    for ob in [outsole, midsole, capsule] + list(upper_obs.values()):
        tidy_slot(ob)
    if missing_role:  # negative test AM-14
        bpy.data.materials[missing_role].name = missing_role + "_without_role"
    if empty_slot:  # negative test AM-18
        bpy.data.objects[empty_slot].data.materials[0] = None
    if default_material:  # negative test AM-18: new empty material (default grey) with the correct role name
        old = bpy.data.materials[default_material]
        old.name = default_material + "_old"
        new = bpy.data.materials.new(default_material)
        for ob in product_object():
            for i, m_ in enumerate(ob.data.materials):
                if m_ == old:
                    ob.data.materials[i] = new
    r0.scale = (scale,) * 3
    r0["spec_length_mm"], r0["spec_forefoot_width_mm"] = data.LENGTH, data.LAB["forefoot_width_mm"]
    r0["source"] = data.data_source()
    bpy.context.view_layer.update()
    return dict(outsole=outsole, midsole=midsole, capsule=capsule, root=r0, info_upper=info_upper, **upper_obs)


def add_divider(capsule, xs, ring_fn, shrink, thickness=1.0):
    bm = bmesh.new()
    bm.from_mesh(capsule.data)
    for xc in xs:
        st = [xc - thickness / 2, xc + thickness / 2]
        ob = loft("_divider", st, [ring_fn(x, shrink=shrink) for x in st])
        bm.from_mesh(ob.data)  # from_mesh appends (does not replace) geometry
        old = ob.data
        bpy.data.objects.remove(ob)
        bpy.data.meshes.remove(old)
    bm.to_mesh(capsule.data)
    bm.free()
    capsule["divider_x_mm"] = [round(float(v), 2) for v in xs]
