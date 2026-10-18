"""Builder: shape design (TOML, written by Claude from a prompt) -> SDF -> mesh -> numeric QC -> contact sheet render.

Design contract (see projects/chess_knight_v1/design.toml): [entity] (target size, voxel), [[part]] (recipe lathe |
cushion), [[detail]] (subtract_/add_ sphere | capsule | box | capsule_series | cone | line | ellipsoid, carve_plane),
[[skeleton]] (local u-y-w coordinates + scale, e.g. along the head; a detail uses `skeleton = name`), [make_material], [qc].
The builder never guesses: a missing key or unknown recipe is a hard error (Claude completes the design).
"""
import os
import time
import tomllib

import numpy as np

from ...core import io, log, qc
from . import sdf

RECIPE = ("lathe", "cushion", "asset")
DETAIL = ("subtract_sphere", "add_sphere", "subtract_capsule", "subtract_box", "add_box", "subtract_capsule_series", "add_cone",
          "subtract_cone", "carve_plane", "subtract_line", "add_line", "add_ellipsoid", "subtract_ellipsoid")


def load_design(path):
    with open(path, "rb") as f:
        r = tomllib.load(f)
    for b in r["part"]:
        if b["recipe"] not in RECIPE:
            raise ValueError(f"recipe '{b['recipe']}' is not in the catalog {RECIPE} (record it as a gap)")
    for d in r.get("detail", []):
        if d["kind"] not in DETAIL:
            raise ValueError(f"detail '{d['kind']}' is not in the catalog {DETAIL} (record it as a gap)")
    return r


def limit(r):
    """Grid box (mm) holding all parts + 2 mm, or [entity] limit_mm when given (shapes assembled from primitives)."""
    if "limit_mm" in r["entity"]:
        return [list(v) for v in r["entity"]["limit_mm"]]
    xs, ys, zs = [], [], []
    for b in r["part"]:
        if b["recipe"] == "lathe":
            rmax = max(p[0] for p in b["profile"])
            xs += [-rmax, rmax]
            ys += [-rmax, rmax]
            zs += [p[1] for p in b["profile"]]
        else:
            xs += [p[0] for p in b["silhouette"]]
            zs += [p[1] for p in b["silhouette"]]
            hmax = max(t[1] for t in b["thickness_z"])
            ys += [-hmax, hmax]
    for d in r.get("detail", []):
        if d["kind"].endswith("cone"):
            for p, rad in ((d["a"], d["r1"]), (d["b"], d["r2"])):
                xs += [p[0] - rad, p[0] + rad]
                ys += [-abs(p[1]) - rad, abs(p[1]) + rad]
                zs += [p[2] - rad, p[2] + rad]
    return [min(xs) - 2, min(ys) - 2, min(zs) - 2], [max(xs) + 2, max(ys) + 2, max(zs) + 2]


def to_world(skeleton, p, s=1.0):
    """Point [u, y, w] in the local skeleton (origin [x, z], downward tilt angle in degrees) -> world [x, y, z]; s = Y mirror."""
    if skeleton is None:
        return (p[0], s * p[1], p[2])
    a, k = np.radians(skeleton["angle"]), skeleton.get("scale", 1.0)
    ax, az = skeleton["origin"]
    u, y, w = p[0] * k, p[1] * k, p[2] * k
    return (ax + u * np.cos(a) + w * np.sin(a), s * y, az - u * np.sin(a) + w * np.cos(a))


def local(skeleton, X, Y, Z):
    """World coordinates -> local skeleton (u, y, w) in local units + scale (mm per unit)."""
    if skeleton is None:
        return X, Y, Z, 1.0
    a, k = np.radians(skeleton["angle"]), skeleton.get("scale", 1.0)
    dx, dz = X - skeleton["origin"][0], Z - skeleton["origin"][1]
    return (dx * np.cos(a) - dz * np.sin(a)) / k, Y / k, (dx * np.sin(a) + dz * np.cos(a)) / k, k


