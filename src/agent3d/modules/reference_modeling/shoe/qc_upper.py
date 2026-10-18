"""Shoe recipe QC M2 (upper): AM-09 smoothness, AM-10 swoosh IoU per side, AM-11 mudguard line, AM-12 laces + holes,
AM-13 panel layers without z-fighting, AM-14 material slots named by role."""
import bpy
import numpy as np
from mathutils import Vector

from ....core.qc import check, iou
from ....core.scene import product_object
from ..geometry import world_bvh
from ..filters import gauss
from ..qc_silhouette import is_inside, ray_ob, ripple_deg
from . import data
from .threshold import THRESHOLD, SW
from .shape import R_LACE, LAST


# ---------------- M2: upper (AM-09 .. AM-14) ----------------
def find_object(*name):
    for n in name:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            return ob
    return None


def _reference_line():
    """Smooth functions to PLACE the AM-09 measurement lines (same for the good model and negatives)."""
    xs, _, zt = data.side_profile("lateral")
    g1, v1 = gauss(xs, zt, 2.0)
    mid, _ = data.midsole_line()
    g2, v2 = gauss(mid[:, 0], mid[:, 1], 3.0)
    gp = np.arange(0.0, data.LENGTH, 0.5)
    g3, v3 = gauss(gp, np.array([data.plan_y(x)[0] for x in gp]), 2.0)
    return (lambda x: float(np.interp(x, g1, v1)), lambda x: float(np.interp(x, g2, v2)),
            lambda x: float(np.interp(x, g3, v3)))


def qc_smooth():
    """AM-09 (C-A3): upper surface smoothness. Rays against the upper body only (panels = body offsets, smooth/wavy along with it):
    4 side lines (lateral/medial x 35%/60% of upper height, x 20-275 mm) + 3 lines over the toe box (x 15-85, y center
    and +-10 mm), every 1 mm. Value = largest RMS normal ripple across the lines (degrees)."""
    ob = find_object("upper", "upper_block")
    a = THRESHOLD["ripple_deg"]
    if ob is None:
        return check("AM-09", "upper_normal_ripple_deg", 99.0, False, f"<= {a} deg", "upper object missing"), {}
    zt, mt, cy = _reference_line()
    line = {}
    for side, sg in (("lateral", 1), ("medial", -1)):
        for f in (0.35, 0.6):
            n = []
            for x in np.arange(20.0, 275.0, 1.0):
                h = ray_ob(ob, (x, sg * 300.0, mt(x) + f * (zt(x) - mt(x))), (0, -sg, 0), True)
                if h:
                    n.append(tuple(h[1]))
            line[f"{side}_{int(f * 100)}"] = n
    for off in (-10.0, 0.0, 10.0):
        n = []
        for x in np.arange(15.0, 85.0, 1.0):
            h = ray_ob(ob, (x, cy(x) + off, 300.0), (0, 0, -1), True)
            if h:
                n.append(tuple(h[1]))
        line[f"top_{int(off)}"] = n
    value = {k: (ripple_deg(v) if len(v) >= 40 else 99.0) for k, v in line.items()}
    worst = max(value, key=value.get)
    v = value[worst]
    return check("AM-09", "upper_normal_ripple_deg", v, v <= a, f"<= {a} deg",
               f"entity {ob.name}; worst {worst}; " + ", ".join(f"{k} {w:.3f}" for k, w in value.items())), value


def swoosh_mask_data(side, xs, zs, shift=(0.0, 0.0)):
    x, lo, hi = data.swoosh_polygon(side)
    x = x + shift[0]
    LO, HI = np.interp(xs, x, lo) + shift[1], np.interp(xs, x, hi) + shift[1]
    inner = (xs >= x[0]) & (xs <= x[-1])
    Z = zs[:, None]
    return (Z >= LO[None]) & (Z <= HI[None]) & inner[None]


def qc_swoosh():
    """AM-10: IoU of the swoosh outline (projection along Y, rays against that side's swoosh object only) vs that side's
    data polygon. Two sides = two independent checks (lateral & medial data from different photos; positions differ ~11 mm)."""
    result, art = [], {}
    a = THRESHOLD["iou_swoosh_min"]
    for side, sg in (("lateral", 1), ("medial", -1)):
        xs = np.arange(130.0, 270.0, SW) + SW / 2
        zs = np.arange(50.0, 105.0, SW) + SW / 2
        d = swoosh_mask_data(side, xs, zs)
        floor = iou(d, swoosh_mask_data(side, xs, zs, (0.5, 0.5)))
        ob = find_object(f"swoosh_{side}")
        m = np.zeros_like(d)
        if ob is not None:
            for i, z in enumerate(zs):
                for j, x in enumerate(xs):
                    m[i, j] = ray_ob(ob, (x, sg * 300.0, z), (0, -sg, 0)) is not None
        v = iou(m, d)
        result.append(check("AM-10", f"iou_swoosh_{side}", v, v >= a, f">= {a}",
                         f"{int(m.sum())} px model, {int(d.sum())} px data, {SW} mm/px; data baseline: IoU of data vs data "
                         f"shifted (0.5; 0.5) mm = {floor:.4f} (threshold basis)" + ("" if ob else "; swoosh object missing")))
        art[side] = (m, d)
    return result, art


