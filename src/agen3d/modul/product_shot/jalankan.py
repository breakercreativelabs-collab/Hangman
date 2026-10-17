"""Pipeline product shot: produk uji -> verbs -> render varian -> QC angka -> contact sheet + qc.json + .blend.

  blender -b --factory-startup -P blender_cli.py -- product_shot jalankan [--produk botol,kaleng] [--kualitas uji|final]
        [--warna merah,biru,hijau] [--out <folder>] [--artefak <folder>] [--sumber <file>]
--sumber: model klien (.glb/.obj/.fbx/.stl/.blend) menggantikan produk uji; tambah --satuan mm --depan +X bila perlu,
          dan --logo_u <u> --logo_z <m> (posisi logo) agar QC-04 mengukur logo, bukan hanya deklarasi.
Keluaran kecil (qc.json, contact_sheet.jpg) di --out (bawaan proyek/produk_uji/hasil/<produk>); .blend + render/ di
--artefak (bawaan artefak/product_shot/<produk>, di-ignore, bisa dibuat ulang). Kode keluar 1 jika ada QC gagal.
"""
import json
import os
import time

import bpy

from ...inti import io, lembar
from ...inti.render import KUALITAS, atur_render
from ...inti.scene import STANDAR, root, siapkan_scene
from . import qc_gambar, qc_scene
from .ambang import AMBANG
from .bingkai import kamera_rasio, render_variants
from .cahaya import PRESET_CAHAYA, studio_lighting
from .verbs import RASIO, import_product, material_variant, normalize, turntable


BAWAAN = dict(produk="botol,kaleng", kualitas="uji", warna="merah,biru,hijau", out=io.proyek("produk_uji", "hasil"),
              artefak=io.artefak("product_shot"), sumber="", satuan="m", depan="-Y", atas="+Z", preset="softbox",
              durasi="6", easing="ease_in_out", logo_u="", logo_z="")


def argumen(argv):
    opsi = io.opsi(argv, BAWAAN)
    opsi["out"] = os.path.abspath(opsi["out"])  # C-10: path relatif membuat bpy gagal senyap menulis gambar
    opsi["artefak"] = os.path.abspath(opsi["artefak"])
    if opsi["sumber"]:
        opsi["sumber"] = os.path.abspath(opsi["sumber"])
    return opsi


def label_render(r):
    return f"{r['rasio']} {r['warna']} {r['preset']} F{r['frame']}"