def world_direction(skeleton, n, s=1.0):
    """Local direction vector (u, y, w) -> world (no scale)."""
    if skeleton is None:
        return np.array((n[0], s * n[1], n[2]), float)
    a = np.radians(skeleton["angle"])
    return np.array((n[0] * np.cos(a) + n[2] * np.sin(a), s * n[1], -n[0] * np.sin(a) + n[2] * np.cos(a)), float)


def plane_area(points, faces, r):
    """KC-07 for each carve_plane with `min_area_mm2`: flat plane area in mm2 (faces <= 0.1 mm from the plane, normal
    <= 8 deg, within 1.5 x the region) and edge fold angle = 75th percentile of the face-normal angle, against the plane
    normal, in a 0.7 mm ring outside the plane (hard edge = large, smoothed = small). Mirrored sides: the smaller wins."""
    skeleton = {k["name"]: k for k in r.get("skeleton", [])}
    t = sdf.triangle(faces)
    a, b, c = points[t[:, 0]], points[t[:, 1]], points[t[:, 2]]
    center, cross = (a + b + c) / 3, np.cross(b - a, c - a)
    area = np.linalg.norm(cross, axis=1) / 2
    nf = cross / np.maximum(2 * area[:, None], 1e-12)
    from mathutils.kdtree import KDTree
    kd = KDTree(len(center))
    for i, p in enumerate(center):
        kd.insert(p, i)
    kd.balance()
    result = []
    for d in r.get("detail", []):
        if d["kind"] != "carve_plane" or "min_area_mm2" not in d:
            continue
        kr = skeleton.get(d.get("skeleton"))
        k = kr.get("scale", 1.0) if kr else 1.0
        per_side = []
        for s in ((1.0, -1.0) if d.get("mirror") else (1.0,)):
            n = world_direction(kr, d["normal"], s)
            n /= np.linalg.norm(n)
            p0, pw = np.array(to_world(kr, d["points"], s)), np.array(to_world(kr, d["center"], s))
            near = np.linalg.norm(center - pw, axis=1) <= 1.5 * k * max(d["half_size"])
            select = near & (np.abs((center - p0) @ n) <= 0.1) & (nf @ n >= np.cos(np.radians(8)))
            # 0.7 mm ring outside the plane: non-plane faces near plane faces; hard edge = normal far from n
            ring = {j for i in np.flatnonzero(select)[::3] for _, j, _ in kd.find_range(center[i], 0.7)}
            ring = np.array(sorted(j for j in ring if not select[j]), int)
            angle = np.degrees(np.arccos(np.clip(nf[ring] @ n, -1, 1))) if len(ring) else np.zeros(0)
            per_side.append((float(area[select].sum()), float(np.percentile(angle, 75)) if len(angle) else 0.0))
        result.append((d["name"], min(v[0] for v in per_side), d["min_area_mm2"], min(v[1] for v in per_side),
                      d.get("min_edge_angle", r["qc"].get("min_edge_angle", 20.0))))
    return result


