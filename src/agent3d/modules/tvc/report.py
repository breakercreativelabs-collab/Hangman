"""TVC QC report (TV-01..08) + negative tests + storyboard.

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- tvc qc [--project am1] [--out <folder>]
      [--artifact <folder>] [--model <file.blend>] [--use_render 1] [--without_negatives 1] [--negative <text>]
Flow: 16:9 scene (geometry checks + storyboard/contrast render) -> 9:16 scene (geometry checks + contrast + test animatic
-> MP4) -> TV-03 (frames) + TV-07 (video file) -> negative tests -> storyboard.jpg + qc_tvc.json.
Small outputs (qc_tvc.json, storyboard.jpg) go to --out (default projects/<id>/result/tvc); render/ + the animatic MP4 to
--artifact (default output/<id>/tvc). Model: --model or the project .blend (made by `reference_modeling qc`).
--use_render 1: reuse existing animatic frames (development). Exit code 1 if any QC check fails or a negative test slips
through (--python-exit-code 1: a Python exception also exits 1; without it Blender exits 0).
"""
import os
import shutil
import time

import bpy

from ...core import io, sheets
from . import config
from .negative import entries, image_negatives, scene_negatives
from .production import build_tvc, encode_mp4, render_animation
from .qc_image import qc_frame, qc_contrast, qc_video, render_contrast, test_res, frame_stats
from .qc_scene import THRESHOLD, qc_scene_tv
from .config import shot_at
from ...core.render import render_frame


def storyboard(path, frames_916, sb_169, check_all, status):
    ok = lambda i: all(c["passed"] for c in check_all if c["id"] == i)
    row = []
    for title, fs in config.K["storyboard"]["9x16"]:
        cell = []
        for f in fs:
            lab = f"F{f} {(f - 1) / config.FPS:.2f}S"
            if f in config.FLASH:
                lab += " FLASH"
            cell.append((frames_916[f - 1], lab, ok("TV-03")))
        row.append((title + " 9:16", cell))
    row.append(("16:9 (MID OF EACH SHOT)", [(p, f"F{f} {shot_at(f)}", ok("TV-02") and ok("TV-06")) for f, p in sb_169]))
    return sheets.make(row, path, config.K["tvc"]["storyboard_title"] + " - " + status, cell_height=300)[0]


def main(argv):
    options = io.options(argv, dict(project="am1", out="", artifact="", model="", use_render="0", without_negatives="0",
                              negative=""))
    config.load_tvc(options["project"])
    out = os.path.abspath(options["out"] or io.project(options["project"], "result", "tvc"))  # C-10
    art = os.path.abspath(options["artifact"] or io.artifact(options["project"], "tvc"))
    model = os.path.abspath(options["model"]) if options["model"] else None
    folder_r = os.path.join(art, "render")
    os.makedirs(folder_r, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    check_all = []

    # 16:9: geometry + storyboard + contrast
    build_tvc("16x9", "test", model)
    h, _ = qc_scene_tv("16x9")
    check_all += h
    sb_169 = [(f, render_frame(os.path.join(folder_r, "story_16x9", f"f_{f:04d}.png"), f))
              for f in config.K["storyboard"]["16x9"]]
    check_all.append(qc_contrast(*render_contrast(folder_r, "16x9"), "16x9"))

    # 9:16: geometry + contrast + animatic
    build_tvc("9x16", "test", model)
    h, d916 = qc_scene_tv("9x16")
    check_all += h
    check_all.append(qc_contrast(*render_contrast(folder_r, "9x16"), "9x16"))
    device = bpy.context.scene.get("device")
    folder_a = os.path.join(folder_r, "9x16_test")
    if options["use_render"] != "1" and os.path.isdir(folder_a):
        shutil.rmtree(folder_a)
    t1 = time.time()
    frames = render_animation(folder_a)
    t_render = time.time() - t1
    name = config.K["tvc"]["file_name"]
    mp4 = encode_mp4(folder_a, os.path.join(art, f"{name}_9x16_test.mp4"), *test_res("9x16"))
    stat = frame_stats(frames)
    flash = set(config.FLASH)
    check_all.append(qc_frame(stat, flash, "9x16"))
    check_all.append(qc_video(mp4, test_res("9x16"), "9x16"))
    for c in check_all:
        print(("PASS " if c["passed"] else "FAIL ") + f"{c['id']} {c['name']} = {c['value']} ({c['threshold']}) {c['context']}")

    negative = []
    if options["without_negatives"] != "1":
        negative = scene_negatives(entries(options["negative"]), model)
        if not options["negative"]:
            negative += image_negatives(folder_r, stat, flash, frames, model)

    passed = all(c["passed"] for c in check_all)
    neg_ok = all(n["caught"] for n in negative)
    status = f"QC {'PASS' if passed else 'FAIL'} - NEGATIVE {sum(n['caught'] for n in negative)}/{len(negative)}"
    sheet = storyboard(os.path.join(out, "storyboard.jpg"), frames, sb_169, check_all, status)
    report = dict(
        project=config.K["tvc"]["report_label"],
        blender=bpy.app.version_string, device=device, animatic_render_time_s=round(t_render, 1),
        total_time_s=round(time.time() - t0, 1), passed=passed,
        failed=[c["id"] + " " + c["name"] for c in check_all if not c["passed"]], threshold=THRESHOLD,
        shot=[dict(id=n, frame=[f0, f1], seconds=[(f0 - 1) / config.FPS, f1 / config.FPS])
              for n, f0, f1 in config.shot_span()],
        flash_frame=sorted(config.FLASH), tagline=config.K["text"]["tagline"], check=check_all, negative_tests=negative,
        negative_tests_all_caught=neg_ok,
        luma_per_frame=[round(float(x), 4) for x in stat[:, 0]],
        file=dict(storyboard=os.path.relpath(sheet, out), video=os.path.relpath(mp4, out)),
    )
    io.write_json(os.path.join(out, "qc_tvc.json"), report)
    print(f"QC TVC: {status}; {report['total_time_s']} s ({device})")
    return 0 if passed and neg_ok else 1
