"""QC TV-01..08, scene part (no render): shot duration + beat, product framing, subject in frame, camera jerk,
exploded view reassembles, title-safe text, no linear keyframes (+ AM-18 on the TVC scene via the reference_modeling
contract). Each check = one row of the project's QC_RULES.md (TV-xx)."""
import math

import bpy
import numpy as np
from mathutils import Vector

from ...core.camera import projection
from ...core.qc import check
from ...core.scene import fcurves, collection, product_object, product_points
from ..reference_modeling import api as model_api
from ..product_shot.api import THRESHOLD as PS_THRESHOLD
from . import config
from .config import macro, shot_at

THRESHOLD = {
    "duration_frames": 1,            # TV-01 |shot duration - plan| (frames)
    "beat_frames": 0.5,         # TV-01 cuts on the 120 BPM grid (12.5 frames) +- 0.5 frame
    "margin_min": PS_THRESHOLD["margin_min"],  # TV-02 = QC-03 (0.02): product not clipped
    "fill_min": 0.40,              # TV-02 frame fill (longest side of the projected bbox); see QC_RULES
    "fill_max": 0.95,
    "luma_min": PS_THRESHOLD["luma_min"],      # TV-03 = QC-05: black frame (0.08)
    "luma_max": PS_THRESHOLD["luma_max"],    # TV-03 = QC-05: white/empty frame (0.92) unless a listed flash
    "std_min": 0.02,              # TV-03 flat (empty) frame: luma std; see QC_RULES
    "subject_min": 0.02,           # TV-03 subject bbox area (product/text/bubble) in frame, fraction of frame
    "flash_spike": 0.15,         # TV-03 rise of mean luma vs the median of +-3 frames = flash
    "jerk_pos": 0.0025,           # TV-04 |3rd difference of camera position| / distance to target, per frame^3; see QC_RULES
    "angle_jerk_deg": 0.15,       # TV-04 |3rd difference of view direction| (deg per frame^3); see QC_RULES
    "assembly_mm": 0.1,              # TV-05 max part displacement vs assembly, frames >= end of assembly
    "safe": 0.05,                 # TV-06 title-safe 90 %: every text vertex within [0.05, 0.95]
    "contrast_min": 4.5,           # TV-06 WCAG text vs background (render after the compositor)
    "linear_max": 0,             # TV-08 LINEAR keyframe segments that change value
}


def f_assemble():
    """First frame at which every exploded part is assembled (216 for AM1)."""
    X = config.K["exploded"]
    return max(X["assemble"] + b["defer"] // 2 for b in X["part"]) + 1


# ---------------- per-frame gathering (single pass) ----------------
def _angle(cam):
    return np.array(cam.matrix_world.to_3x3() @ Vector((0, 0, -1)))


def _world_bbox(ob):
    M = np.array(ob.matrix_world)
    b = np.array([tuple(c) for c in ob.bound_box])
    return b @ M[:3, :3].T + M[:3, 3]


def _subject_area(cam, obs):
    """Area of the projected bbox (clipped to the frame) of all visible subjects, as a fraction of the frame. Points
    behind the camera are dropped."""
    pts = [_world_bbox(o) for o in obs if not o.hide_render and max(o.scale) > 1e-3]
    if not pts:
        return 0.0
    u, v, z = projection(cam, np.concatenate(pts))
    ok = z > 0
    if not ok.any():
        return 0.0
    u, v = np.clip(u[ok], 0, 1), np.clip(v[ok], 0, 1)
    return float((u.max() - u.min()) * (v.max() - v.min()))


def _text_vertices(ob, dg):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.empty(len(me.vertices) * 3, "f")
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    M = np.array(ev.matrix_world)
    return co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]


