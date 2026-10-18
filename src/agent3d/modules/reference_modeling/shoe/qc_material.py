"""Shoe recipe QC M3 (project palette materials): AM-15 color per role (neutral render), AM-16 iridescent swoosh,
AM-17 translucent capsule, AM-18 non-default material slots."""
import math
import os

import bpy
import numpy as np
from mathutils import Vector

from ....core import color
from ....core.io import read_png
from ....core.camera import look_at as look_at_target, camera, ray
from ....core.material import bsdf
from ....core.qc import check
from ....core.render import render_image
from ....core.scene import product_object
from ...product_shot.api import qc_glass
from ..geometry import mesh_obj, mm
from ..qc_silhouette import mean_hue
from . import data
from .threshold import THRESHOLD
from .p3_material import P3
from .sole import CAPSULE_MARGIN
from .studio import use_studio


# ---------------- M3: material P3 (AM-15 .. AM-18) ----------------
# expected role for the MAIN slot (index 0) of each object, fixed by the M2 structure (not by the assigned material):
# materials swapped between objects are still detected. Other slots (e.g. lining on cut faces) are not sampled.
ROLE_OBJECT = {"upper": "lining", "panel_mesh": "upper_mesh", "tongue": "upper_mesh", "mudguard": "mudguard",
               "eyestay_lateral": "overlay_suede", "eyestay_medial": "overlay_suede", "heel_overlay": "overlay_suede",
               "swoosh_lateral": "swoosh", "swoosh_medial": "swoosh", "eyelet": "chrome_accent", "lace": "lace",
               "stitching": "lace", "midsole": "midsole", "outsole": "outsole", "air_capsule": "air_capsule"}
METAL = ("chrome_accent",)  # AM-15: metal color = environment reflection; only value is tested
FACING_MIN = 0.7      # AM-15: only pixels whose surface is nearly perpendicular to the camera (|n.v| >= 0.7; Fresnel/sheen/holo
                     # at grazing angles is not the material color)


def structure_role(ob, slot):
    """EXPECTED role for (object, slot) from the model structure, not from the assigned material. AM1: main slot of
    the objects in ROLE_OBJECT. Data panels (Task 11): slot 0 = ob['role']; midsole/outsole slot >= 1 = that object's
    base_width panels (order of [[model.panel]] with base_width = "midsole"/"outsole", merged by panel_data.build_base_panel).
    Anything else None (not sampled)."""
    if ob.get("panel"):
        return ob["role"] if slot == 0 else None
    if slot == 0:
        return ROLE_OBJECT.get(ob.name)
    if ob.name in ("midsole", "outsole"):
        base_width = [sp["role"] for sp in data.CONFIG.get("model", {}).get("panel", []) if sp.get("base_width") == ob.name]
        return base_width[slot - 1] if slot - 1 < len(base_width) else None
    return None


def role_pixels(path, cam, step=2, facing_min=FACING_MIN, entity=None):
    """Render colors (display space, PNG) per role: pixels whose camera ray first hits the main slot of a product
    object, not on a silhouette edge (all 4 neighbors = same object), and |n.v| >= facing_min. entity: limit to these
    object names. Returns {role: array (n, 3)}."""
    sc = bpy.context.scene
    rgb = read_png(path)
    h, w = rgb.shape[:2]
    dg = bpy.context.evaluated_depsgraph_get()
    is_hit = {}
    for x, y, o, d in ray(cam, w, h, step):
        ok, loc, nor, idx, ob, _ = sc.ray_cast(dg, o, d)
        if not ok or ob is None or (entity and ob.name not in entity):
            continue
        role = structure_role(ob, ob.data.polygons[idx].material_index)
        if role is None:
            continue
        is_hit[(x, y)] = ((ob.name, role), abs(nor.dot(d)))
    result = {}
    for (x, y), (name, look_at) in is_hit.items():
        neighbor = [is_hit.get((x + dx, y + dy), (None,))[0] for dx, dy in ((step, 0), (-step, 0), (0, step),
                                                                           (0, -step))]
        if look_at < facing_min or any(t != name for t in neighbor):
            continue
        result.setdefault(name[1], []).append(rgb[y, x])
    return {k: np.array(v) for k, v in result.items()}


