"""QC report of the shoe recipe: all checks AM-01..18 + QC-11, negative tests (25), shape + material contact sheets, qc_am1.json.

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- reference_modeling qc [--project am1]
      [--out <folder>] [--artifact <folder>] [--without_negatives 1] [--negative <text>] [--stage m1|m2|m3|all_items]
Output: <out>/qc_am1.json + contact_sheet.jpg (shape M1+M2) + contact_sheet_m3.jpg (default projects/<id>/result);
model .blend (used by tvc) + render/ in the artifact folder (default from project.toml [output]).
--negative <text>: only negative tests whose name contains that text (development; the official report = all_items).
--stage m1|m2: staged QC (stage_report.py): m1 bottom part (AM-01..08 + QC-11, upper block), m2 + data upper panels
(AM-09/10/12/13/14), neutral materials; qc_<project>_<stage>.json + contact_sheet_<stage>.jpg. --without_negatives 1 = fast QC per job (negatives only when QC code changes).
Exit code 1 if any QC check fails OR any negative test is not caught.
"""
import os
import time

import bpy

from ....core import io, sheets
from ....core.qc import check, iou, caught
from ....core.render import setup_render
from ...product_shot.api import qc_glass
from . import data
from .threshold import THRESHOLD, PIX
from .qc_bottom import (mask, mask_data, side_map, qc_window, qc_midsole, qc_notch, qc_tread,
                       qc_size)
from .qc_material import qc_holo, qc_capsule_transmission, qc_slot_material, qc_role_color, render_holo, render_neutral
from .qc_upper import qc_smooth, qc_layers, qc_material, qc_mudguard, qc_swoosh, qc_lace
from .sole import build_shoe
from .studio import use_studio
from .viewpoints import overlay_mudguard, heel_overlay, render_p3, render_views, swatch_png
from ..qc_silhouette import mask_overlay


M1_ID = {"AM-01", "AM-02", "AM-03", "AM-04", "AM-05", "AM-06", "AM-07", "AM-08", "QC-11"}
BUILD_STAGE = {"m1": dict(upper="block", palette="neutral"), "all_items": {}}


def run_qc(folder, stage="all_items"):
    """All checks for the current scene (stage m1: bottom part only). Returns (checks, artifacts for overlays)."""
    os.makedirs(folder, exist_ok=True)
    result, art = [], {}
    for view, name, id_ in (("side_view", "iou_side_silhouette_lateral", "AM-01"), ("bottom", "iou_bottom_plan", "AM-02")):
        m, hs, vs = mask(view, folder)
        d = mask_data(view, hs, vs)
        value = iou(m, d)
        context = f"{m.sum()} px model, {d.sum()} px data, {PIX} mm/px"
        if view == "side_view":
            context += " (the same data is used to build: build consistency check, not independent evidence)"
        result.append(check(id_, name, value, value >= THRESHOLD["iou_min"], f">= {THRESHOLD['iou_min']}", context))
        art[view] = (m, d)
        if view == "side_view":
            dm = mask_data("side_medial", hs, vs)
            value, data_noise_floor = iou(m, dm), iou(d, dm)
            a = THRESHOLD["iou_medial_min"]
            result.append(check("AM-06", "iou_side_silhouette_medial", value, value >= a, f">= {a}",
                             f"medial data independent of the build; data noise floor (IoU lateral vs medial) {data_noise_floor:.4f}"))
            art["medial"] = (m, dm)
    c3, art["midsole"] = qc_midsole()
    result.append(c3)
    mapping, xs, zs = side_map(150.0, 296.0, 0.0, 60.0, 1)
    art["mapping"] = (mapping, xs, zs)
    result.append(qc_window(mapping, xs, zs, "lateral"))
    pm, xm, zm = side_map(170.0, 265.0, 0.0, 40.0, -1)
    result.append(qc_window(pm, xm, zm, "medial"))
    art["medial_map"] = (pm, xm, zm)
    result += qc_size()
    result.append(qc_notch())
    floor = use_studio("review")
    c7, art["bottom_render"] = qc_tread(folder, art["bottom"][0], floor)
    result += c7
    glass = qc_glass()  # product-shot QC-11: the clear capsule must be hollow
    result += glass or [check("QC-11", "hollow_glass_wall_ratio", 1.0, False, "clear object exists", "capsule not found")]
    if stage == "m1":
        return result, art
    # M2 upper
    c9, art["smoothness"] = qc_smooth()
    result.append(c9)
    c10, art["swoosh"] = qc_swoosh()
    result += c10
    c11, art["mudguard"] = qc_mudguard()
    result.append(c11)
    result += qc_lace()
    result.append(qc_layers())
    result.append(qc_material())
    # M3 material P3
    views = render_neutral(folder)
    c15, art["swatch"] = qc_role_color(views)
    result += c15
    art["neutral"] = views
    art["holo"] = render_holo(folder)
    c16, art["holo_hue"] = qc_holo(art["holo"])
    result.append(c16)
    c17, art["capsule_probe"] = qc_capsule_transmission(folder)
    result.append(c17)
    result.append(qc_slot_material())
    return result, art


