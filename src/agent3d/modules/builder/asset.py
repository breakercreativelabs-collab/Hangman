"""Asset path (user decision 2026-10-17): for organic shapes, find an openly LICENSED 3D model, grade its quality
with numbers (KA-01..07), then adapt it (scale, rotate, cut, merge with builder-made parts) via SDF -> a new closed
mesh that passes KC QC. Non-generative: no AI creates the shape; attribution is required.

Assets are stored only in references/ (not in the repo). Design: [[part]] recipe = "asset" with model, entity,
license_name, attribution, rotate_z, height_mm (height of the whole asset after scaling), cut_z (keep z >= cut_z),
cut_smoothness.
"""
import math
import os

import numpy as np

from ...core import io, qc

ALLOWED_LICENSES = ("CC0", "CC-BY", "CC-BY-4.0", "CC-BY 4.0", "PUBLIC DOMAIN", "MIT")


def load_asset(b):
    """Import glTF, take one entity, apply its world transform, put the base at the origin (XY center), scale to
    `height_mm`, rotate about Z by `rotate_z`. Returns (points mm Nx3, triangles Mx3)."""
    import bpy
    source = io.path_repo(b["model"])
    if not os.path.isfile(source) and b.get("download"):  # openly licensed asset: downloaded once into references/ (public package)
        import urllib.request
        os.makedirs(os.path.dirname(source), exist_ok=True)
        with urllib.request.urlopen(b["download"], timeout=120) as r, open(source + ".tmp", "wb") as f:
            f.write(r.read())
        os.replace(source + ".tmp", source)
    if not os.path.isfile(source):
        raise FileNotFoundError(f"asset {b['model']} not found (download it to references/ first; see the source in the design)")
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=source)
    new = [o for o in bpy.data.objects if o not in before]
    target = next((o for o in new if o.name == b["entity"]), None)
    if target is None:
        raise ValueError(f"entity '{b['entity']}' not found in the asset; available: {[o.name for o in new if o.type == 'MESH']}")
    me = target.data.copy()
    me.transform(target.matrix_world)
    if b.get("subdiv", 0):  # smooth a low-poly asset: weld vertices (bmesh) first, then Catmull-Clark (subdivision surface)
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6 * max(target.dimensions))
        bm.to_mesh(me)
        bm.free()
        tmp = bpy.data.objects.new("tmp_asset", me)
        bpy.context.scene.collection.objects.link(tmp)
        mod = tmp.modifiers.new("subdiv", "SUBSURF")
        mod.levels = mod.render_levels = int(b["subdiv"])
        ev = tmp.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me2 = bpy.data.meshes.new_from_object(ev)
        bpy.data.objects.remove(tmp)
        bpy.data.meshes.remove(me)
        me = me2
    me.calc_loop_triangles()
    t = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", t)
    t = t.reshape(-1, 3)
    f = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", f)
    for o in new:
        bpy.data.objects.remove(o)
    bpy.data.meshes.remove(me)
    t, f = weld(t, f.reshape(-1, 3))
    center = np.array([(t[:, 0].min() + t[:, 0].max()) / 2, (t[:, 1].min() + t[:, 1].max()) / 2, t[:, 2].min()])
    t = (t - center) * (b["height_mm"] / (t[:, 2].max() - t[:, 2].min()))
    a = math.radians(b.get("rotate_z", 0.0))
    x, y = t[:, 0] * math.cos(a) - t[:, 1] * math.sin(a), t[:, 0] * math.sin(a) + t[:, 1] * math.cos(a)
    return np.c_[x, y, t[:, 2]], f


def weld(points, seg, tol=1e-6):
    """Merge vertices at the same position (glTF splits vertices at UV/normal seams -> the mesh looks leaky with
    thousands of loose parts although the shape is one piece). Tolerance relative to entity size; drops degenerate
    triangles."""
    scale = float(np.ptp(points, axis=0).max()) or 1.0
    key = np.round(points / (scale * tol)).astype(np.int64)
    _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    seg = inv.ravel()[seg]
    seg = seg[(seg[:, 0] != seg[:, 1]) & (seg[:, 1] != seg[:, 2]) & (seg[:, 0] != seg[:, 2])]
    return points[idx], seg


