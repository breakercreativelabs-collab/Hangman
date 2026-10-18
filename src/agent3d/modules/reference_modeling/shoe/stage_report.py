"""Staged QC of the shoe recipe (Task 11 via project am90): stage M1 (bottom) or M2 (bottom + upper panels), neutral
materials, without building the next stage.

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- reference_modeling qc --project <id> --stage m1|m2
      [--without_negatives 1]   (fast QC per job; negative tests only when QC code changes)
Output: <out>/qc_<project>_<stage>.json + contact_sheet_<stage>.jpg; .blend + renders in the artifact folder.
M1: AM-01..08 + QC-11 (upper block). M2: + AM-09 smoothness, AM-10 IoU of each data panel per side (qc_panel), AM-12 laces,
AM-13 layers (data panels), AM-14 roles. Projects without data panels (am1) use the full report (`--stage all_items`).
"""
import os
import time

import bpy

from ....core import io, sheets
from ....core.qc import caught
from ....core.render import setup_render
from . import data
from .report import BUILD_STAGE, M1_ID, NEGATIVE, run_qc
from .panel_data import data_layers
from .qc_material import qc_capsule_transmission, qc_slot_material, qc_role_color, render_neutral
from .qc_panel import qc_panel_iou
from .qc_upper import qc_smooth, qc_layers, qc_material, qc_lace
from .sole import build_shoe
from .viewpoints import heel_overlay, render_views, swatch_png
from ..qc_silhouette import mask_overlay

VIEWPOINTS = {"m1": ["side_lateral", "side_medial", "three_quarter", "three_quarter_back", "top", "macro_window"],
          "m2": ["side_lateral", "side_medial", "three_quarter", "three_quarter_back", "top", "macro_window",
                 "macro_lace"]}
VIEWPOINTS["m3"] = VIEWPOINTS["m2"]
KEY_M2_M3 = {"upper", "param_material", "swap_role", "empty_slot", "default_material", "missing_role"}
NEGATIVE_M2 = [  # generic data panels: name, build parameters, QC that MUST fail
    ("wavy M1 upper block (C-A3)", dict(upper="block"), {"AM-09"}),
    ("M2 upper from raw data (C-A3)", dict(upper="m2_raw"), {"AM-09"}),
    ("swoosh panel shifted 5 mm", dict(panel_param=dict(shift={"swoosh": (5.0, 0.0)})),
     {"AM-10:iou_swoosh_lateral", "AM-10:iou_swoosh_medial"}),
    ("medial panel from lateral data", dict(panel_param=dict(medial_from_lateral=True)), {"AM-10:iou_swoosh_medial"}),
    ("lace down 3 mm", dict(lace_drop_mm=3.0), {"AM-12:lace_distance_min_mm"}),
    ("4 hole pairs", dict(n_pairs=4), {"AM-12:normal_lace_holes"}),
    ("holes shifted 5 mm", dict(hole_shift_mm=5.0), {"AM-12:normal_lace_holes"}),
    ("coincident layers (no offset)", dict(layer_gap=False), {"AM-13"}),
    ("lace material without role name", dict(missing_role="lace"), {"AM-14"}),
]
NEGATIVE_M3 = [  # colorway materials (generic): swapped roles, wrong color, opaque capsule, empty slot, default grey
    ("swapped roles mudguard/overlay", dict(swap_role=("mudguard", "overlay")),
     {"AM-15:color_mudguard", "AM-15:color_overlay"}),
    ("color swoosh wrong (#D02F6B)", dict(param_material=dict(wrong_hex={"swoosh": "#D02F6B"})), {"AM-15:color_swoosh"}),
    ("capsule opaque", dict(param_material=dict(capsule_mode="opaque")), {"AM-17"}),
    ("empty swoosh slot", dict(empty_slot="swoosh"), {"AM-18"}),
    ("accent default grey (correct role name)", dict(default_material="accent"), {"AM-18"}),
]


def stage_negatives(stage):
    m1 = [n for n in NEGATIVE if set(w.split(":")[0] for w in n[2]) <= M1_ID and not KEY_M2_M3 & set(n[1])]
    return m1 + (NEGATIVE_M2 if stage in ("m2", "m3") else []) + (NEGATIVE_M3 if stage == "m3" else [])