def _detail(X, Y, Z, d, mirror_y, skeleton=None):
    s = -1.0 if mirror_y else 1.0
    j = d["kind"]
    world = lambda p: to_world(skeleton, p, s)  # noqa: E731
    k = skeleton.get("scale", 1.0) if skeleton else 1.0  # sizes (r, radius) follow the skeleton scale
    d = {kk: ([v * k for v in vv] if kk == "radius" else vv * k if kk in ("r", "r1", "r2") else vv) for kk, vv in d.items()}
    if "points" in d and skeleton:
        d["points"] = [list(t[:3]) + [t[3] * k] if len(t) > 3 else t for t in d["points"]]
    if j in ("subtract_sphere", "add_sphere"):
        return sdf.sdf_sphere(X, Y, Z, world(d["center"]), d["r"])
    if j.endswith("ellipsoid"):
        angle = (skeleton["angle"] if skeleton else 0.0) + d.get("angle", 0.0)
        return sdf.ellipsoid(X, Y, Z, world(d["center"]), d["radius"], angle)
    if j.endswith("cone"):
        return sdf.cone(X, Y, Z, world(d["a"]), world(d["b"]), d["r1"], d["r2"], d.get("scale", (1.0, 1.0, 1.0)))
    if j == "subtract_capsule":
        return sdf.sdf_capsule(X, Y, Z, world(d["a"]), world(d["b"]), d["r"])
    if j.endswith("_box"):  # in a local skeleton the box rotates with it (e.g. the bishop's slanted mitre cut)
        if skeleton:
            U, V, W, _ = local(skeleton, X, Y, Z)
            p = d["center"]
            return sdf.box(U, V * s, W, p, d["half_size"], d["r"] / k) * k  # half_size: local units
        return sdf.box(X, Y, Z, world(d["center"]), d["half_size"], d["r"])
    if j.endswith("_line"):  # tube along a polyline [x, y, z(, r)]; per-point r = tapered tube
        field = None
        for a, b in zip(d["points"][:-1], d["points"][1:]):
            ra, rb = (a[3] if len(a) > 3 else d["r"]), (b[3] if len(b) > 3 else d["r"])
            k = sdf.cone(X, Y, Z, world(a), world(b), ra, rb, d.get("scale", (1.0, 1.0, 1.0)))
            field = k if field is None else np.minimum(field, k)
        return field
    field = None  # subtract_capsule_series: Y-aligned capsule of length width_y at each point (x, z)
    for x, z in d["points"]:
        k = sdf.sdf_capsule(X, Y, Z, (x, -d["width_y"] / 2, z), (x, d["width_y"] / 2, z), d["r"])
        field = k if field is None else np.minimum(field, k)
    return field


def circular_pattern(entries):
    """A detail with `spin_n` = n copies rotated around the Z axis (starting at `spin_start` degrees), world coordinates.
    For notched crowns, rows of holes, wheel spokes, etc."""
    for d in entries:
        n = d.get("spin_n")
        if not n:
            yield d
            continue
        for i in range(n):
            a = np.radians(d.get("spin_start", 0.0) + 360.0 * i / n)
            c, s_ = np.cos(a), np.sin(a)
            yield {k: ([v[0] * c - v[1] * s_, v[0] * s_ + v[1] * c, v[2]] if k in ("center", "a", "b") else v)
                   for k, v in d.items() if k not in ("spin_n", "spin_start")}


def surface_y(total, x, y, z, px, pz):
    """Surface y (mm, +Y side) of the current field in column (px, pz): outermost zero along Y, linear interpolation."""
    i, k = int(np.abs(x - px).argmin()), int(np.abs(z - pz).argmin())
    coll = total[i, :, k]
    inner = np.flatnonzero(coll < 0)
    if not len(inner):
        raise ValueError(f"detail at (x {px}, z {pz}) does not touch the object (empty column)")
    j = inner.max()
    if j + 1 >= len(y):
        return float(y[j])
    a, b = coll[j], coll[j + 1]
    return float(y[j] + (y[j + 1] - y[j]) * a / (a - b))


def snap_to_surface(d, total, x, y, z):
    """Detail Y position relative to the surface (not guessed): `depth` (carved, mm inward) or `bump` (raised, mm outward).
    Y = surface +/- radius; applies to the center or to each line point. If the shape changes, the detail stays attached."""
    d = dict(d)
    r = d.get("r", d.get("r1", 0.0))
    shift = (r - d["depth"]) if "depth" in d else (d["bump"] - r)
    if "center" in d:
        px, _, pz = d["center"]
        d["center"] = [px, surface_y(total, x, y, z, px, pz) + shift, pz]
    if "points" in d and len(d["points"][0]) >= 3:
        d["points"] = [[t[0], surface_y(total, x, y, z, t[0], t[2]) + shift, t[2]] + list(t[3:]) for t in d["points"]]
    return d


