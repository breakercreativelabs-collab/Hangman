"""Product shot numeric QC, scene part (no render): QC-01/02/03/04/06/07/08/09/11.
Each check = one row in QC_RULES.md (same ID). Every check is a dict: id, name, value, threshold, passed, context.
"""
import math

import bpy
import numpy as np
from mathutils import Vector, interpolate

from ...core.camera import projection
from ...core.qc import check
from ...core.scene import COLLECTION, control, fcurves, product_object, root as product_root, product_points
from .threshold import THRESHOLD
from .framing import use_camera
from .verbs import product_size


def sample_frames(n=9):
    sc = bpy.context.scene
    return sorted({round(f) for f in np.linspace(sc.frame_start, sc.frame_end, n)})


# ---------------- geometry ----------------
def qc_floor_contact():
    """QC-01: product is not floating/sunk, checked across the turntable."""
    sc, worst, f_bad = bpy.context.scene, 0.0, None
    for f in sample_frames():
        sc.frame_set(f)
        z = float(product_points()[:, 2].min()) * 1000
        if abs(z) >= abs(worst):
            worst, f_bad = z, f
    sc.frame_set(sc.frame_start)
    a = THRESHOLD["floor_contact_mm"]
    status = "floating" if worst > a else "sunk" if worst < -a else "grounded"
    return check("QC-01", "floor_contact_z_min_mm", worst, abs(worst) <= a, f"|z| <= {a} mm",
               f"{status}, worst at frame {f_bad}")


def qc_camera(cam):
    """QC-02 frame fill, QC-03 not clipped (all sample frames), QC-08 camera outside the product."""
    sc = bpy.context.scene
    use_camera(cam)
    result, fill0, margin, f_m = [], None, 1.0, None
    for f in sample_frames():
        sc.frame_set(f)
        pts = product_points()
        u, v, z = projection(cam, pts)
        if fill0 is None:
            fill0 = max(u.max() - u.min(), v.max() - v.min())
        m = float(min(u.min(), v.min(), 1 - u.max(), 1 - v.max())) if (z > 0).all() else -1.0
        if m < margin:
            margin, f_m = m, f
    sc.frame_set(sc.frame_start)
    A = THRESHOLD
    result.append(check("QC-02", "frame_fill", float(fill0), A["fill_min"] <= fill0 <= A["fill_max"],
                     f"{A['fill_min']}..{A['fill_max']}", cam.name))
    result.append(check("QC-03", "edge_margin_min", margin, margin >= A["margin_min"], f">= {A['margin_min']}",
                     f"{cam.name}, worst frame {f_m}" + (" (CLIPPED)" if margin < 0 else "")))
    pts = product_points()
    lo, hi = pts.min(0), pts.max(0)
    c = np.array(cam.location)
    is_inside = bool(((c >= lo) & (c <= hi)).all())
    distance = float(np.linalg.norm(pts - c, axis=1).min())
    limit = cam.data.clip_start * A["camera_distance_min_x_clip"]
    result.append(check("QC-08", "camera_to_product_distance_m", distance, (not is_inside) and distance > limit,
                     f"outside bbox and > {A['camera_distance_min_x_clip']} x clip_start", cam.name))
    return result


def _uv_at(ob, idx, location):
    """UV coordinate at point `location` (object local space) on face `idx` (barycentric interpolation)."""
    me = ob.data
    if not me.uv_layers:
        return None
    poly = me.polygons[idx]
    w = interpolate.poly_3d_calc([me.vertices[v].co for v in poly.vertices], location)
    uv = me.uv_layers.active.data
    return Vector(sum((uv[li].uv * wi for li, wi in zip(poly.loop_indices, w)), Vector((0, 0))))