def qc_stage(folder, stage):
    result, art = run_qc(folder, "m1")
    if stage in ("m2", "m3"):
        c9, art["smoothness"] = qc_smooth()
        result.append(c9)
        c10, art["panel"] = qc_panel_iou()
        result += c10
        result += qc_lace()
        result.append(qc_layers(data_layers()))
        result.append(qc_material())
    if stage == "m3":
        art["neutral"] = render_neutral(folder)
        c15, art["swatch"] = qc_role_color(art["neutral"])
        result += c15
        c17, art["capsule_probe"] = qc_capsule_transmission(folder)
        result.append(c17)
        result.append(qc_slot_material())
    return result, art


def stage_main(options):
    project, stage = options["project"], options["stage"]
    data.load_data(project)
    out = os.path.abspath(options["out"] or data.output_path("result"))  # C-10
    folder_r = os.path.abspath(options["artifact"] or data.output_path("render"))
    blend = os.path.join(os.path.dirname(data.output_path("blend")) if not options["artifact"] else folder_r,
                         f"{project}_{stage}.blend")
    os.makedirs(folder_r, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    base = BUILD_STAGE.get(stage, dict(palette="neutral") if stage == "m2" else {})
    t0 = time.time()
    obs = build_shoe(**base)
    # AM90-C15: read values from the objects NOW; negative tests rebuild the scene, which deletes the old objects
    info_model = dict(model=obs.get("info_upper", {}), capsule_divider_x_mm=list(obs["capsule"].get("divider_x_mm", [])))
    t_build = time.time() - t0
    device = setup_render("test")
    bpy.context.scene.cycles.use_denoising = False
    main_checks, art = qc_stage(folder_r, stage)
    t_qc = time.time() - t0
    for c in main_checks:
        print(("PASS " if c["passed"] else "FAIL ") + f"{c['id']} {c['name']} = {c['value']} ({c['threshold']}) {c['context']}")
    ovl = {k: mask_overlay(*art[k], os.path.join(folder_r, f"overlay_{k}.png")) for k in ("side_view", "bottom", "medial")}
    ovl["heel"] = heel_overlay(art, os.path.join(folder_r, "heel_overlay.png"))
    for k, (m, d) in art.get("panel", {}).items():
        ovl[k] = mask_overlay(m[::-1], d[::-1], os.path.join(folder_r, f"overlay_panel_{k}.png"))
    viewpoints = render_views(folder_r, set(VIEWPOINTS[stage]))
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    negative = []
    select = [n for n in stage_negatives(stage)  # --negative "a|b": only negatives whose name contains one of the texts
             if not options["negative"] or any(t in n[0] for t in options["negative"].split("|"))]
    if options["without_negatives"] != "1":
        for name, param, required in select:
            build_shoe(**{**base, **param})
            setup_render("test")
            bpy.context.scene.cycles.use_denoising = False
            slug = "".join(ch if ch.isalnum() else "_" for ch in name)
            result, art_n = qc_stage(os.path.join(folder_r, f"negative_{stage}", slug), stage)
            ok, failed = caught(result, required)
            negative.append(dict(name=name, parameter={k: str(v) for k, v in param.items()}, required_failed=sorted(required),
                                failed=failed, caught=ok, value={f"{c['id']} {c['name']}": c["value"] for c in result},
                                _render=art_n["bottom_render"]))
            print(("CAUGHT " if ok else "MISSED(!) ") + f"negative '{name}': failed {failed}")

    by = {c["id"]: c for c in main_checks}
    value_of = lambda name: next((c["value"] for c in main_checks if c["name"] == name), None)
    all_items = lambda i: all(c["passed"] for c in main_checks if c["id"] == i)
    lab = lambda c: f"{c['id']} {c['value']}"
    upper_lbl = "UPPER = COARSE BLOCK" if stage == "m1" else "UPPER DATA PANELS, NEUTRAL MATERIALS"
    row = [
        (f"VIEWS {stage.upper()} (CYCLES TEST, EXPOSURE -1; {upper_lbl})", [
            (viewpoints["side_lateral"], "side_view lateral", True), (viewpoints["side_medial"], "side_view medial", True),
            (viewpoints["three_quarter"], "3/4 front", True), (viewpoints["three_quarter_back"], "3/4 back", True)]),
        ("MACRO + TOP + BOTTOM", [
            (viewpoints["macro_window"], f"macro window AM-08 notch {value_of('midsole_wall_notch_mm')} mm",
             all_items("AM-04") and all_items("AM-08")),
            (viewpoints["top"], "top" + (f" AM-12 lace {value_of('lace_distance_min_mm')} mm" if stage == "m2" else ""),
             stage == "m1" or all_items("AM-12"))]
         + ([(viewpoints["macro_lace"], f"macro lace AM-13 layer {value_of('layer_distance_min_mm')} mm", all_items("AM-13"))]
            if stage == "m2" else [])
         + [(art["bottom_render"], f"bottom AM-07 banding {value_of('bottom_column_banding')} tread {value_of('bottom_tread_contrast')}",
             all_items("AM-07"))]),
        ("OVERLAY M1: GREY = BOTH, BLUE = MODEL ONLY, RED = DATA ONLY / DATA CONTOUR",
         [(ovl["side_view"], "silhouette side_view " + lab(by["AM-01"]), all_items("AM-01")),
          (ovl["medial"], "silhouette MEDIAL " + lab(by["AM-06"]), all_items("AM-06")),
          (ovl["bottom"], "plan bottom " + lab(by["AM-02"]), all_items("AM-02")),
          (ovl["heel"], "midsole red " + lab(by["AM-03"]) + " window yellow", all_items("AM-03") and all_items("AM-04"))]),
    ]
    if stage == "m3":
        c15 = {c["name"][6:]: c for c in main_checks if c["id"] == "AM-15"}
        sw = swatch_png(folder_r, art["swatch"])
        row.insert(0, ("NEUTRAL RENDER M3 (COLOR QC AM-15, EXPOSURE 0) + CAPSULE MACRO AM-17", [
            (art["neutral"][0][0], "neutral lateral", all_items("AM-15")), (art["neutral"][2][0], "neutral 3/4", all_items("AM-15")),
            (art["neutral"][3][0], "neutral 3/4 back", all_items("AM-15")),
            (art["capsule_probe"], f"capsule AM-17 transmission {value_of('capsule_transmission_luma')}", all_items("AM-17"))]))
        per = list(sw)
        for i in range(0, len(per), 6):
            row.insert(1 + i // 6, ("ROLE SWATCHES: LEFT = PHOTO HEX, RIGHT = NEUTRAL RENDER MEDIAN (AM-15)" if i == 0 else "",
                                      [(sw[k], f"{k} {c15[k]['value']}", c15[k]["passed"]) for k in per[i:i + 6] if k in c15]))
    if stage in ("m2", "m3"):
        c10 = {c["name"][4:]: c for c in main_checks if c["id"] == "AM-10"}
        for side in ("lateral", "medial"):
            row.append((f"OVERLAY PANEL {side.upper()} (AM-10, Y PROJECTION; AM-09 RIPPLE {value_of('upper_normal_ripple_deg')} DEG)",
                          [(ovl[k], f"{k} {c10[k]['value']}", c10[k]["passed"]) for k in c10 if k.endswith(side) and k in ovl]))
    neg_r = [(n["_render"], f"NEGATIVE {n['name']}: failed " + " ".join(n["failed"]), False) for n in negative
             if n["name"].startswith(("tread wave", "base sole"))]
    if neg_r:
        row.append(("NEGATIVE TESTS (MUST BE RED)", neg_r))
    passed = all(c["passed"] for c in main_checks)
    neg_ok = all(n["caught"] for n in negative)
    status = f"QC {stage.upper()} {'PASS' if passed else 'FAIL'} - NEGATIVE {sum(n['caught'] for n in negative)}/{len(negative)}"
    sheet, _ = sheets.make(row, os.path.join(out, f"contact_sheet_{stage}.jpg"),
                           f"{data.CONFIG['project']['sheet_title']} {stage.upper()} - " + status)
    for n in negative:
        n.pop("_render", None)
    report = dict(project=data.CONFIG["project"]["report"], stage=stage, data=data.data_source(),
                   blender=bpy.app.version_string, device=device, build_time_s=round(t_build, 1),
                   qc_time_s=round(t_qc, 1), total_time_s=round(time.time() - t0, 1), passed=passed,
                   failed=[c["id"] + " " + c["name"] for c in main_checks if not c["passed"]], check=main_checks,
                   negative_tests=negative, negative_tests_all_caught=neg_ok, **info_model,
                   file=dict(contact_sheet=os.path.relpath(sheet, out), blend=os.path.relpath(blend, out)))
    io.write_json(os.path.join(out, f"qc_{project}_{stage}.json"), report)
    print(f"QC {data.CONFIG['project']['sheet_title']} {stage.upper()}: {'PASS' if passed else 'FAIL'}; negative "
          f"{sum(n['caught'] for n in negative)}/{len(negative)}; {report['total_time_s']} s ({device})")
    return 0 if passed and neg_ok else 1
