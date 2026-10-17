"""Laporan QC TVC (TV-01..08) + uji negatif + storyboard.

  blender -b --factory-startup --python-exit-code 1 -P blender_cli.py -- tvc qc [--proyek am1] [--out <folder>]
      [--artefak <folder>] [--model <file.blend>] [--pakai_render 1] [--tanpa_negatif 1] [--negatif <teks>]
Alur: scene 16:9 (cek geometri + render storyboard/kontras) -> scene 9:16 (cek geometri + kontras + animatic uji
-> MP4) -> TV-03 (frame) + TV-07 (file video) -> uji negatif -> storyboard.jpg + qc_tvc.json.
Keluaran kecil (qc_tvc.json, storyboard.jpg) di --out (bawaan proyek/<id>/hasil/tvc); render/ + MP4 animatic di
--artefak (bawaan artefak/<id>/tvc). Model: --model atau .blend proyek (`modeling_referensi qc` membuatnya).
--pakai_render 1: pakai frame animatic yang sudah ada (pengembangan). Kode keluar 1 jika ada QC gagal atau negatif
lolos (--python-exit-code 1: exception Python juga keluar 1; tanpa itu Blender keluar 0).
"""
import os
import shutil
import time

import bpy

from ...inti import io, lembar
from . import konfig
from .negatif import daftar, negatif_gambar, negatif_scene
from .produksi import bangun_tvc, encode_mp4, render_animasi
from .qc_gambar import qc_frame, qc_kontras, qc_video, render_kontras, res_uji, statistik_frame
from .qc_scene import AMBANG, qc_scene_tv
from .konfig import shot_di
from ...inti.render import render_frame


def storyboard(path, frames_916, sb_169, cek_semua, status):
    ok = lambda i: all(c["lulus"] for c in cek_semua if c["id"] == i)
    baris = []
    for judul, fs in konfig.K["storyboard"]["9x16"]:
        sel = []
        for f in fs:
            lab = f"F{f} {(f - 1) / konfig.FPS:.2f}S"
            if f in konfig.FLASH:
                lab += " FLASH"
            sel.append((frames_916[f - 1], lab, ok("TV-03")))
        baris.append((judul + " 9:16", sel))
    baris.append(("16:9 (TENGAH TIAP SHOT)", [(p, f"F{f} {shot_di(f)}", ok("TV-02") and ok("TV-06")) for f, p in sb_169]))
    return lembar.buat(baris, path, konfig.K["tvc"]["judul_storyboard"] + " - " + status, tinggi_sel=300)[0]


def main(argv):
    opsi = io.opsi(argv, dict(proyek="am1", out="", artefak="", model="", pakai_render="0", tanpa_negatif="0",
                              negatif=""))
    konfig.muat_tvc(opsi["proyek"])
    out = os.path.abspath(opsi["out"] or io.proyek(opsi["proyek"], "hasil", "tvc"))  # C-10
    art = os.path.abspath(opsi["artefak"] or io.artefak(opsi["proyek"], "tvc"))
    model = os.path.abspath(opsi["model"]) if opsi["model"] else None
    folder_r = os.path.join(art, "render")
    os.makedirs(folder_r, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    cek_semua = []

    # 16:9: geometri + storyboard + kontras
    bangun_tvc("16x9", "uji", model)
    h, _ = qc_scene_tv("16x9")
    cek_semua += h
    sb_169 = [(f, render_frame(os.path.join(folder_r, "story_16x9", f"f_{f:04d}.png"), f))
              for f in konfig.K["storyboard"]["16x9"]]
    cek_semua.append(qc_kontras(*render_kontras(folder_r, "16x9"), "16x9"))

    # 9:16: geometri + kontras + animatic
    bangun_tvc("9x16", "uji", model)
    h, d916 = qc_scene_tv("9x16")
    cek_semua += h
    cek_semua.append(qc_kontras(*render_kontras(folder_r, "9x16"), "9x16"))
    perangkat = bpy.context.scene.get("perangkat")
    folder_a = os.path.join(folder_r, "9x16_uji")
    if opsi["pakai_render"] != "1" and os.path.isdir(folder_a):
        shutil.rmtree(folder_a)
    t1 = time.time()
    frames = render_animasi(folder_a)
    t_render = time.time() - t1
    nama = konfig.K["tvc"]["nama_berkas"]
    mp4 = encode_mp4(folder_a, os.path.join(art, f"{nama}_9x16_uji.mp4"), *res_uji("9x16"))
    stat = statistik_frame(frames)
    flash = set(konfig.FLASH)
    cek_semua.append(qc_frame(stat, flash, "9x16"))
    cek_semua.append(qc_video(mp4, res_uji("9x16"), "9x16"))
    for c in cek_semua:
        print(("LULUS " if c["lulus"] else "GAGAL ") + f"{c['id']} {c['nama']} = {c['nilai']} ({c['ambang']}) {c['konteks']}")

    negatif = []
    if opsi["tanpa_negatif"] != "1":
        negatif = negatif_scene(daftar(opsi["negatif"]), model)
        if not opsi["negatif"]:
            negatif += negatif_gambar(folder_r, stat, flash, frames, model)

    lulus = all(c["lulus"] for c in cek_semua)
    neg_ok = all(n["tertangkap"] for n in negatif)
    status = f"QC {'LULUS' if lulus else 'GAGAL'} - NEGATIF {sum(n['tertangkap'] for n in negatif)}/{len(negatif)}"
    sheet = storyboard(os.path.join(out, "storyboard.jpg"), frames, sb_169, cek_semua, status)
    laporan = dict(
        proyek=konfig.K["tvc"]["label_laporan"],
        blender=bpy.app.version_string, perangkat=perangkat, waktu_render_animatic_s=round(t_render, 1),
        waktu_total_s=round(time.time() - t0, 1), lulus=lulus,
        gagal=[c["id"] + " " + c["nama"] for c in cek_semua if not c["lulus"]], ambang=AMBANG,
        shot=[dict(id=n, frame=[f0, f1], detik=[(f0 - 1) / konfig.FPS, f1 / konfig.FPS])
              for n, f0, f1 in konfig.rentang_shot()],
        flash_frame=sorted(konfig.FLASH), tagline=konfig.K["teks"]["tagline"], cek=cek_semua, uji_negatif=negatif,
        uji_negatif_semua_tertangkap=neg_ok,
        luma_per_frame=[round(float(x), 4) for x in stat[:, 0]],
        file=dict(storyboard=os.path.relpath(sheet, out), video=os.path.relpath(mp4, out)),
    )
    io.tulis_json(os.path.join(out, "qc_tvc.json"), laporan)
    print(f"QC TVC: {status}; {laporan['waktu_total_s']} s ({perangkat})")
    return 0 if lulus and neg_ok else 1