def render_neutral(folder):
    """AM-15 color QC render: neutral review lighting (white lamps, grey world), exposure 0, Khronos PBR Neutral
    (same as product-shot QC-10). Returns [(path, camera)]."""
    sc = bpy.context.scene
    use_studio("review")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", 0.0
    denoise, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    px = data.model("viewpoints", "center_x_mm", 147.0) / 1000  # relative to the shoe middle (AM1 0.147 m: identical)
    center = Vector((px, 0.0, 0.06))
    cams = {"side_lateral": (camera("CAM_side", (px, 0.6, 0.068), (math.pi / 2, 0, math.pi), 0.32), None),
            "side_medial": (camera("CAM_side_m", (px, -0.6, 0.068), (math.pi / 2, 0, 0), 0.32), None),
            "three_quarter": (camera("CAM_34", (px - 0.317, 0.33, 0.23), (0, 0, 0), lens=50), center),
            "three_quarter_back": (camera("CAM_34b", (px + 0.313, -0.26, 0.24), (0, 0, 0), lens=50), center),
            "top": (camera("CAM_top", (px, 0.0, 0.6), (0, 0, 0), 0.32), None),
            # chrome eyelets (torus r 0.45 mm) are only measurable in a macro
            "macro_lace": (camera("CAM_m_lace", (0.10, 0.16, 0.22), (0, 0, 0), lens=60), Vector((0.145, 0.0, 0.112)))}
    out = []
    for name, (cam, t) in cams.items():
        if t is not None:
            look_at_target(cam, t)
        w, h = (640, 300) if name == "top" else (640, 340) if name.startswith("side_view") else (640, 420)
        out.append((render_image(cam, os.path.join(folder, f"color_{name}.png"), w, h, 32, False), cam))
    sc.cycles.use_denoising = denoise
    return out


def qc_role_color(views):
    """AM-15: color of each role in the neutral render vs the P3 hex. Median RGB of the role pixels (all views) -> HSV, QC-10 rule:
    target saturation >= 0.2: saturation ratio >= 0.60 and hue difference <= 20 deg; neutral/pastel target (< 0.2):
    |value difference| <= 0.35, pixel saturation <= pastel_sat_max, and hue <= 20 deg when pixel & target saturation >= 0.05
    (a pastel swapped with another pastel = different hue); metal (METAL): only |value difference| (color = reflected surroundings)."""
    collect = {}
    for path, cam in views:
        for k, v in role_pixels(path, cam).items():
            collect.setdefault(k, []).append(v)
    result, swatch = [], {}
    A = THRESHOLD
    for role in data.role_list():
        hexa = P3()[role][0]
        ht, st, vt = color.hsv(color.hex_rgb(hexa))
        if role not in collect:
            result.append(check("AM-15", f"color_{role}", "n/a", False, "role pixels exist", "not visible in the neutral render"))
            continue
        px = np.vstack(collect[role])
        med = np.median(px, 0)
        hp, sp, vp = color.hsv(med)
        swatch[role] = (hexa, med, len(px))
        if st >= 0.2:
            ratio, dh = sp / st, color.dhue(hp, ht)
            ok = ratio >= A["saturation_ratio_min"] and dh <= A["hue_delta_max"]
            result.append(check("AM-15", f"color_{role}", float(ratio), ok,
                             f"ratio sat >= {A['saturation_ratio_min']}, hue <= {A['hue_delta_max']} deg",
                             f"{hexa}: hue difference {dh:.1f} deg, median {np.round(med, 3).tolist()}, {len(px)} px"))
        elif role in METAL:
            dv = abs(vp - vt)
            ok = dv <= A["value_delta_max"]
            result.append(check("AM-15", f"color_{role}", float(dv), ok, f"|dV| <= {A['value_delta_max']} (metal)",
                             f"{hexa}: metal = reflected surroundings (sat {sp:.3f}, hue {hp * 360:.0f} is not the material color), "
                             f"median {np.round(med, 3).tolist()}, {len(px)} px"))
        else:
            dv = abs(vp - vt)
            dh = color.dhue(hp, ht) if sp >= A["pastel_hue_sat_min"] and st >= A["pastel_hue_sat_min"] else 0.0
            ok = dv <= A["value_delta_max"] and sp <= A["pastel_sat_max"] and dh <= A["hue_delta_max"]
            result.append(check("AM-15", f"color_{role}", float(dv), ok,
                             f"|dV| <= {A['value_delta_max']}, sat <= {A['pastel_sat_max']}, hue <= "
                             f"{A['hue_delta_max']} deg if sat >= {A['pastel_hue_sat_min']} (pastel/neutral)",
                             f"{hexa}: pixel sat {sp:.3f} (target {st:.3f}), hue difference {dh:.1f} deg "
                             f"({hp * 360:.0f} vs {ht * 360:.0f}), median {np.round(med, 3).tolist()}, {len(px)} px"))
    return result, swatch