def gather():
    """One pass over all frames: active camera (marker), camera matrix, distance to the rig target, subject area, text,
    TURNTABLE scale, part displacement vs assembly."""
    sc = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    tt, root = bpy.data.objects["TURNTABLE"], bpy.data.objects["PRODUCT_ROOT"]
    product = product_object()
    subject = product + list(collection("TEXT").objects) + list(collection("GELEMBUNG").objects)
    text = list(collection("TEXT").objects)
    marker = sorted(sc.timeline_markers, key=lambda m: m.frame)
    d = dict(frame=[], cam=[], pos=[], direction=[], distance=[], subject=[], safe=[], scale=[], assemble=[])
    F_ASSEMBLE, XP_OUT = f_assemble(), config.K["exploded"]["exit_code"]
    for f in range(sc.frame_start, sc.frame_end + 1):
        sc.frame_set(f)
        m = [m for m in marker if m.frame <= f]
        cam = m[-1].camera if m else sc.camera
        d["frame"].append(f)
        d["cam"].append(cam.name if cam else "")
        d["pos"].append(np.array(cam.matrix_world.translation))
        d["direction"].append(_angle(cam))
        d["distance"].append((cam.matrix_world.translation - cam.parent.matrix_world.translation).length
                          if cam.parent else 1.0)
        d["subject"].append(_subject_area(cam, subject))
        d["scale"].append(tt.matrix_world.to_scale().x)
        show = [o for o in text if not o.hide_render and max(o.scale) > 1e-4]
        if show:
            u, v, z = projection(cam, np.concatenate([_text_vertices(o, dg) for o in show]))
            d["safe"].append(float(min(u.min(), v.min(), 1 - u.max(), 1 - v.max())) if (z > 0).all() else -1.0)
        else:
            d["safe"].append(None)
        if f >= F_ASSEMBLE or f <= XP_OUT:
            Ri = root.matrix_world.inverted()
            w = 0.0
            for ob in product:
                rel = np.array(Ri @ ob.matrix_world) - np.eye(4)
                b = np.c_[np.array([tuple(c) for c in ob.bound_box]), np.ones(8)]
                w = max(w, float(np.linalg.norm(b @ rel.T, axis=1).max()))
            d["assemble"].append(w * 1000)
        else:
            d["assemble"].append(None)
        d["active_cam_marker"] = d.get("active_cam_marker", True) and (sc.camera == cam)
    sc.frame_set(sc.frame_start)
    return d


# ---------------- checks ----------------
def qc_duration(ratio):
    """TV-01: each shot duration from markers = plan +- 1 frame; cuts on the beat grid; marker cameras correct."""
    sc = bpy.context.scene
    mk = sorted(sc.timeline_markers, key=lambda m: m.frame)
    limit = [m.frame for m in mk] + [sc.frame_end + 1]
    wrong, worst, beat_err = [], 0, 0.0
    for s in config.shot():
        name, a, b = s["id"], s["start"], s["done"]
        plan = round((b - a) * config.FPS)
        i = next((i for i, m in enumerate(mk) if m.name == name), None)
        if i is None:
            wrong.append(f"{name}: marker missing")
            continue
        dur = limit[i + 1] - limit[i]
        worst = max(worst, abs(dur - plan))
        g = (mk[i].frame - 1) / config.BEAT
        beat_err = max(beat_err, abs(mk[i].frame - 1 - round(g) * config.BEAT))
        if mk[i].camera is None or mk[i].camera.get("shot") != name:
            wrong.append(f"{name}: camera marker wrong")
    total = sc.frame_end - sc.frame_start + 1
    ok_total = total == round(config.DURATION * config.FPS) and sc.render.fps == config.FPS
    passed = not wrong and worst <= THRESHOLD["duration_frames"] and beat_err <= THRESHOLD["beat_frames"] and ok_total
    return [check("TV-01", f"duration_shot_delta_frame_{ratio}", worst, passed,
                f"<= {THRESHOLD['duration_frames']} frame; cuts on the beat +- {THRESHOLD['beat_frames']}; "
                f"total {round(config.DURATION * config.FPS)} @ {config.FPS} fps",
                f"{len(mk)} markers, cuts {[m.frame for m in mk]}, max beat error {beat_err:.2f} frame, total {total} "
                f"@ {sc.render.fps} fps" + ("; " + "; ".join(wrong) if wrong else ""))]