def field(r, step=None):
    """SDF of the full design on the voxel grid. Returns (field [x, y, z], origin mm, vox mm).
    step(name, field, origin, vox): called after each part/detail (live mode)."""
    vox = r["entity"]["voxel_mm"]
    x, y, z = sdf.grid(*limit(r), vox)
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    total = None
    for b in r["part"]:
        if b["recipe"] == "asset":  # asset path: openly licensed model -> SDF (asset.py), scored KA-01..07
            from . import asset
            m, rpt = asset.asset_field(b, (float(x[0]), float(y[0]), float(z[0])), vox, X.shape, Z,
                                     negative=r.get("_mode") == "full")
            r.setdefault("_asset_report", []).append(dict(part=b["name"], model=b["model"], entity=b["entity"],
                                                         license_name=b.get("license_name"), attribution=b.get("attribution"), **rpt))
            for c in rpt["check"]:
                print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']} ({c['threshold']})")
            print(f"  asset {b['entity']}: score {rpt['score']} value {rpt['value']}")
        elif b["recipe"] == "lathe":  # smoothed_profile = Catmull-Rom curve step in mm (absent = polygon as is)
            prof = sdf.smooth_profile(b["profile"], b["smoothed_profile"], b.get("sharp_profile", ())) if "smoothed_profile" in b else b["profile"]
            m = sdf.lathe(X, Y, Z, prof, vox)
        else:
            m = sdf.cushion(x, y, z, b)
        total = m if total is None else sdf.merge(total, m, r["entity"]["smooth_union_mm"])
        if step:
            step(b["name"], total, (float(x[0]), float(y[0]), float(z[0])), vox)
    skeleton = {k["name"]: k for k in r.get("skeleton", [])}
    for d in circular_pattern(r.get("detail", [])):
        kr = skeleton[d["skeleton"]] if "skeleton" in d else None
        if "depth" in d or "bump" in d:
            d = snap_to_surface(d, total, x, y, z)
        for mirror in ((False, True) if d.get("mirror") else (False,)):
            if d["kind"] == "carve_plane":  # in the local skeleton if given (the plane follows the head direction)
                s_ = -1.0 if mirror else 1.0
                t_, n_, p_ = d["points"], d["normal"], d["center"]
                U, V, W, k = local(kr, X, Y, Z)
                total = sdf.carve(total, U, V, W, (t_[0], s_ * t_[1], t_[2]), (n_[0], s_ * n_[1], n_[2]),
                                  (p_[0], s_ * p_[1], p_[2]), d["half_size"], d.get("transition", 1.5), k)
                continue
            m = _detail(X, Y, Z, d, mirror, kr)
            k = d.get("smoothness", 0.0)
            total = sdf.merge(total, m, k) if d["kind"].startswith("add") else sdf.subtract(total, m, k)
        if step:
            step(d.get("name", d["kind"]), total, (float(x[0]), float(y[0]), float(z[0])), vox)
    return total, (float(x[0]), float(y[0]), float(z[0])), vox


def manifold_edges(faces):
    """(edge count, edges not shared by exactly 2 faces)."""
    m = np.asarray(faces)
    e = np.sort(np.stack([m, np.roll(m, -1, axis=1)], -1).reshape(-1, 2), axis=1)
    _, n = np.unique(e, axis=0, return_counts=True)
    return len(n), int((n != 2).sum())


def mirror_distance(points, faces, step=5):
    """Y symmetry error (mm): max distance from mirrored points (subsampled) to the mesh SURFACE (mathutils BVH; robust to decimate)."""
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons(points.tolist(), np.asarray(faces).tolist())
    return max(bvh.find_nearest((p[0], -p[1], p[2]))[3] for p in points[::step])