def jalankan_produk(nama, sumber, o):
    t0 = time.time()
    folder = os.path.join(o["out"], nama)
    folder_art = os.path.join(o.get("artefak", o["out"]), nama)
    folder_render = os.path.join(folder_art, "render")
    siapkan_scene()
    perangkat = atur_render(o["kualitas"])
    r0 = import_product(sumber)
    if o["logo_u"] and o["logo_z"]:  # posisi logo di UV label klien (u) dan tinggi tengah logo (m) -> QC-04 kuat
        r0["logo_u"], r0["logo_z"] = float(o["logo_u"]), float(o["logo_z"])
    norm = normalize(satuan=o["satuan"], depan=o["depan"], atas=o["atas"])
    studio_lighting(o["preset"])
    turntable(float(o["durasi"]), o["easing"])
    kamera = [kamera_rasio(r, 0.70) for r in RASIO]
    cek = qc_scene.qc_scene(kamera)
    sel_ok = lambda r: all(r[k]["lulus"] for k in ("qc", "qc_warna", "qc_logam") if k in r)
    baris, semua_render = [], []

    def render(awalan, rasio, frame=None):
        rs = render_variants(folder_render, awalan, rasio, frame)
        for r in rs:
            cam = bpy.data.objects[r["kamera"]]
            r["qc"] = qc_gambar.qc_histogram(r["file"], cam)
            if r["frame"] == bpy.context.scene.frame_start:  # warna dicek di frame hero (label menghadap kamera)
                r["qc_warna"] = qc_gambar.qc_warna(r["file"], cam, r["warna"])
                r["qc_logam"] = qc_gambar.qc_logam(r["file"], cam)  # QC-12 (C-15)
        semua_render.extend(rs)
        return rs

    warna = o["warna"].split(",")
    for w in warna:  # baris 1..n: varian warna x 3 rasio
        material_variant(w)
        rs = render(f"{nama}_{w}_{o['preset']}", list(RASIO))
        baris.append((f"VARIAN {w}", [(r["file"], label_render(r), sel_ok(r)) for r in rs]))
    material_variant(warna[0])
    isi = []
    for p in PRESET_CAHAYA:  # baris: preset cahaya, rasio 1:1
        if p == o["preset"]:
            continue
        studio_lighting(p)
        isi += [(r["file"], label_render(r), sel_ok(r)) for r in render(f"{nama}_{warna[0]}_{p}", ["1:1"])]
    studio_lighting(o["preset"])
    if isi:
        baris.append(("PRESET CAHAYA", isi))
    sc = bpy.context.scene
    isi = []
    for k in (0.25, 0.5, 0.75):  # baris: turntable (sudut menurut easing)
        f = round(sc.frame_start + k * (sc.frame_end - sc.frame_start))
        sc.frame_set(f)
        sudut = round(root().parent.rotation_euler.z * 57.29578)
        for r in render(f"{nama}_{warna[0]}_turntable", ["1:1"], f):
            isi.append((r["file"], f"F{f} {sudut} DERAJAT", sel_ok(r)))
    baris.append(("TURNTABLE " + o["easing"], isi))
    sc.frame_set(sc.frame_start)
    for r in semua_render:
        for k in ("qc", "qc_warna", "qc_logam"):
            if k in r:
                cek.append(r[k] | {"konteks": f"{os.path.basename(r['file'])}: {r[k]['konteks']}"})
    lulus = all(c["lulus"] for c in cek)
    gagal = sorted({c["id"] for c in cek if not c["lulus"]})
    judul = f"{nama} {norm['dimensi_mm'][2]:.1f} MM  QC {'LULUS' if lulus else 'GAGAL ' + ' '.join(gagal)}"
    sheet, ukuran = lembar.buat(baris, os.path.join(folder, "contact_sheet.jpg"), judul)
    laporan = dict(produk=nama, sumber=sumber, standar=STANDAR, blender=bpy.app.version_string,
                   perangkat=perangkat, kualitas=o["kualitas"], sampel=sc.cycles.samples,
                   resolusi={r: [round(x * KUALITAS[o["kualitas"]]["skala"]) for x in v] for r, v in RASIO.items()},
                   normalisasi=norm, turntable=dict(durasi_detik=float(o["durasi"]), easing=o["easing"],
                                                     frame=[sc.frame_start, sc.frame_end], fps=sc.render.fps),
                   lulus=lulus, gagal=gagal, jumlah_cek=len(cek), jumlah_render=len(semua_render),
                   contact_sheet=os.path.relpath(sheet, folder), ukuran_contact_sheet=ukuran,
                   ambang=AMBANG, cek=cek, waktu_detik=round(time.time() - t0, 1))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "qc.json"), "w", encoding="utf-8") as f:
        json.dump(laporan, f, ensure_ascii=False, indent=1)
    os.makedirs(folder_art, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder_art, f"{nama}.blend"), compress=True)
    print(f"HASIL {nama}: QC {'LULUS' if lulus else 'GAGAL ' + str(gagal)} | {len(cek)} cek | "
          f"{len(semua_render)} render | {laporan['waktu_detik']} s | {perangkat}")
    return laporan


def main(argv):
    o = argumen(argv)
    if o["sumber"]:
        daftar = [(os.path.splitext(os.path.basename(o["sumber"]))[0], o["sumber"])]
    else:
        daftar = [(p, "uji:" + p) for p in o["produk"].split(",")]
    hasil = [jalankan_produk(n, s, o) for n, s in daftar]
    return 0 if all(h["lulus"] for h in hasil) else 1