def qc_framing(ratio):
    """TV-02: non-macro shots, every 2 frames while the product is visible (TURNTABLE scale >= 0.9): not clipped
    (margin >= QC-03) and a reasonable frame fill."""
    sc = bpy.context.scene
    tt = bpy.data.objects["TURNTABLE"]
    margin, fill_lo, fill_hi, f_m, f_lo, f_hi, n = 1.0, 9.0, 0.0, None, None, None, 0
    for name, f0, f1 in config.shot_span():
        if macro(name):
            continue
        for f in range(f0, f1 + 1, 2):
            sc.frame_set(f)
            if tt.matrix_world.to_scale().x < 0.9:
                continue
            cam = next(m.camera for m in sorted(sc.timeline_markers, key=lambda m: -m.frame) if m.frame <= f)
            u, v, z = projection(cam, product_points()[::5])
            m = float(min(u.min(), v.min(), 1 - u.max(), 1 - v.max())) if (z > 0).all() else -1.0
            contents = float(max(u.max() - u.min(), v.max() - v.min()))
            n += 1
            if m < margin:
                margin, f_m = m, f
            if contents < fill_lo:
                fill_lo, f_lo = contents, f
            if contents > fill_hi:
                fill_hi, f_hi = contents, f
    sc.frame_set(sc.frame_start)
    A = THRESHOLD
    return [check("TV-02", f"edge_margin_min_{ratio}", margin, margin >= A["margin_min"], f">= {A['margin_min']} (QC-03)",
                f"{n} non-macro frames, worst frame {f_m} ({shot_at(f_m)})" + (" CLIPPED" if margin < 0 else "")),
            check("TV-02", f"frame_fill_{ratio}", [round(fill_lo, 3), round(fill_hi, 3)],
                A["fill_min"] <= fill_lo and fill_hi <= A["fill_max"], f"{A['fill_min']}..{A['fill_max']}",
                f"min frame {f_lo} ({shot_at(f_lo)}), max frame {f_hi} ({shot_at(f_hi)})")]


def qc_subject(d, ratio):
    """TV-03 (geometry): every frame has a subject (product / text / bubble) in frame, bbox area >= 2 %."""
    s = np.array(d["subject"])
    i = int(s.argmin())
    return check("TV-03", f"subject_min_{ratio}", float(s.min()), float(s.min()) >= THRESHOLD["subject_min"],
               f">= {THRESHOLD['subject_min']} of frame", f"smallest at frame {d['frame'][i]} ({shot_at(d['frame'][i])})")


def _jerk(d):
    """Camera jerk per 4-frame window within a single shot (windows that cross a cut are skipped)."""
    P, A, D, cam = np.array(d["pos"]), np.array(d["direction"]), np.array(d["distance"]), d["cam"]
    jp, ja, f_p, f_a = 0.0, 0.0, None, None
    n_cuts = 0
    for i in range(1, len(P) - 2):
        if len({cam[i - 1], cam[i], cam[i + 1], cam[i + 2]}) > 1:
            n_cuts += 1
            continue
        p = np.linalg.norm(P[i + 2] - 3 * P[i + 1] + 3 * P[i] - P[i - 1]) / max(D[i], 1e-6)
        a = math.degrees(np.linalg.norm(A[i + 2] - 3 * A[i + 1] + 3 * A[i] - A[i - 1]))
        if p > jp:
            jp, f_p = p, d["frame"][i]
        if a > ja:
            ja, f_a = a, d["frame"][i]
    return jp, ja, f_p, f_a, n_cuts