SW_TARGET = Vector((0.205, 0.04, 0.078))  # lateral swoosh center (m)
HOLO_ANGLE = (0.0, 50.0)  # deg azimuth from the swoosh normal (+Y) toward the heel; elevation 10 deg


def render_holo(folder, prefix="holo"):
    """AM-16: lateral swoosh macro from 2 camera angles, neutral lighting (exposure 0)."""
    sc = bpy.context.scene
    use_studio("review")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", 0.0
    denoise, sc.cycles.use_denoising = sc.cycles.use_denoising, True
    out = []
    for az in HOLO_ANGLE:
        a, el = math.radians(az), math.radians(10.0)
        hit_loc = SW_TARGET + Vector((math.sin(a) * math.cos(el), math.cos(a) * math.cos(el), math.sin(el))) * 0.24
        cam = camera(f"CAM_holo_{int(az)}", tuple(hit_loc), (0, 0, 0), lens=60)
        look_at_target(cam, SW_TARGET)
        out.append((render_image(cam, os.path.join(folder, f"{prefix}_{int(az)}.png"), 480, 320, 32, False), cam))
    sc.cycles.use_denoising = denoise
    return out


def qc_holo(views):
    """AM-16: iridescent swoosh = mean hue of the swoosh pixels changes between camera angles. Lateral swoosh pixels
    (any |n.v|, not edges), saturation-weighted circular hue per angle; value = largest hue difference between angles."""
    hue, n = [], []
    for path, cam in views:
        px = role_pixels(path, cam, 1, 0.0, {"swoosh_lateral"}).get("swoosh", np.zeros((0, 3)))
        hh, k = mean_hue(px) if len(px) else (float("nan"), 0)
        hue.append(hh)
        n.append(k)
    a = THRESHOLD["holo_hue_min"]
    if any(math.isnan(x) for x in hue):
        return check("AM-16", "holo_hue_delta_deg", 0.0, False, f">= {a} deg", f"too few swoosh pixels: {n}"), hue
    d = max(color.dhue(x, y) for i, x in enumerate(hue) for y in hue[i + 1:])
    return check("AM-16", "holo_hue_delta_deg", float(d), d >= a, f">= {a} deg",
               "hue " + " / ".join(f"az {s:.0f}: {x * 360:.0f} deg ({k} px)" for s, x, k in zip(HOLO_ANGLE, hue, n))), hue


