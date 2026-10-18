"""GENERIC shoe recipe M2 (Task 11): upper panels from color-class DATA polygons, no shoe-specific code.

Shoe = sole unit (sole.py) + panels from data. Panels are defined in project.toml `[[model.panel]]`:
  name (= extraction panel `[[extraction.panel]]`), role (material slot), layer = [d_inner, d_outer] mm from S,
  stitching (bool), base_width = "upper" (S layer shell) | "midsole" (painted region on the midsole, e.g. heel cassette).
Upper panel = layer shell ∩ that side's polygon prism (outer polygon minus holes, extruded along Y, limited to the
half side: lateral y >= plan center line, medial the opposite) − lace holes. A midsole base_width panel = the midsole
pieces inside the prism, merged back into the midsole object as a second material slot (M1 QC still reads one midsole object).
Layer stacking is set by `layer` (gap >= 0.2 mm between touching layers: AM-13).
"""
import bmesh
import bpy
import numpy as np
from mathutils import Vector

from ....core.material import make_material
from ..geometry import boolean, world_bvh, loft_box, mesh_obj, xz_prism, copy
from . import data
from .shape import STITCH
from .lace import _offset_xz, _resample_xz

ROLE_GRAY = (0.55, 0.55, 0.56)  # neutral M2 material for roles missing from neutral_material


def specification():
    return data.CONFIG.get("model", {}).get("panel", [])


def role_material(mat, role):
    if role not in mat:
        mat[role] = bpy.data.materials.get(role) or make_material(role, ROLE_GRAY, 0.6)
    return mat[role]


def side_cutter(name, side, B, tmp, shift=(0.0, 0.0), source=None):
    """Panel region prism on one side (None when there is no data). shift (x, z) mm and source (other side's data)
    are only for negative test AM-10."""
    poly_list = data.class_panels(name, source or side)
    if not poly_list:
        return None
    pot = None
    gs = lambda L: [(p[0] + shift[0], p[1] + shift[1]) for p in L]
    for i, pg in enumerate(poly_list):
        pr = xz_prism(f"_pr_{name}_{side}_{i}", gs(pg["outer"]))
        for j, h in enumerate(pg["hole"]):
            boolean(pr, xz_prism(f"_lb_{name}_{side}_{i}_{j}", gs(h), -250.0, 250.0), "DIFFERENCE", delete=True)
        if pot is None:
            pot = pr
        else:
            boolean(pot, pr, "UNION", delete=True)
    L = data.LENGTH
    xs = list(np.arange(-8.0, L + 8.0, 0.5))
    sg = 1.0 if side == "lateral" else -1.0
    c = data.model("upper", "side_gap_mm", 0.4) / 2  # center-line gap between the L/M pieces (heel stitching; AM-13)
    half = loft_box(f"_sp_{name}_{side}", xs,
                         lambda x: tuple(sorted((B.plan(min(max(x, 0.0), L))[0] + sg * c, sg * 250.0))),
                         lambda x: (-60.0, 400.0), tmp)
    boolean(pot, half, "INTERSECT", delete=True)
    return pot


def plan_cutter(name, tmp):
    """Vertical prism (along Z), union of the tread zone `name` polygons (data.TREAD), in model coordinates (mm)."""
    zone = (data.TREAD or {}).get("zone", {}).get(name)
    if not zone or not zone["polygon"]:
        return None
    pot = None
    for i, pg in enumerate(zone["polygon"]):
        P = data.plan_xy(pg["outer"])
        n = len(P)
        V = [(x / 1000.0, y / 1000.0, z / 1000.0) for z in (-60.0, 80.0) for x, y in P]
        F = [tuple(range(n)), tuple(range(n, 2 * n))[::-1]] + [(j, (j + 1) % n, n + (j + 1) % n, n + j) for j in range(n)]
        pr = mesh_obj(f"_pz_{name}_{i}", V, F, tmp, validation=False)
        if pot is None:
            pot = pr
        else:
            boolean(pot, pr, "UNION", delete=True)
    return pot


def _merge_into(target, n_cuts, new_mat):
    """Merge the geometry of `n_cuts` into object `target` with material slot `new_mat` (new index)."""
    target.data.materials.append(new_mat)
    k = len(target.data.materials) - 1
    bm = bmesh.new()
    bm.from_mesh(target.data)
    n0 = len(bm.faces)
    bm.from_mesh(n_cuts.data)
    bm.faces.ensure_lookup_table()
    for f in bm.faces[n0:]:
        f.material_index = k
    bm.to_mesh(target.data)
    bm.free()
    old = n_cuts.data
    bpy.data.objects.remove(n_cuts)
    bpy.data.meshes.remove(old)