def qc_mesh(points, faces, r):
    """QC KC-01..06 (builder QC_RULES.md) on a mesh in mm. Returns the list of checks."""
    o, q = r["entity"], r["qc"]
    height = float(points[:, 2].max() - points[:, 2].min())
    bottom = points[points[:, 2] < points[:, 2].min() + 3.0]
    still = float(2 * np.sqrt(bottom[:, 0] ** 2 + bottom[:, 1] ** 2).max())
    n_edges, bad = manifold_edges(faces)
    symmetry = mirror_distance(points, faces)
    tb = sdf.centroid(points, faces)
    tread = bottom[bottom[:, 2] < points[:, 2].min() + 0.05]
    r_tread = float(np.sqrt(tread[:, 0] ** 2 + tread[:, 1] ** 2).max()) if len(tread) else 0.0
    r_tb = float(np.hypot(tb[0], tb[1]))
    n_seg = len(sdf.triangle(faces))
    plane = plane_area(points, faces, r)
    subtract = [f"{n} {v:.1f}mm2/{a:.0f}deg" for n, v, m, a, ma in plane if v < m or a < ma]
    extra = [qc.check("KC-07", "hard edges of carved planes", min((a for *_, a, _ in plane), default=0.0), not subtract,
                       "each plane: area >= min_area_mm2 AND edge fold angle (P75) >= min_edge_angle",
                       "; ".join(f"{n} {v:.1f}mm2 {a:.0f}deg" for n, v, _, a, _ in plane) +
                       (f" | SHORT: {subtract}" if subtract else ""))] if plane else []
    return extra + [
        qc.check("KC-01", "height", height, abs(height - o["height_mm"]) <= q["height_tolerance_mm"],
               f"{o['height_mm']} +-{q['height_tolerance_mm']} mm"),
        qc.check("KC-02", "base diameter", still, abs(still - o["base_diameter_mm"]) <= q["diameter_tolerance_mm"],
               f"{o['base_diameter_mm']} +-{q['diameter_tolerance_mm']} mm"),
        qc.check("KC-03", "manifold", bad, bad == 0, f"0 of {n_edges} edges"),
        qc.check("KC-04", "Y mirror symmetry", symmetry, symmetry <= q["symmetry_tolerance_mm"],
               f"<= {q['symmetry_tolerance_mm']} mm"),
        qc.check("KC-05", "stands upright", r_tb, r_tb <= 0.5 * r_tread, f"center of mass <= 0.5 x footprint r ({r_tread:.1f})",
               f"center of mass {tb.round(2).tolist()}"),
        qc.check("KC-06", "triangle count", n_seg, n_seg <= q["max_polygons"], f"<= {q['max_polygons']}"),
    ]


def smooth(points, faces, n):
    """Simple Laplacian smoothing, n passes (KC-07 negative-test corruptor: mimics 'everything soft')."""
    m = np.asarray(faces)
    e = np.vstack([m[:, [0, 1]], m[:, [1, 2]], m[:, [2, 0]]])
    t = points.copy()
    for _ in range(n):
        sums, counts = np.zeros_like(t), np.zeros(len(t))
        np.add.at(sums, e[:, 0], t[e[:, 1]])
        np.add.at(counts, e[:, 0], 1)
        t = 0.5 * t + 0.5 * sums / np.maximum(counts, 1)[:, None]
    return t


def negative_tests(points, faces, r):
    """Each required KC must fail on a deliberately corrupted mesh."""
    corrupt = [
        ("height x1.05", lambda t, m: (t * [1, 1, 1.05], m), ["KC-01"]),
        ("base 4% wider", lambda t, m: (t * [1.04, 1.04, 1], m), ["KC-02"]),
        ("one face removed", lambda t, m: (t, m[1:]), ["KC-03"]),
        ("shift Y 1 mm above z 30", lambda t, m: (t + np.where(t[:, 2:3] > 30, [0, 1.0, 0], 0), m), ["KC-04"]),
        ("head moved forward 25 mm", lambda t, m: (t + np.where(t[:, 2:3] > 13, [25.0, 0, 0], 0), m), ["KC-05"]),
        ("polygon limit 1000", lambda t, m: (t, m), ["KC-06"]),
    ] + ([("Laplacian smoothed 20x (fillet ~1.5 mm = everything soft)", lambda t, m: (smooth(t, m, 20), m), ["KC-07"])]
         if any(d["kind"] == "carve_plane" and "min_area_mm2" in d for d in r.get("detail", [])) else [])
    result = []
    for name, f, required in corrupt:
        t2, m2 = f(points.copy(), faces.copy())
        r2 = dict(r, qc=dict(r["qc"], max_polygons=1000)) if "polygon" in name else r
        check = qc_mesh(t2, m2, r2)
        ok, failed = qc.caught(check, required)
        value = {c["id"]: c["value"] for c in check if c["id"] in required}
        result.append(dict(name=name, required=required, failed=failed, caught=ok, required_value=value))
        print(f"  negative {'OK ' if ok else 'LEAK'} {name}: failed {failed}; value {value}")
    return result