def qc_capsule_transmission(folder):
    """AM-17: translucent pink capsule. A small emissive probe (3 mm cube) in the capsule cavity (between dividers), the
    window macro rendered twice (probe hidden / shown, same seed): mean luma rise of the capsule pixels.
    An opaque capsule hides the probe completely (difference ~0). Also: the QC-11 hollow check must pass."""
    sc = bpy.context.scene
    capsule_ob = bpy.data.objects.get("air_capsule")
    a = THRESHOLD["capsule_transmission_min"]
    if capsule_ob is None:
        return check("AM-17", "capsule_transmission_luma", 0.0, False, f">= {a}", "capsule missing"), None
    use_studio("review")
    sc.view_settings.view_transform, sc.view_settings.exposure = "Khronos PBR Neutral", 0.0
    jx0, jx1, jz0, jz1 = data.data_window_bbox()
    divider = sorted(capsule_ob.get("divider_x_mm", []))
    limit = [jx0 - CAPSULE_MARGIN[0]] + list(divider) + [jx1 + CAPSULE_MARGIN[0]]
    i = int(np.argmax(np.diff(limit)))  # widest gap between dividers
    xc = (limit[i] + limit[i + 1]) / 2
    cy, _ = data.plan_y(xc)
    zc = (jz0 + jz1) / 2
    pr = mesh_obj("_probe", [(mm(xc + dx), mm(cy + dy), mm(zc + dz)) for dx in (-1.5, 1.5) for dy in (-1.5, 1.5)
                            for dz in (-1.5, 1.5)],
                 [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)], validation=False)
    em = bpy.data.materials.new("_emission_probe")
    b = bsdf(em)
    b.inputs["Emission Color"].default_value, b.inputs["Emission Strength"].default_value = (1, 1, 1, 1), 40.0
    pr.data.materials.append(em)
    jx, jz = (v / 1000 for v in data.model("viewpoints", "window_xz_mm", [216.3, 19.0]))
    cam = camera("CAM_macro", (jx - 0.0113, 0.17, jz + 0.026), (0, 0, 0), lens=60)
    look_at_target(cam, Vector((jx, 0.045, jz)))
    denoise, sc.cycles.use_denoising = sc.cycles.use_denoising, False
    L = []
    for show in (False, True):
        pr.hide_render = not show
        p = render_image(cam, os.path.join(folder, f"capsule_probe_{int(show)}.png"), 320, 210, 32, False)
        L.append(read_png(p) @ np.array([0.2126, 0.7152, 0.0722], "f"))
    pr.hide_render = True
    sc.cycles.use_denoising = denoise
    # capsule pixels: first ray hit is the capsule (the probe is removed first so ray_cast cannot see it)
    bpy.data.objects.remove(pr)
    bpy.data.materials.remove(em)
    px = []
    dg = bpy.context.evaluated_depsgraph_get()
    for x, y, o, d in ray(cam, 320, 210, 1):
        ok, _, _, _, ob, _ = sc.ray_cast(dg, o, d)
        if ok and ob is not None and ob.name == "air_capsule":
            px.append((y, x))
    if len(px) < 30:
        return check("AM-17", "capsule_transmission_luma", 0.0, False, f">= {a}", f"capsule pixels {len(px)}"), p
    ii, jj = np.array(px).T
    dL = float((L[1][ii, jj] - L[0][ii, jj]).mean())
    glass = qc_glass()
    cavity = bool(glass) and all(c["passed"] for c in glass)
    return check("AM-17", "capsule_transmission_luma", dL, dL >= a and cavity, f">= {a} and QC-11 hollow passed",
               f"{len(px)} px capsule, 3 mm probe at x {xc:.1f} mm; QC-11 " + ("passed" if cavity else "FAIL/missing")), p


def qc_slot_material():
    """AM-18: every product object has non-default role materials: no empty slots, every material named after a
    role, tagged with that role's P3 hex (material_am1), and not the default grey BSDF (Base Color 0.8 without links)."""
    wrong = []
    n = 0
    for ob in product_object():
        if not ob.data.materials:
            wrong.append(f"{ob.name}: no slots")
        for i, m in enumerate(ob.data.materials):
            n += 1
            if m is None:
                wrong.append(f"{ob.name}[{i}]: slot empty")
                continue
            if m.name not in P3() or m.get("hex_p3") != P3()[m.name][0]:
                wrong.append(f"{ob.name}[{i}]: {m.name} without P3 hex")
                continue
            b = next((x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED"), None) if m.node_tree else None
            bc = b.inputs["Base Color"] if b else None
            if bc is None or (not bc.links and all(abs(c - 0.8) < 1e-3 for c in bc.default_value[:3])):
                wrong.append(f"{ob.name}[{i}]: {m.name} default grey")
    return check("AM-18", "slot_material_non_default", len(wrong), not wrong, "= 0 wrong slots",
               f"{n} slots on {len(product_object())} objects; " + ("; ".join(wrong[:5]) if wrong else "all materials are P3 roles"))