def qc_front(cam):
    """QC-04: logo (front side) faces the camera in the hero frame. A ray from the camera to the product axis at logo
    height must hit a LABEL material, and u at the hit point must equal the logo u (delta in degrees of perimeter).
    Without logo data (import without logo_u/logo_z): only the declared front direction (weaker)."""
    sc = bpy.context.scene
    sc.frame_set(sc.frame_start)
    use_camera(cam)
    root = product_root()
    h, _ = product_size()
    center = root.matrix_world @ Vector((0, 0, root.get("logo_z", h / 2)))
    front = (root.matrix_world.to_3x3() @ Vector((0, -1, 0)))
    to_camera = cam.location - center
    front.z = to_camera.z = 0
    decl_angle = math.degrees(front.angle(to_camera)) if front.length and to_camera.length else 180.0
    dg = bpy.context.evaluated_depsgraph_get()
    is_hit, _, _, _, ob, _ = sc.ray_cast(dg, cam.location, (center - cam.location).normalized())
    product = {o.name for o in product_object()}
    has_label = any(m and m.name.startswith("LABEL") for o in product_object() for m in o.data.materials)
    mat_name, logo_angle = "", None
    if is_hit and ob and ob.name in product:
        mi = ob.matrix_world.inverted()
        ok, hit_loc, _, idx = ob.ray_cast(mi @ cam.location, (mi.to_3x3() @ (center - cam.location)).normalized())
        if ok:
            mats = ob.data.materials
            mat_name = mats[ob.data.polygons[idx].material_index].name if len(mats) else ""
            uv = _uv_at(ob, idx, hit_loc)
            if uv is not None and "logo_u" in root:
                logo_angle = abs((uv.x - root["logo_u"] + 0.5) % 1.0 - 0.5) * 360
    visible = bool(is_hit and ob and ob.name in product and (mat_name.startswith("LABEL") or not has_label))
    a = THRESHOLD["front_angle_max"]
    passed = decl_angle <= a and visible and (logo_angle is None or logo_angle <= a)
    value = logo_angle if logo_angle is not None else decl_angle
    return [check("QC-04", "logo_angle_to_camera_deg" if logo_angle is not None else "declared_front_angle_deg",
                float(value), passed, f"<= {a} deg + ray is_hit LABEL",
                f"{cam.name}; declared {decl_angle:.1f} deg; ray hit: {ob.name if is_hit and ob else 'none'} / "
                f"{mat_name or '-'}")]


