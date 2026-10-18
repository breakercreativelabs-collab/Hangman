"""Synthetic curriculum (layer 1 of the feedback system): all test products x 3 light presets x color palette, test quality.

  blender -b --factory-startup -P blender_cli.py -- product_shot curriculum [--product a,b] [--out <folder>]
        [--artifact <folder>] [--quality test] [--palette red,...]
Per product: run.run_product (contact sheet + qc.json, used by the judge), then a palette sweep (every preset x
every color, ratio 1:1, hero frame): QC-05 + QC-10 per render (+ QC-12 once per preset), summarized in palette.jpg.
Writes <out>/report.json and <out>/REPORT.md. Exit code 1 if any QC failed or a product raised an error.
"""
import json
import os
import time
import traceback
from collections import defaultdict

import bpy

from ...core import io, sheets
from . import run, qc_image, specification
from .threshold import THRESHOLD
from .framing import ratio_camera, render_variants
from .light import LIGHT_PRESETS, studio_lighting
from .verbs import COLOR, material_variant


def curriculum_options(argv):
    o = io.options(argv, dict(product=",".join(specification.PRODUCT), out=io.project("sample_products", "result", "curriculum"),
                           artifact=io.artifact("product_shot", "curriculum"), quality="test", palette=",".join(COLOR)))
    o["out"] = os.path.abspath(o["out"])  # C-10
    o["artifact"] = os.path.abspath(o["artifact"])
    return o


def palette_sweep(name, folder, palette, folder_art=None):
    """Every light preset x every palette color: render 1:1 hero frame, QC-05 + QC-10."""
    cam = ratio_camera("1:1", 0.70)
    check, row = [], []
    for p in LIGHT_PRESETS:
        studio_lighting(p)
        contents = []
        for w in palette:
            material_variant(w)
            r = render_variants(os.path.join(folder_art or folder, "render"), f"{name}_palette_{p}_{w}", ["1:1"])[0]
            result = [qc_image.qc_histogram(r["file"], cam), qc_image.qc_color(r["file"], cam, r["color"])]
            if w == palette[0]:  # QC-12 once per preset: metal does not change with the color variant
                result.append(qc_image.qc_metal(r["file"], cam))
            for c in result:
                c["context"] = f"{os.path.basename(r['file'])}: {c['context']}"
            check += [c | dict(preset=p, color=w) for c in result]
            contents.append((r["file"], f"{w} {p}", all(c["passed"] for c in result)))
        row.append((f"PALETTE {p}", contents))
    studio_lighting("softbox")
    sheet, _ = sheets.make(row, os.path.join(folder, "palette.jpg"), f"{name} PALETTE x PRESET")
    return check, sheet


def recap(name, check):
    per_qc = defaultdict(lambda: [0, 0])
    for c in check:
        per_qc[c["id"]][0] += 1
        per_qc[c["id"]][1] += c["passed"]
    return {k: dict(check=n, passed=l, level=round(l / n, 4)) for k, (n, l) in sorted(per_qc.items())}


