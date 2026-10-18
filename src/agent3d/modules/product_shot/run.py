"""Product shot pipeline: test product -> verbs -> variant renders -> numeric QC -> contact sheet + qc.json + .blend.

  blender -b --factory-startup -P blender_cli.py -- product_shot run [--product bottle,can] [--quality test|final]
        [--color red,blue,green] [--out <folder>] [--artifact <folder>] [--source <file>]
--source: client model (.glb/.obj/.fbx/.stl/.blend) replaces the test product; add --unit mm --front +X if needed,
          and --logo_u <u> --logo_z <m> (logo position) so QC-04 measures the logo, not just the declaration.
Small outputs (qc.json, contact_sheet.jpg) go to --out (default projects/sample_products/result/<product>); .blend + render/ go to
--artifact (default output/product_shot/<product>, ignored, reproducible). Exit code 1 if any QC failed.
"""
import json
import os
import time

import bpy

from ...core import io, sheets
from ...core.render import QUALITY, setup_render
from ...core.scene import STANDARD, root, prepare_scene
from . import qc_image, qc_scene
from .threshold import THRESHOLD
from .framing import ratio_camera, render_variants
from .light import LIGHT_PRESETS, studio_lighting
from .verbs import RATIO, import_product, material_variant, normalize, turntable


DEFAULTS = dict(product="bottle,can", quality="test", color="red,blue,green", out=io.project("sample_products", "result"),
              artifact=io.artifact("product_shot"), source="", unit="m", front="-Y", top="+Z", preset="softbox",
              duration="6", easing="ease_in_out", logo_u="", logo_z="")


def argument(argv):
    options = io.options(argv, DEFAULTS)
    options["out"] = os.path.abspath(options["out"])  # C-10: a relative path makes bpy silently fail to write images
    options["artifact"] = os.path.abspath(options["artifact"])
    if options["source"]:
        options["source"] = os.path.abspath(options["source"])
    return options


def label_render(r):
    return f"{r['ratio']} {r['color']} {r['preset']} F{r['frame']}"


def run_product(name, source, o):
    t0 = time.time()
    folder = os.path.join(o["out"], name)
    folder_art = os.path.join(o.get("artifact", o["out"]), name)
    folder_render = os.path.join(folder_art, "render")
    prepare_scene()
    device = setup_render(o["quality"])
    r0 = import_product(source)
    if o["logo_u"] and o["logo_z"]:  # logo position in the client label UV (u) and logo center height (m) -> strong QC-04
        r0["logo_u"], r0["logo_z"] = float(o["logo_u"]), float(o["logo_z"])
    norm = normalize(unit=o["unit"], front=o["front"], top=o["top"])
    studio_lighting(o["preset"])
    turntable(float(o["duration"]), o["easing"])
    camera = [ratio_camera(r, 0.70) for r in RATIO]
    check = qc_scene.qc_scene(camera)
    cell_ok = lambda r: all(r[k]["passed"] for k in ("qc", "qc_color", "qc_metal") if k in r)
    row, all_renders = [], []

    def render(prefix, ratio, frame=None):
        rs = render_variants(folder_render, prefix, ratio, frame)
        for r in rs:
            cam = bpy.data.objects[r["camera"]]
            r["qc"] = qc_image.qc_histogram(r["file"], cam)
            if r["frame"] == bpy.context.scene.frame_start:  # color is checked on the hero frame (label facing camera)
                r["qc_color"] = qc_image.qc_color(r["file"], cam, r["color"])
                r["qc_metal"] = qc_image.qc_metal(r["file"], cam)  # QC-12 (C-15)
        all_renders.extend(rs)
        return rs

    color = o["color"].split(",")
    for w in color:  # rows 1..n: color variants x 3 ratios
        material_variant(w)
        rs = render(f"{name}_{w}_{o['preset']}", list(RATIO))
        row.append((f"VARIANT {w}", [(r["file"], label_render(r), cell_ok(r)) for r in rs]))
    material_variant(color[0])
    contents = []
    for p in LIGHT_PRESETS:  # row: light presets, ratio 1:1
        if p == o["preset"]:
            continue
        studio_lighting(p)
        contents += [(r["file"], label_render(r), cell_ok(r)) for r in render(f"{name}_{color[0]}_{p}", ["1:1"])]
    studio_lighting(o["preset"])
    if contents:
        row.append(("LIGHT PRESET", contents))
    sc = bpy.context.scene
    contents = []
    for k in (0.25, 0.5, 0.75):  # row: turntable (angle follows easing)
        f = round(sc.frame_start + k * (sc.frame_end - sc.frame_start))
        sc.frame_set(f)
        angle = round(root().parent.rotation_euler.z * 57.29578)
        for r in render(f"{name}_{color[0]}_turntable", ["1:1"], f):
            contents.append((r["file"], f"F{f} {angle} DEG", cell_ok(r)))
    row.append(("TURNTABLE " + o["easing"], contents))
    sc.frame_set(sc.frame_start)
    for r in all_renders:
        for k in ("qc", "qc_color", "qc_metal"):
            if k in r:
                check.append(r[k] | {"context": f"{os.path.basename(r['file'])}: {r[k]['context']}"})
    passed = all(c["passed"] for c in check)
    failed = sorted({c["id"] for c in check if not c["passed"]})
    title = f"{name} {norm['dimension_mm'][2]:.1f} MM  QC {'PASS' if passed else 'FAIL ' + ' '.join(failed)}"
    sheet, size = sheets.make(row, os.path.join(folder, "contact_sheet.jpg"), title)
    report = dict(product=name, source=source, standard=STANDARD, blender=bpy.app.version_string,
                   device=device, quality=o["quality"], sample=sc.cycles.samples,
                   resolution={r: [round(x * QUALITY[o["quality"]]["scale"]) for x in v] for r, v in RATIO.items()},
                   normalization=norm, turntable=dict(duration_seconds=float(o["duration"]), easing=o["easing"],
                                                     frame=[sc.frame_start, sc.frame_end], fps=sc.render.fps),
                   passed=passed, failed=failed, check_count=len(check), render_count=len(all_renders),
                   contact_sheet=os.path.relpath(sheet, folder), contact_sheet_size=size,
                   threshold=THRESHOLD, check=check, time_seconds=round(time.time() - t0, 1))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "qc.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    os.makedirs(folder_art, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder_art, f"{name}.blend"), compress=True)
    print(f"RESULT {name}: QC {'PASS' if passed else 'FAIL ' + str(failed)} | {len(check)} checks | "
          f"{len(all_renders)} renders | {report['time_seconds']} s | {device}")
    return report


def main(argv):
    o = argument(argv)
    if o["source"]:
        entries = [(os.path.splitext(os.path.basename(o["source"]))[0], o["source"])]
    else:
        entries = [(p, "sample:" + p) for p in o["product"].split(",")]
    result = [run_product(n, s, o) for n, s in entries]
    return 0 if all(h["passed"] for h in result) else 1