def build_panel_data(B, shell, cut_top, clip_l, holes, pk, tmp, mat, shift=None, medial_from_lateral=False):
    """All data panels. shell(name, d_in, d_out, collection) from upper.py; cut_top/clip_l = collar/tongue cutters;
    holes = lace hole cylinders. Returns {object_name: object} (upper panels per side).
    Negative tests: shift {panel: (x, z) mm}; medial_from_lateral = medial panel built from the lateral polygon."""
    obs = {}
    for sp in specification():
        name, role = sp["name"], sp["role"]
        if sp.get("base_width", "upper") != "upper":  # base_width midsole/outsole: build_base_panel() after the sole booleans (sole.py)
            continue
        m = role_material(mat, role)
        g = (shift or {}).get(name, (0.0, 0.0))
        pot = {s: side_cutter(name, s, B, tmp, g, "lateral" if medial_from_lateral and s == "medial" else None)
               for s in ("lateral", "medial")}
        d_in, d_out = sp["layer"]
        sh = shell(f"_c_{name}", d_in, d_out, tmp)
        sh["fold"] = d_in < 0  # inward offsets can fold at small-radius corners: boolean self-intersection
        sh.data.materials.append(m)
        boolean(sh, cut_top, "DIFFERENCE", transfer=True)
        boolean(sh, clip_l, "INTERSECT")
        part = []
        for s, c in pot.items():
            if c is None:
                continue
            ob = copy(sh, f"{name}_{s}", pk)
            boolean(ob, c, "INTERSECT", delete=True)
            if len(ob.data.polygons):
                part.append(ob)
            else:
                bpy.data.objects.remove(ob)
        if not part:
            continue
        ob = part[0]
        for other in part[1:]:  # L + M pieces as one object: no gap/coincident faces on the toe/heel center line
            boolean(ob, other, "UNION", delete=True)
        ob.name = ob.data.name = name
        if holes is not None:
            boolean(ob, holes, "DIFFERENCE", transfer=True)
        ob["role"], ob["panel"] = role, name
        obs[ob.name] = ob
    return obs


def build_base_panel(B, mat):
    """Panels with `base_width = "midsole"` (painted regions, e.g. heel cassette): called by sole.py AFTER all midsole
    booleans (cavity, window). All pieces are cut from the original midsole first and merged at the very end as a second
    material slot: a merged mesh contains internal cut faces (non-manifold) that make later EXACT booleans fail
    (AM90-C10: midsole 19 587 -> 110 faces)."""
    tmp = bpy.data.collections.new("_tmp_base")
    bpy.context.scene.collection.children.link(tmp)
    for sp in specification():
        base_width = sp.get("base_width", "upper")
        if base_width not in ("midsole", "outsole"):
            continue
        mid = bpy.data.objects[base_width]
        name, m = sp["name"], role_material(mat, sp["role"])
        if base_width == "outsole":  # tread zones from the sole photo: plan polygon prisms along Z (extraction/tread.py)
            pot = {"plan": plan_cutter(name, tmp)}
        else:
            pot = {s: side_cutter(name, s, B, tmp) for s in ("lateral", "medial")}
        heads = {}
        for s, c in pot.items():
            if c is not None:
                heads[s] = copy(mid, f"_{name}_{s}", tmp)
                boolean(heads[s], c, "INTERSECT")
        for s, c in pot.items():
            if c is not None:
                boolean(mid, c, "DIFFERENCE", delete=True)
        for k in heads.values():
            if len(k.data.polygons):
                _merge_into(mid, k, m)
        mid[f"panel_{name}"] = True
    for o in list(tmp.objects):
        bpy.data.objects.remove(o)
    bpy.data.collections.remove(tmp)


def build_stitching_data(B, obs, mat, pk):
    """Dashed stitching 1.5 mm inside the outline of every `stitching = true` panel (data polygons, per side), mapped
    onto S + normal (C-A6 method: offset in the xz plane, folds at notches dropped). Height = panel outer layer + 0.1 mm."""
    J = STITCH
    V, F = [], []
    n_dash = {}

    def points_S(x, z, side, lift):
        y = B.y_side(x, z, side)
        if y is None:
            return None
        ya, yb = B.y_side(x + 0.3, z, side), B.y_side(x, z + 0.3, side)
        if ya is None or yb is None:
            return None
        n = Vector((0.3, ya - y, 0.0)).cross(Vector((0.0, yb - y, 0.3))).normalized()
        if (n.y > 0) != (side == "lateral"):
            n = -n
        return Vector((x, y, z)) + n * lift, n

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

    for sp in specification():
        if not sp.get("stitching") or sp.get("base_width", "upper") != "upper":
            continue
        n_dash[sp["name"]] = 0
        ob_p = obs.get(sp["name"])
        if ob_p is None:
            continue
        bvh = world_bvh([ob_p])[0]  # AM90-C13: stitching points only where the panel exists (polygons grown past the
        # silhouette/collar: S still exists above the already-cut collar -> floating stitching)
        for side in ("lateral", "medial"):
            for pg in data.class_panels(sp["name"], side):
                P = np.array(pg["outer"], float)
                area = 0.5 * float(np.dot(P[:, 0], np.roll(P[:, 1], -1)) - np.dot(np.roll(P[:, 0], -1), P[:, 1]))
                poly = _resample_xz([tuple(p) for p in P] + [tuple(P[0])], 0.25)[:-1]
                line = _offset_xz(poly, J["offset"] if area > 0 else -J["offset"], True)  # toward the polygon inside
                lift = sp["layer"][1] + 0.1
                tt = [None if q is None else points_S(q[0], q[1], side, lift) for q in line]
                tt = [t_ if t_ is not None and (bvh.find_nearest(t_[0], 1.0)[0] is not None) else None for t_ in tt]
                n_dash[sp["name"]] += dash(tt)
    if not V:
        return None
    ob = mesh_obj("stitching", np.array(V) / 1000.0, F, pk, mat["lace"])
    for k, v in n_dash.items():
        ob[f"dash_{k}"] = v
    return ob


def data_layers():
    """Layer object names for AM-13 (data panel project): body, mesh, tongue + all data upper panels."""
    return ["upper", "panel_mesh", "tongue"] + sorted(o.name for o in bpy.data.objects if o.get("panel") and
                                                    o.name in bpy.context.scene.objects)