def assemble(design_path, out, render=True, sample=32, mode="full", live=""):
    """Build the model from the design, run QC + negative tests, export .blend/.glb + contact sheet. Exit code 0 = pass.
    mode "preview": numeric QC still runs, no negative tests, 1 fast render (preview.png) - for iterations under 1 minute;
    "full" (handover/final): all negative tests + 6-view contact sheet + comparison.
    live = folder: each step is written there for the live-mode add-on in an open Blender (live.py)."""
    t0 = time.time()
    timings = {}
    r = load_design(design_path)
    r["_mode"] = mode
    capture = None
    if live:
        from .live import Recorder
        capture = Recorder(live, r["entity"]["name"])
    m, origin, vox = field(r, capture.step if capture else None)
    timings["field"] = round(time.time() - t0, 1)
    log.info(f"field {m.shape} vox {vox} mm ({timings['field']} s)")
    points, quad = sdf.sdf_to_mesh(m, origin, vox)
    del m
    log.info(f"mesh {len(points)} points, {len(quad)} quad ({time.time() - t0:.1f} s)")
    from . import staging
    ob = staging.mesh_object(r["entity"]["name"], points, quad, r["entity"].get("target_triangles"))
    points, faces = staging.data_mesh(ob)
    check = qc_mesh(points, faces, r)
    if r.get("_asset_report"):  # KA-08 counts toward pass: an asset missing a required feature (e.g. eye) fails
        from . import asset
        check += asset.completeness(r)
    for c in check:
        print(f"  {c['id']} {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['value']} ({c['threshold']})")
    timings["mesh_qc"] = round(time.time() - t0, 1)
    neg = negative_tests(points, faces, r) if mode == "full" else []
    for la in r.get("_asset_report", []):  # the asset judge's negative tests count too (required KA caught)
        neg += la.get("negative", [])
    if mode == "full" and any(c["id"] == "KA-08" for c in check):
        neg += asset.completeness_negative_tests(r)
    os.makedirs(out, exist_ok=True)
    staging.export(ob, out, blend=mode == "full")  # preview: the model lives in the open Blender, no .blend
    if capture:
        capture.done(os.path.join(out, "model.glb"))
    if not render:
        sheets = None
    elif mode == "preview":
        sheets = staging.preview(ob, out, viewpoints=r["entity"].get("preview", ((35, 18),)), r=r)
    else:
        sheets = staging.build_contact_sheet(ob, r, check, out, sample)
    timings["total"] = round(time.time() - t0, 1)
    report = dict(design=os.path.relpath(design_path, io.path_repo()), points=len(points),
                   triangle=len(sdf.triangle(faces)), seconds=round(time.time() - t0, 1), mode=mode, timings=timings,
                   sheets=os.path.relpath(sheets, io.path_repo()) if sheets else None, check=check,
                   negative=neg, asset=r.get("_asset_report"), **qc.summarize(check, neg),
                   recipe_used=[b["recipe"] for b in r["part"]] + [d["kind"] for d in r.get("detail", [])])
    io.write_json(os.path.join(out, "report_qc.json"), report)
    log.info(f"done {report['seconds']} s; passed {report['passed']}; negative "
             f"{report['caught_negatives']}/{report['negative_count']}")
    return 0 if report["passed"] and report["caught_negatives"] == report["negative_count"] else 1