# ---------------- negative tests ----------------
NEGATIVE = [  # name, build parameters, QC that MUST fail ("AM-xx" or "AM-xx:check_name")
    ("window shifted 5 mm", dict(window_shift_mm=5.0), {"AM-04"}),
    ("scale +3%", dict(scale=1.03), {"AM-05", "AM-06"}),
    ("midsole 3 mm too thick", dict(midsole_extra_mm=3.0), {"AM-03"}),
    ("no window", dict(without_window=True), {"AM-04"}),
    ("capsule solid", dict(solid_capsule=True), {"QC-11"}),
    ("base sole median-5 (v1, C-A2)", dict(base="median5"), {"AM-08"}),
    ("tread wave (v1, C-A1)", dict(tread="wave"), {"AM-07"}),
    ("no tread", dict(tread="plain"), {"AM-07"}),
    ("wavy M1 upper block (C-A3)", dict(upper="block"), {"AM-09"}),
    ("M2 upper from raw data (C-A3)", dict(upper="m2_raw"), {"AM-09"}),
    ("swoosh shifted 5 mm", dict(swoosh_shift_mm=5.0), {"AM-10:iou_swoosh_lateral", "AM-10:iou_swoosh_medial"}),
    ("medial swoosh from lateral data", dict(swoosh_medial_from_lateral=True), {"AM-10:iou_swoosh_medial"}),
    ("mudguard up 4 mm", dict(mudguard_shift_mm=4.0), {"AM-11"}),
    ("lace down 3 mm", dict(lace_drop_mm=3.0), {"AM-12:lace_distance_min_mm"}),
    ("4 hole pairs", dict(n_pairs=4), {"AM-12:normal_lace_holes"}),
    ("holes shifted 5 mm", dict(hole_shift_mm=5.0), {"AM-12:normal_lace_holes"}),
    ("coincident layers (no offset)", dict(layer_gap=False), {"AM-13"}),
    ("lace material without role name", dict(missing_role="lace"), {"AM-14"}),
    # M3 material P3
    ("swapped roles mudguard/upper_mesh", dict(swap_role=("mudguard", "upper_mesh")),
     {"AM-15:color_mudguard", "AM-15:color_upper_mesh"}),
    ("swapped roles lining/upper_mesh", dict(swap_role=("lining", "upper_mesh")),
     {"AM-15:color_lining", "AM-15:color_upper_mesh"}),
    ("color swoosh wrong (#D02F6B)", dict(param_material=dict(wrong_hex={"swoosh": "#D02F6B"})), {"AM-15:color_swoosh"}),
    ("swoosh diffuse plain", dict(param_material=dict(swoosh="plain")), {"AM-16"}),
    ("capsule opaque", dict(param_material=dict(capsule_mode="opaque")), {"AM-17"}),
    ("slot eyelet empty", dict(empty_slot="eyelet"), {"AM-18"}),
    ("chrome_accent default grey (correct role name)", dict(default_material="chrome_accent"), {"AM-18"}),
]
NEGATIVE_RENDER = {"wavy M1 upper block (C-A3)": "three_quarter", "M2 upper from raw data (C-A3)": "three_quarter",
                  "coincident layers (no offset)": "macro_swoosh"}