def qc_mudguard():
    """AM-11: top mudguard line (lateral projection, rays against the mudguard object only): highest z still hitting the
    mudguard (0.5 mm scan + 0.01 mm bisection) at every data x, except the toe tip where the mudguard runs up to the top
    silhouette (data line < 3 mm from the silhouette). Mean |model - data|."""
    ob = find_object("mudguard")
    mg = np.array(data.DATA["mudguard_top_line_lateral"], float)
    xs, _, zt = data.side_profile("lateral")
    a = THRESHOLD["mudguard_mm"]
    use = [(x, z) for x, z in mg if np.interp(x, xs, zt) - z > 3.0]
    if ob is None:
        return check("AM-11", "mudguard_top_line_mean_error_mm", 99.0, False, f"<= {a} mm", "mudguard object missing"), None
    is_hit = lambda x, z: ray_ob(ob, (x, 300.0, z), (0, -1, 0)) is not None
    result = []
    for x, zd in use:
        zz = np.arange(zd - 12.0, zd + 12.0, 0.5)
        k = [is_hit(x, z) for z in zz]
        idx = [i for i in range(len(zz) - 1) if k[i] and not k[i + 1]]
        if not idx:
            result.append(np.nan)
            continue
        lo, hi = zz[idx[-1]], zz[idx[-1] + 1]
        while hi - lo > 0.01:
            m = (lo + hi) / 2
            lo, hi = (m, hi) if is_hit(x, m) else (lo, m)
        result.append((lo + hi) / 2)
    zm = np.array(result)
    zd = np.array([z for _, z in use])
    ok = ~np.isnan(zm)
    g = np.abs(zm[ok] - zd[ok])
    v = float(g.mean()) if ok.any() else 99.0
    passed = v <= a and ok.mean() >= 0.95
    return check("AM-11", "mudguard_top_line_mean_error_mm", v, passed, f"<= {a} mm (>= 95% points measured)",
               f"{ok.sum()}/{len(ok)} points (x >= {use[0][0]:.1f}; {len(mg) - len(use)} toe points skipped), "
               f"max {g.max():.2f} mm, median {np.median(g):.2f}; medial = lateral line [D]"), \
        (np.array([p[0] for p in use]), zd, zm)


def qc_lace():
    """AM-12: (a) laces do not penetrate the upper: signed distance from the lace center line to every other product object
    (BVH, sign from the nearest surface normal) - r >= 0; between lace segments >= 2r. (b) holes: 6-7 pairs, hole spacing
    10-16 mm per side, and the 2 large data holes per side (area >= 10 mm2) each have a model hole within 3 mm (x, z)."""
    from mathutils.kdtree import KDTree
    path = LAST.get("lace_path") if bpy.data.objects.get("lace") else None
    holes = LAST.get("hole") if bpy.data.objects.get("lace") else None
    if not path or not holes:
        return [check("AM-12", "lace_distance_min_mm", -99.0, False, ">= 0 mm", "lace missing"),
                check("AM-12", "normal_lace_holes", 0, False, "6-7 pairs", "lace missing")]
    root = bpy.data.objects["PRODUCT_ROOT"].matrix_world
    world = lambda p: (root @ (Vector(p) / 1000.0)) * 1000.0
    other = [o for o in product_object() if o.name not in ("lace", "stitching")]
    bvhs = [(o.name, world_bvh([o])[0]) for o in other]
    r = R_LACE * root.to_scale()[0]
    distance, worst = 1e9, None
    pts, sid = [], []
    for s, j in enumerate(path):
        for p in j:
            q = world(p)
            pts.append(q)
            sid.append(s)
            for name, b in bvhs:
                loc, _, _, d = b.find_nearest(q, r + 1.0)
                if loc is None:
                    continue
                sd = -d if is_inside(b, q) else d
                if sd - r < distance:
                    distance, worst = sd - r, f"{name} ({q.x:.1f}, {q.y:.1f}, {q.z:.1f})"
    distance = min(distance, 1.0)
    kd = KDTree(len(pts))
    for i, p in enumerate(pts):
        kd.insert(p, i)
    kd.balance()
    inter = 1e9
    for i, p in enumerate(pts):
        for _, k, d in kd.find_range(p, 2 * r + 1.0):
            if sid[k] != sid[i]:
                inter = min(inter, d)
    a = THRESHOLD["lace_distance_mm"]
    c1 = check("AM-12", "lace_distance_min_mm", float(distance), distance >= a and inter >= 2 * r - 1e-6, f">= {a} mm (and between segments >= 2r)",
             f"{len(path)} segments, r {r:.2f} mm, closest: {worst}; min distance between segments "
             f"{inter if inter < 1e8 else float('inf'):.2f} mm (>= {2 * r:.2f})")
    # hole
    n = min(len(holes["lateral"]), len(holes["medial"]))
    distance_l = {s: float(np.median(np.diff(sorted(p[0] for p in holes[s])))) if len(holes[s]) > 1 else 0.0 for s in holes}
    error = []
    for s in ("lateral", "medial"):
        for xd, zd, _ in LAST["hole_data"][s]:  # zd None = project [D] row (x only)
            error.append(min(max(abs(p[0] - xd), abs(p[2] - zd) if zd is not None else 0.0) for p in holes[s]))
    gmax = max(error) if error else 0.0  # project without data holes ([D] row from project.toml): count + spacing only
    ok = 6 <= n <= 7 and all(10.0 <= v <= 16.0 for v in distance_l.values()) and gmax <= THRESHOLD["hole_mm"]
    c2 = check("AM-12", "normal_lace_holes", n, ok, f"6-7 pairs, spacing 10-16 mm, data holes <= {THRESHOLD['hole_mm']} mm",
             f"spacing lateral {distance_l['lateral']:.2f} / medial {distance_l['medial']:.2f} mm; "
             + f"error of {len(error)} baseline holes " + ", ".join(f"{g:.2f}" for g in error) + " mm"
             + (" (baseline = project.toml [D] row, x only)" if any(d[1] is None for s in LAST["hole_data"]
                                                                  for d in LAST["hole_data"][s]) else " (other holes [D])"))
    return [c1, c2]