def asset_value(points, seg, b):
    """Asset quality judge KA-01..07 (builder QC_RULES). Score 0-100 = weighted percentage of passed checks; grade A/B/C."""
    e = np.sort(np.vstack([seg[:, [0, 1]], seg[:, [1, 2]], seg[:, [2, 0]]]), axis=1)
    _, n_e = np.unique(e, axis=0, return_counts=True)
    leak = float((n_e != 2).mean())
    a, bb, c = points[seg[:, 0]], points[seg[:, 1]], points[seg[:, 2]]
    vol = float(np.einsum("ij,ij->i", a, np.cross(bb, c)).sum() / 6.0)
    side = np.stack([np.linalg.norm(bb - a, axis=1), np.linalg.norm(c - bb, axis=1), np.linalg.norm(a - c, axis=1)], 1)
    area = np.linalg.norm(np.cross(bb - a, c - a), axis=1) / 2
    ratio = side.max(1) ** 2 / np.maximum(4 * area / math.sqrt(3), 1e-12)  # 1 = equilateral
    flake = float((ratio > 10).mean())
    # loose parts: connected components via union-find over edges
    parent = np.arange(len(points))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for p, q in e:
        rp, rq = root(p), root(q)
        if rp != rq:
            parent[rp] = rq
    use = np.unique(seg)
    detach = len({root(i) for i in use})
    from mathutils.kdtree import KDTree
    kd = KDTree(len(points))
    for i, p in enumerate(points):
        kd.insert(p, i)
    kd.balance()
    sim = float(np.median([kd.find((p[0], -p[1], p[2]))[2] for p in points[::max(len(points) // 3000, 1)]]))
    lic = str(b.get("license_name", "")).upper()
    check = [
        qc.check("KA-01", "open license + attribution", lic, any(lic.startswith(x) for x in ALLOWED_LICENSES) and
               bool(b.get("attribution")), "CC0/CC-BY/MIT + written attribution"),
        qc.check("KA-02", "edge leak (non-manifold)", leak, leak <= 0.001, "<= 0.1% of edges (SDF needs a closed mesh; "
               "negative test: a 10% hole = 0.3-1%, which passed the old 1% threshold)"),
        qc.check("KA-03", "normal orientation (volume > 0)", vol, vol > 0, "signed volume > 0"),
        qc.check("KA-04", "sliver triangles (ratio > 10)", flake, flake <= 0.05, "<= 5%"),
        qc.check("KA-05", "triangle count", len(seg), 2000 <= len(seg) <= 500000, "2.000-500.000"),
        qc.check("KA-06", "loose parts", detach, detach <= b.get("max_detached", 3), f"<= {b.get('max_detached', 3)}"),
        qc.check("KA-07", "Y mirror symmetry (median)", sim, sim <= b.get("asset_symmetry_tolerance", 0.5),
               f"<= {b.get('asset_symmetry_tolerance', 0.5)} mm (symmetric asset)"),
    ]
    weight = dict(zip([f"KA-0{i}" for i in range(1, 8)], (30, 15, 10, 10, 10, 10, 15)))
    score = sum(weight[c["id"]] for c in check if c["passed"])
    value = "A" if score >= 85 and check[0]["passed"] else "B" if score >= 65 and check[0]["passed"] else "C"
    return dict(score=score, value=value, check=check)


def asset_negative_tests(points, seg, b):
    """Each required KA must fail on a deliberately corrupted asset (repo rule: every new QC needs a negative test)."""
    n = len(seg)
    flake = np.c_[np.arange(0, 3000, 3), np.arange(1, 3000, 3), np.arange(2, 3000, 3)] % len(points)
    t_flake = np.vstack([points, points[flake[:, 0]] + [0, 0, 0], points[flake[:, 0]] + [5.0, 0, 0],
                          points[flake[:, 0]] + [10.0, 0.001, 0]])
    k = len(points)
    m = np.arange(len(flake))
    flake_seg = np.vstack([seg, np.c_[k + m, k + len(flake) + m, k + 2 * len(flake) + m]] * 1)
    corrupt = [
        ("empty license", points, seg, dict(b, license_name="", attribution=""), "KA-01"),
        ("10% of triangles removed", points, seg[n // 10:], b, "KA-02"),
        ("normals flipped", points, seg[:, ::-1], b, "KA-03"),
        ("sliver triangles added", t_flake, np.vstack([flake_seg] + [flake_seg[n:]] * 40), b, "KA-04"),
        ("cut down to 1,000 triangles", points, seg[:1000], b, "KA-05"),
        ("5 separate copies", np.vstack([points + [60.0 * i, 0, 0] for i in range(5)]),
         np.vstack([seg + len(points) * i for i in range(5)]), b, "KA-06"),
        ("+Y half shifted 2 mm", points + np.where(points[:, 1:2] > 0, [0, 0, 2.0], 0), seg, b, "KA-07"),
    ]
    result = []
    for name, t, f, bb, required in corrupt:
        check = asset_value(t, f, bb)["check"]
        ok, failed = qc.caught(check, [required])
        result.append(dict(name=name, required=[required], failed=failed, caught=ok))
        print(f"  negative asset {'OK ' if ok else 'LEAK'} {name}: failed {failed}")
    return result


REQUIRED_FEATURES = {  # KA-08: anatomical features required per entity kind (lesson: a grade-A knight asset had no eyes)
    "knight": ("eye", "ear", "nostril", "mouth", "mane"),
}


def completeness(r):
    """KA-08: every required feature of the entity kind must be present, either in the asset (`asset_features`, declared by
    Claude after inspecting a close-up render of the asset) or as a [[detail]] whose name contains the feature.
    Value = the missing features."""
    result = []
    for b in r["part"]:
        if b["recipe"] != "asset" or "object_kind" not in b:
            continue
        exists = set(b.get("asset_features", ())) | {c for c in REQUIRED_FEATURES.get(b["object_kind"], ())
                                             for d in r.get("detail", []) if c in d.get("name", "")}
        missing = [c for c in REQUIRED_FEATURES.get(b["object_kind"], ()) if c not in exists]
        result.append(qc.check("KA-08", f"required feature completeness ({b['object_kind']})", missing or "complete", not missing,
                            "all: " + ", ".join(REQUIRED_FEATURES.get(b["object_kind"], ("unknown kind",)))))
    return result


def completeness_negative_tests(r):
    """KA-08 must fail when the eye details are removed (the original knight asset defect)."""
    corrupt = dict(r, detail=[d for d in r.get("detail", []) if "eye" not in d.get("name", "")])
    ok, failed = qc.caught(completeness(corrupt), ["KA-08"])
    print(f"  negative asset {'OK ' if ok else 'LEAK'} eye details removed: failed {failed}")
    return [dict(name="eye details removed", required=["KA-08"], failed=failed, caught=ok)]


def asset_field(b, origin, vox, shape, Z, negative=False):
    """Asset SDF on the builder grid (OpenVDB level set from triangles; values in mm, negative inside) + bottom z cut."""
    import openvdb
    from . import sdf
    points, seg = load_asset(b)
    rpt = asset_value(points, seg, b)
    if negative:
        rpt["negative"] = asset_negative_tests(points, seg, b)
    p = ((points - np.asarray(origin)) / vox).astype(np.float32)  # grid index coordinates
    g = openvdb.FloatGrid.createLevelSetFromPolygons(p, triangles=seg.astype(np.uint32),
                                                     transform=openvdb.createLinearTransform(1.0),
                                                     exBandWidth=4.0, inBandWidth=1.0e4)
    m = np.full(shape, g.background, np.float32)
    g.copyToArray(m, ijk=(0, 0, 0))
    m *= vox  # index units -> mm
    if "extend_from_z" in b:  # the cross section at that z is extended straight down (body merges into the base, not a "marble")
        k0 = int(np.abs(Z[0, 0, :] - b["extend_from_z"]).argmin())
        m[:, :, :k0] = m[:, :, k0:k0 + 1]
    if "cut_z" in b:
        m = sdf.subtract(m, Z - b["cut_z"], b.get("cut_smoothness", 0.0))  # drop the region z < cut_z (SDF negative below)
    return m, rpt