def qc_motion(d, ratio):
    """TV-04: smooth camera motion. 3rd difference of position (relative to distance to target) and of view direction per
    frame, within a shot. Jumps are allowed only at cuts (windows crossing a cut are not counted)."""
    jp, ja, f_p, f_a, n = _jerk(d)
    A = THRESHOLD
    return [check("TV-04", f"jerk_posisi_relatif_{ratio}", jp, jp <= A["jerk_pos"], f"<= {A['jerk_pos']} /frame^3",
                f"max at frame {f_p} ({shot_at(f_p)}); {n} windows crossing a cut skipped"),
            check("TV-04", f"jerk_direction_deg_{ratio}", ja, ja <= A["angle_jerk_deg"], f"<= {A['angle_jerk_deg']} deg/frame^3",
                f"max at frame {f_a} ({shot_at(f_a)})")]


def qc_assembly(d, ratio):
    """TV-05: after the exploded view (frames >= end of assembly) and before it explodes, every part is in its assembled
    position: max displacement of entity bbox corners (PRODUCT_ROOT space) vs the model assembly."""
    r = [(f, w) for f, w in zip(d["frame"], d["assemble"]) if w is not None]
    f_b, w_b = max(r, key=lambda x: x[1])
    shot_x = config.K["exploded"]["shot"]
    f_end = config.f_shot(shot_x)[1]
    end = next(w for f, w in r if f == f_end)
    return check("TV-05", f"assemble_back_mm_{ratio}", w_b, w_b <= THRESHOLD["assembly_mm"], f"<= {THRESHOLD['assembly_mm']} mm",
               f"frames 1-{config.K['exploded']['exit_code']} and {f_assemble()}-{config.END_FRAME} ({len(r)} frames); "
               f"end {shot_x.split('_')[0]} ({f_end}) {end:.4f} mm; "
               f"worst frame {f_b}")


def qc_safe(d, ratio):
    """TV-06 (a): every visible text vertex is inside the 90 % title-safe area on every frame (including kinetic overshoot)."""
    s = [(f, v) for f, v in zip(d["frame"], d["safe"]) if v is not None]
    if not s:
        return check("TV-06", f"title_safe_margin_{ratio}", -1.0, False, f">= {THRESHOLD['safe']}", "text not found")
    f_b, v_b = min(s, key=lambda x: x[1])
    return check("TV-06", f"title_safe_margin_{ratio}", v_b, v_b >= THRESHOLD["safe"],
               f">= {THRESHOLD['safe']} (90 % title-safe)", f"{len(s)} frames with text; worst frame {f_b}")


def qc_easing():
    """TV-08: no LINEAR keyframe segment that changes value (objects + camera data + compositor)."""
    linear, n = [], 0
    ids = list(bpy.data.objects) + list(bpy.data.cameras) + list(bpy.data.node_groups)
    for idb in ids:
        for fc in fcurves(idb):
            if fc.data_path.startswith("hide_"):
                continue
            kp = fc.keyframe_points
            for a, b in zip(kp[:-1], kp[1:]):
                n += 1
                if a.interpolation == "LINEAR" and abs(a.co.y - b.co.y) > 1e-9:
                    linear.append(f"{idb.name}.{fc.data_path}[{fc.array_index}]@{int(a.co.x)}")
    return check("TV-08", "linear_segment", len(linear), len(linear) <= THRESHOLD["linear_max"], "= 0",
               f"{n} segments; " + (", ".join(linear[:4]) if linear else "BACK/BOUNCE/SINE/BEZIER/CONSTANT"))


def qc_scene_tv(ratio):
    d = gather()
    result = qc_duration(ratio) + qc_framing(ratio) + [qc_subject(d, ratio)] + qc_motion(d, ratio)
    result += [qc_assembly(d, ratio), qc_safe(d, ratio), qc_easing()]
    if not d["active_cam_marker"]:
        result.append(check("TV-01", f"camera_follow_marker_{ratio}", 0, False, "scene.camera = marker camera", "switch failed"))
    am18 = model_api.qc_slot_material()
    am18["name"] += f"_scene_tvc_{ratio}"
    return result + [am18], d