def write_md(rpt, path):
    ids = sorted({k for p in rpt["product"].values() for k in p.get("per_qc", {})})
    L = [f"# Synthetic curriculum report ({rpt['date']})", "",
         f"Blender {rpt['blender']} · device {rpt['device']} · quality `{rpt['quality']}` · "
         f"{len(rpt['product'])} products × {len(LIGHT_PRESETS)} presets × {len(rpt['palette'])} colors · "
         f"total {rpt['time_seconds']} s", "",
         f"**Result: {'PASS' if rpt['passed'] else 'FAIL'}**: {rpt['check_count']} checks, {rpt['failed_count']} failed.", "",
         "## Pass rate per QC per product", "",
         "| Product | " + " | ".join(ids) + " | Renders | Time (s) | Status |",
         "|---|" + "---|" * (len(ids) + 3)]
    for n, p in rpt["product"].items():
        if "error" in p:
            L.append(f"| {n} | " + " | ".join("-" for _ in ids) + " | - | - | ERROR |")
            continue
        cell = [f"{p['per_qc'][i]['passed']}/{p['per_qc'][i]['check']}" if i in p["per_qc"] else "-" for i in ids]
        L.append(f"| {n} | " + " | ".join(cell) + f" | {p['render_count']} | {p['time_seconds']} | "
                 f"{'PASS' if p['passed'] else 'FAIL'} |")
    L += ["", "## Failures", ""]
    failed = [(n, g) for n, p in rpt["product"].items() for g in p.get("failure", [])]
    L += [f"- **{n}** {g['id']} `{g['name']}` = {g['value']} (threshold {g['threshold']}): {g['context']}" for n, g in failed] \
        or ["None."]
    errs = [(n, p["error"]) for n, p in rpt["product"].items() if "error" in p]
    L += [f"- **{n}** ERROR: `{e.splitlines()[-1]}`" for n, e in errs]
    L += ["", "Files per product: `<product>/contact_sheet.jpg` (judge), `<product>/palette.jpg`, `<product>/qc.json`."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv):
    o = curriculum_options(argv)
    t0 = time.time()
    os.makedirs(o["out"], exist_ok=True)
    palette = o["palette"].split(",")
    rpt = dict(date=time.strftime("%Y-%m-%d"), blender=bpy.app.version_string, quality=o["quality"],
               palette=palette, preset=list(LIGHT_PRESETS), product={})
    oj = dict(quality=o["quality"], color="red,blue,green", out=o["out"], artifact=o["artifact"], unit="m", front="-Y", top="+Z",
              preset="softbox", duration="6", easing="ease_in_out", logo_u="", logo_z="")
    for name in o["product"].split(","):
        t1 = time.time()
        try:
            r = run.run_product(name, "sample:" + name, oj)
            rpt["device"] = r["device"]
            folder = os.path.join(o["out"], name)
            check_palette, _ = palette_sweep(name, folder, palette, os.path.join(o["artifact"], name))
            check = r["check"] + check_palette
            rpt["product"][name] = dict(
                name=specification.SPEC[name]["name"], dimension_mm=r["normalization"]["dimension_mm"],
                passed=all(c["passed"] for c in check), per_qc=recap(name, check), check_count=len(check),
                render_count=r["render_count"] + len(LIGHT_PRESETS) * len(palette),
                failure=[c for c in check if not c["passed"]], time_seconds=round(time.time() - t1, 1),
                palette=[dict(preset=c["preset"], color=c["color"], id=c["id"], passed=c["passed"],
                            value=c["value"]["mean_luma"] if c["id"] == "QC-05" else c["value"]) for c in check_palette],
                contact_sheet=f"{name}/contact_sheet.jpg", palette_png=f"{name}/palette.jpg")
        except Exception:
            rpt["product"][name] = dict(passed=False, error=traceback.format_exc(), time_seconds=round(time.time() - t1, 1))
            print(rpt["product"][name]["error"])
        print(f"CURRICULUM {name}: {'PASS' if rpt['product'][name]['passed'] else 'FAIL'} "
              f"({rpt['product'][name]['time_seconds']} s)")
    ps = rpt["product"].values()
    rpt.update(passed=all(p["passed"] for p in ps), check_count=sum(p.get("check_count", 0) for p in ps),
               failed_count=sum(len(p.get("failure", [])) + ("error" in p) for p in ps),
               time_seconds=round(time.time() - t0, 1), threshold=THRESHOLD)
    rpt.setdefault("device", "?")
    with open(os.path.join(o["out"], "report.json"), "w", encoding="utf-8") as f:
        json.dump(rpt, f, ensure_ascii=False, indent=1)
    write_md(rpt, os.path.join(o["out"], "REPORT.md"))
    print(f"CURRICULUM {'PASS' if rpt['passed'] else 'FAIL'}: {rpt['check_count']} checks, {rpt['failed_count']} failed, "
          f"{rpt['time_seconds']} s")
    return 0 if rpt["passed"] else 1