LAYERED_OBJECTS = ("upper", "panel_mesh", "mudguard", "eyestay_lateral", "eyestay_medial", "heel_overlay",
           "swoosh_lateral", "swoosh_medial", "tongue")


def qc_layers(layered_objects=LAYERED_OBJECTS):
    """AM-13: panel layers do not z-fight or show through each other. For every pair of layer objects: (a) number of
    intersecting triangle pairs (BVH overlap) = 0; (b) vertex distance to the other object's surface >= 0.2 mm
    (<= 6000 sampled vertices per object). Not checked: midsole (panels deliberately embedded 2 mm), eyelets, laces, stitching."""
    obs = [bpy.data.objects[n] for n in layered_objects if bpy.data.objects.get(n)]
    a = THRESHOLD["layer_mm"]
    if len(obs) < len(layered_objects):
        return check("AM-13", "layer_distance_min_mm", -1.0, False, f">= {a} mm, 0 intersections", "layer objects incomplete")
    data = {o.name: world_bvh([o]) for o in obs}
    cuts, pair = 0, []
    for i, o1 in enumerate(obs):
        for o2 in obs[i + 1:]:
            k = len(data[o1.name][0].overlap(data[o2.name][0]))
            if k:
                cuts += k
                pair.append(f"{o1.name}/{o2.name} {k}")
    rng = np.random.default_rng(0)
    dmin, where = 1e9, ""
    for o1 in obs:
        V = data[o1.name][1]
        if len(V) > 6000:
            V = V[rng.choice(len(V), 6000, replace=False)]
        for o2 in obs:
            if o2 is o1:
                continue
            b = data[o2.name][0]
            for v in V:
                hit = b.find_nearest(Vector(v), 1.0)
                if hit[0] is not None and hit[3] < dmin:
                    dmin, where = hit[3], f"{o1.name} to {o2.name} at ({v[0]:.0f}, {v[1]:.0f}, {v[2]:.0f})"
    dmin = min(dmin, 1.0)
    return check("AM-13", "layer_distance_min_mm", float(dmin), cuts == 0 and dmin >= a, f">= {a} mm, 0 intersections",
               f"{len(obs)} objects, intersecting triangles {cuts}" + (f" ({'; '.join(pair[:4])})" if pair else "")
               + f"; closest {where}")


def qc_material():
    """AM-14: material slots per part use the P3 role names (taste.md); all 10 roles exist and every product object
    uses a role as its main material."""
    use, wrong = set(), []
    ROLE = data.role_list()
    for ob in product_object():
        name = [m.name for m in ob.data.materials if m]
        use |= set(name)
        if not name or name[0] not in ROLE:
            wrong.append(ob.name)
    missing = [p for p in ROLE if p not in use]
    return check("AM-14", "role_material_slot", len(ROLE) - len(missing), not missing and not wrong,
               f"{len(ROLE)} roles", ("missing: " + ", ".join(missing) + "; " if missing else "")
               + ("objects without a role: " + ", ".join(wrong) if wrong else "all objects use a role"))