NEGATIVE_RENDER_M3 = {  # M3 negatives: renders taken from the QC artifacts (no extra renders)
    "swapped roles mudguard/upper_mesh": lambda a: a["neutral"][2][0],
    "swapped roles lining/upper_mesh": lambda a: a["neutral"][3][0],
    "color swoosh wrong (#D02F6B)": lambda a: a["holo"][0][0],
    "swoosh diffuse plain": lambda a: a["holo"][1][0],
    "capsule opaque": lambda a: a["capsule_probe"],
}


def main(argv):
    options = io.options(argv, dict(project="am1", out="", artifact="", without_negatives="0", negative="", stage="all_items"))
    stage = options["stage"]
    if stage in ("m1", "m2", "m3"):
        from .stage_report import stage_main
        return stage_main(options)
    data.load_data(options["project"])
    out = os.path.abspath(options["out"] or data.output_path("result"))  # C-10
    folder_r = os.path.abspath(options["artifact"] or data.output_path("render"))
    blend = data.output_path("blend") if not options["artifact"] else os.path.join(folder_r, os.path.basename(
        data.output_path("blend")))
    os.makedirs(folder_r, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()

    obs = build_shoe()
    t_build = time.time() - t0
    device = setup_render("test")
    sc = bpy.context.scene
    sc.cycles.use_denoising = False
    main_checks, art = run_qc(folder_r)
    t_qc = time.time() - t0
    for c in main_checks:
        print(("PASS " if c["passed"] else "FAIL ") + f"{c['id']} {c['name']} = {c['value']} ({c['threshold']}) {c['context']}")
    ovl = {
        "side_view": mask_overlay(*art["side_view"], os.path.join(folder_r, "overlay_side.png")),
        "bottom": mask_overlay(*art["bottom"], os.path.join(folder_r, "overlay_bottom.png")),
        "medial": mask_overlay(*art["medial"], os.path.join(folder_r, "overlay_medial.png")),
        "heel": heel_overlay(art, os.path.join(folder_r, "heel_overlay.png")),
        "swoosh_lateral": mask_overlay(*art["swoosh"]["lateral"], os.path.join(folder_r, "overlay_swoosh_lateral.png")),
        "swoosh_medial": mask_overlay(*art["swoosh"]["medial"], os.path.join(folder_r, "overlay_swoosh_medial.png")),
        "mudguard": overlay_mudguard(art["mudguard"], os.path.join(folder_r, "overlay_mudguard.png")),
    }
    viewpoints = render_views(folder_r)
    p3 = render_p3(folder_r)
    swatch = swatch_png(folder_r, art["swatch"])
    os.makedirs(os.path.dirname(blend), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    negative = []
    select = [n for n in NEGATIVE if not options["negative"] or options["negative"] in n[0]]
    if options["without_negatives"] != "1":
        for name, param, required in select:
            build_shoe(**param)
            setup_render("test")
            bpy.context.scene.cycles.use_denoising = False
            slug = "".join(ch if ch.isalnum() else "_" for ch in name)
            folder_n = os.path.join(folder_r, "negative", slug)
            result, art_n = run_qc(folder_n)
            ok, failed = caught(result, required)
            negative.append(dict(name=name, parameter=param, required_failed=sorted(required), failed=failed, caught=ok,
                                value={f"{c['id']} {c['name']}": c["value"] for c in result}))
            negative[-1]["_render"] = art_n["bottom_render"]
            if name in NEGATIVE_RENDER:
                negative[-1]["_render"] = render_views(folder_n, {NEGATIVE_RENDER[name]})[NEGATIVE_RENDER[name]]
            if name in NEGATIVE_RENDER_M3:
                negative[-1]["_render_m3"] = NEGATIVE_RENDER_M3[name](art_n)
            print(("CAUGHT " if ok else "MISSED(!) ") + f"negative '{name}': failed {failed}")

    def lab(c):
        return f"{c['id']} {c['value']}"
    by = {c["id"]: c for c in main_checks}
    value_of = lambda name: next(c["value"] for c in main_checks if c["name"] == name)
    all_items = lambda i: all(c["passed"] for c in main_checks if c["id"] == i)
    row = [
        ("VIEWS (CYCLES CPU TEST, EXPOSURE -1)", [
            (viewpoints["side_lateral"], "side_view lateral (right)", True),
            (viewpoints["side_medial"], "side_view medial (left)", True),
            (viewpoints["three_quarter"], "3/4 front", True),
            (viewpoints["three_quarter_back"], "3/4 back (collar, lining)", True),
            (viewpoints["top"], "top (tongue gap, laces)", True)]),
        ("MACRO + BOTTOM", [
            (viewpoints["macro_swoosh"], f"macro swoosh + stitching AM-13 layer {value_of('layer_distance_min_mm')} mm", all_items("AM-13")),
            (viewpoints["macro_lace"], f"macro lace AM-12 distance {value_of('lace_distance_min_mm')} mm", all_items("AM-12")),
            (viewpoints["macro_window"], f"macro window AM-08 notch {value_of('midsole_wall_notch_mm')} mm", all_items("AM-04") and all_items("AM-08")),
            (art["bottom_render"], f"bottom AM-07 banding {value_of('bottom_column_banding')} tread {value_of('bottom_tread_contrast')}", all_items("AM-07"))]),
        ("OVERLAY M1: GREY = BOTH, BLUE = MODEL ONLY, RED = DATA ONLY / DATA CONTOUR",
         [(ovl["side_view"], "silhouette side_view " + lab(by["AM-01"]), all_items("AM-01")),
          (ovl["medial"], "silhouette MEDIAL " + lab(by["AM-06"]), all_items("AM-06")),
          (ovl["bottom"], "plan bottom " + lab(by["AM-02"]), all_items("AM-02")),
          (ovl["heel"], "midsole red " + lab(by["AM-03"]) + " window yellow", all_items("AM-03") and all_items("AM-04"))]),
        ("OVERLAY M2: SWOOSH (SAME COLORS) + MUDGUARD (RED = DATA, CYAN = MODEL)",
         [(ovl["swoosh_lateral"], f"swoosh lateral AM-10 {value_of('iou_swoosh_lateral')}", value_of("iou_swoosh_lateral") >= THRESHOLD["iou_swoosh_min"]),
          (ovl["swoosh_medial"], f"swoosh medial AM-10 {value_of('iou_swoosh_medial')}", value_of("iou_swoosh_medial") >= THRESHOLD["iou_swoosh_min"]),
          (ovl["mudguard"], "top mudguard line " + lab(by["AM-11"]) + f" mm; AM-09 ripple {value_of('upper_normal_ripple_deg')} deg",
           all_items("AM-11") and all_items("AM-09"))]),
    ]
    neg_r = [(n["_render"], f"NEGATIVE {n['name']}: failed " + " ".join(n["failed"]), False) for n in negative
             if n["name"].startswith(("tread wave", "base sole")) or n["name"] in NEGATIVE_RENDER]
    if neg_r:
        row.append(("NEGATIVE TESTS (MUST BE RED)", neg_r))
    passed = all(c["passed"] for c in main_checks)
    neg_ok = all(n["caught"] for n in negative)
    status = f"QC {'PASS' if passed else 'FAIL'} - NEGATIVE {sum(n['caught'] for n in negative)}/{len(negative)}"
    sheet, _ = sheets.make(row, os.path.join(out, "contact_sheet.jpg"),
                           f"{data.CONFIG['project']['sheet_title']} M1+M2 SHAPE - " + status)

    # M3 contact sheet (P3 materials)
    c15 = {c["name"][6:]: c for c in main_checks if c["id"] == "AM-15"}
    hh = art["holo_hue"]
    palette = data.CONFIG["palette"]["name"].upper()
    row_m3 = [
        (f"STUDIO {palette} (EYE CHECK, EXPOSURE -0.5)", [
            (p3["p3_hero"], "hero 3/4", True),
            (p3["p3_lateral"], "side_view lateral (right)", True),
            (p3["p3_medial"], "side_view medial (left)", True)]),
        ("MACRO (AM-16 SWOOSH 2 ANGLES, NEUTRAL LIGHT) + CAPSULE + MESH/SUEDE", [
            (art["holo"][0][0], f"swoosh az 0: hue {hh[0] * 360:.0f} deg", all_items("AM-16")),
            (art["holo"][1][0], f"swoosh az 50: hue {hh[1] * 360:.0f} deg; AM-16 {value_of('holo_hue_delta_deg')} deg",
             all_items("AM-16")),
            (p3["p3_macro_capsule"], f"capsule AM-17 transmission {value_of('capsule_transmission_luma')}", all_items("AM-17")),
            (p3["p3_macro_mesh"], "mesh lavender + suede butter + stitching", True)]),
        ("ROLE SWATCHES: LEFT = P3 HEX, RIGHT = NEUTRAL RENDER MEDIAN (AM-15)",
         [(swatch[k], f"{k} {c15[k]['value']}", c15[k]["passed"]) for k in data.ROLE[:5] if k in swatch]),
        ("", [(swatch[k], f"{k} {c15[k]['value']}", c15[k]["passed"]) for k in data.ROLE[5:] if k in swatch]),
        ("NEUTRAL COLOR QC RENDER (EXPOSURE 0) + EYELET MACRO", [
            (art["neutral"][0][0], "neutral lateral", all_items("AM-15")),
            (art["neutral"][2][0], "neutral 3/4", all_items("AM-15")),
            (art["neutral"][5][0], f"chrome eyelet AM-18 wrong slots {value_of('slot_material_non_default')}", all_items("AM-18"))]),
    ]
    neg_m3 = [(n["_render_m3"], f"NEGATIVE {n['name']}: failed " + " ".join(n["failed"]), False) for n in negative
              if n.get("_render_m3")]
    if neg_m3:
        row_m3.append(("M3 NEGATIVE TESTS (MUST BE RED)", neg_m3))
    m3_ok = all(all_items(i) for i in ("AM-15", "AM-16", "AM-17", "AM-18"))
    sheet_m3, _ = sheets.make(row_m3, os.path.join(out, "contact_sheet_m3.jpg"),
                              f"{data.CONFIG['project']['sheet_title']} M3 MATERIAL {palette} - M3 {'PASS' if m3_ok else 'FAIL'} - " + status)
    for n in negative:
        n.pop("_render", None)
        n.pop("_render_m3", None)

    report = dict(
        project=data.CONFIG["project"]["report"], data=data.data_source(),
        blender=bpy.app.version_string, device=device, build_time_s=round(t_build, 1),
        qc_time_s=round(t_qc, 1), total_time_s=round(time.time() - t0, 1),
        passed=passed, failed=[c["id"] + " " + c["name"] for c in main_checks if not c["passed"]],
        threshold=THRESHOLD, check=main_checks, negative_tests=negative, negative_tests_all_caught=neg_ok,
        model=obs.get("info_upper", {}),
        swatch={k: dict(hex=v[0], median_render=[round(float(c), 3) for c in v[1]], pixel=v[2])
                for k, v in art["swatch"].items()},
        file=dict(contact_sheet=os.path.relpath(sheet, out), contact_sheet_m3=os.path.relpath(sheet_m3, out),
                  blend=os.path.relpath(blend, out)),
    )
    io.write_json(os.path.join(out, f"qc_{options['project']}.json"), report)
    print(f"QC {data.CONFIG['project']['sheet_title']}: {'PASS' if passed else 'FAIL'}; negative {sum(n['caught'] for n in negative)}/{len(negative)}; "
          f"{report['total_time_s']} s ({device})")
    return 0 if passed and neg_ok else 1