def qc_keyframe():
    """QC-06: turntable is not linear: interpolation is not LINEAR/CONSTANT and there is easing at start & end."""
    tt = product_root().parent
    fcs = fcurves(tt)
    if not fcs:
        return [check("QC-06", "nonlinear_keyframe", "no animation", False, "turntable present", "TURNTABLE")]
    sc = bpy.context.scene
    fc = next((f for f in fcs if f.data_path == "rotation_euler" and f.array_index == 2), fcs[0])
    interp = sorted({k.interpolation for k in fc.keyframe_points})
    f0, f1 = sc.frame_start, sc.frame_end
    t = np.linspace(f0, f1, 401)
    a = np.array([fc.evaluate(x) for x in t])
    v = np.abs(np.diff(a))
    mean = v.mean() if v.mean() > 0 else 1e-9
    n = max(1, len(v) // 20)
    ratio = float(max(v[:n].mean(), v[-n:].mean()) / mean)
    limit = THRESHOLD["tip_speed_max"]
    passed = not ({"LINEAR", "CONSTANT"} & set(interp)) and ratio <= limit
    return [check("QC-06", "tip_speed_ratio", ratio, passed, f"<= {limit}, interpolation not LINEAR",
                f"interpolation {interp}, {f1 - f0 + 1} frames")]


def qc_dimension():
    """QC-07: real-world size. Test products are compared with the datasheet spec; imports: plausible range only."""
    root = product_root()
    bpy.context.scene.frame_set(bpy.context.scene.frame_start)
    p = product_points()
    height = float(p[:, 2].max() - p[:, 2].min()) * 1000
    still = float(2 * np.hypot(p[:, 0], p[:, 1]).max()) * 1000
    tol = THRESHOLD["dimension_mm"]
    if "spec_width_mm" in root:  # box/flat: width (X, front side) and thickness (Y) checked separately
        dt = height - root["spec_height_mm"]
        dl = float(p[:, 0].max() - p[:, 0].min()) * 1000 - root["spec_width_mm"]
        dk = float(p[:, 1].max() - p[:, 1].min()) * 1000 - root["spec_thickness_mm"]
        return [check("QC-07", "height_delta_mm", dt, abs(dt) <= tol, f"|d| <= {tol} mm", f"height {height:.2f} mm"),
                check("QC-07", "width_delta_mm", dl, abs(dl) <= tol, f"|d| <= {tol} mm", "width X (front side)"),
                check("QC-07", "thickness_delta_mm", dk, abs(dk) <= tol, f"|d| <= {tol} mm", "thickness Y")]
    if "spec_height_mm" in root:
        dt = height - root["spec_height_mm"]
        # diameter: the widest part may be the label/cap, slightly above the body diameter
        dd = still - root["spec_diameter_mm"]
        return [check("QC-07", "height_delta_mm", dt, abs(dt) <= tol, f"|d| <= {tol} mm", f"height {height:.2f} mm"),
                check("QC-07", "diameter_delta_mm", dd, abs(dd) <= tol, f"|d| <= {tol} mm", f"diameter {still:.2f} mm")]
    return [check("QC-07", "height_mm", height, 10 <= height <= 3000, "10..3000 mm (no spec)", "imported product")]


def qc_standard():
    """QC-09: standard .blend: 4 populated collections + CONTROL with the required properties."""
    subtract = [k for k in COLLECTION if not bpy.data.collections.get(k) or not bpy.data.collections[k].all_objects]
    c = control()
    required = ("standard", "product", "variant_color", "hex_color", "light_intensity", "light_preset",
             "duration_seconds", "easing", "fps", "fill_target")
    subtract += [f"CONTROL[{k}]" for k in required if c is None or k not in c]
    return [check("QC-09", "blend_standard_missing", len(subtract), not subtract, "= 0", ", ".join(subtract) or "complete")]


def is_clear(m):
    """Clear glass/plastic material: Principled with dominant transmission and IOR >= threshold (not liquid)."""
    if not (m and m.node_tree):
        return False
    b = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    return bool(b) and b.inputs["Transmission Weight"].default_value > 0.5 \
        and b.inputs["IOR"].default_value >= THRESHOLD["glass_ior_min"]


def qc_glass():
    """QC-11 (C-11): clear glass/plastic objects must be hollow. Solid glass refracts the background & the label back side
    into a dark band. A horizontal ray crosses the object at 40% of its height: ratio of the first wall thickness to
    the total width (solid ~1.0) and the number of surfaces crossed (hollow >= 4)."""
    dg, result = bpy.context.evaluated_depsgraph_get(), []
    for ob in product_object():
        if not any(is_clear(s.material) for s in ob.material_slots):
            continue
        bb = [Vector(c) for c in ob.bound_box]
        lo, hi = Vector([min(c[i] for c in bb) for i in range(3)]), Vector([max(c[i] for c in bb) for i in range(3)])
        z, cy = lo.z + 0.4 * (hi.z - lo.z), (lo.y + hi.y) / 2
        origin, direction, is_hit = Vector((lo.x - 0.01, cy, z)), Vector((1, 0, 0)), []
        for _ in range(16):
            ok, loc, *_ = ob.ray_cast(origin, direction, depsgraph=dg)  # object local space
            if not ok:
                break
            is_hit.append(loc.x)
            origin = loc + direction * 1e-5
        if len(is_hit) < 2:
            continue
        ratio = (is_hit[1] - is_hit[0]) / max(is_hit[-1] - is_hit[0], 1e-9)
        a = THRESHOLD["wall_ratio_max"]
        result.append(check("QC-11", "hollow_glass_wall_ratio", ratio, len(is_hit) >= 4 and ratio <= a,
                         f"<= {a} and >= 4 surfaces",
                         f"{ob.name}: {len(is_hit)} surfaces, wall {(is_hit[1] - is_hit[0]) * 1000:.1f} mm"))
    return result


def qc_scene(camera):
    """All non-image checks for the current scene."""
    result = qc_standard() + qc_dimension() + [qc_floor_contact()] + qc_keyframe() + qc_glass()
    for cam in camera:
        result += qc_camera(cam) + qc_front(cam)
    return result
