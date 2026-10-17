"""Kurikulum sintetis (lapis 1 sistem belajar): semua produk uji x 3 preset cahaya x palet warna, kualitas uji.

  blender -b --factory-startup -P blender_cli.py -- product_shot kurikulum [--produk a,b] [--out <folder>]
        [--artefak <folder>] [--kualitas uji] [--palet merah,...]
Per produk: jalankan.jalankan_produk (contact sheet + qc.json, dipakai juri) lalu sapuan palet (setiap preset x
setiap warna, rasio 1:1, frame hero): QC-05 + QC-10 per render (+ QC-12 sekali per preset), dirangkum ke palet.jpg.
Menulis <out>/laporan.json dan <out>/LAPORAN.md. Kode keluar 1 jika ada QC gagal atau produk error.
"""
import json
import os
import time
import traceback
from collections import defaultdict

import bpy

from ...inti import io, lembar
from . import jalankan, qc_gambar, spesifikasi
from .ambang import AMBANG
from .bingkai import kamera_rasio, render_variants
from .cahaya import PRESET_CAHAYA, studio_lighting
from .verbs import WARNA, material_variant


def opsi_kurikulum(argv):
    o = io.opsi(argv, dict(produk=",".join(spesifikasi.PRODUK), out=io.proyek("produk_uji", "hasil", "kurikulum"),
                           artefak=io.artefak("product_shot", "kurikulum"), kualitas="uji", palet=",".join(WARNA)))
    o["out"] = os.path.abspath(o["out"])  # C-10
    o["artefak"] = os.path.abspath(o["artefak"])
    return o


def sapu_palet(nama, folder, palet, folder_art=None):
    """Setiap preset cahaya x setiap warna palet: render 1:1 frame hero, QC-05 + QC-10."""
    cam = kamera_rasio("1:1", 0.70)
    cek, baris = [], []
    for p in PRESET_CAHAYA:
        studio_lighting(p)
        isi = []
        for w in palet:
            material_variant(w)
            r = render_variants(os.path.join(folder_art or folder, "render"), f"{nama}_palet_{p}_{w}", ["1:1"])[0]
            hasil = [qc_gambar.qc_histogram(r["file"], cam), qc_gambar.qc_warna(r["file"], cam, r["warna"])]
            if w == palet[0]:  # QC-12 sekali per preset: logam tidak ikut warna varian
                hasil.append(qc_gambar.qc_logam(r["file"], cam))
            for c in hasil:
                c["konteks"] = f"{os.path.basename(r['file'])}: {c['konteks']}"
            cek += [c | dict(preset=p, warna=w) for c in hasil]
            isi.append((r["file"], f"{w} {p}", all(c["lulus"] for c in hasil)))
        baris.append((f"PALET {p}", isi))
    studio_lighting("softbox")
    sheet, _ = lembar.buat(baris, os.path.join(folder, "palet.jpg"), f"{nama} PALET x PRESET")
    return cek, sheet


def rangkum(nama, cek):
    per_qc = defaultdict(lambda: [0, 0])
    for c in cek:
        per_qc[c["id"]][0] += 1
        per_qc[c["id"]][1] += c["lulus"]
    return {k: dict(cek=n, lulus=l, tingkat=round(l / n, 4)) for k, (n, l) in sorted(per_qc.items())}


def tulis_md(lap, path):
    ids = sorted({k for p in lap["produk"].values() for k in p.get("per_qc", {})})
    L = [f"# Laporan kurikulum sintetis ({lap['tanggal']})", "",
         f"Blender {lap['blender']} · perangkat {lap['perangkat']} · kualitas `{lap['kualitas']}` · "
         f"{len(lap['produk'])} produk × {len(PRESET_CAHAYA)} preset × {len(lap['palet'])} warna · "
         f"total {lap['waktu_detik']} s", "",
         f"**Hasil: {'LULUS' if lap['lulus'] else 'GAGAL'}** — {lap['jumlah_cek']} cek, {lap['jumlah_gagal']} gagal.", "",
         "## Tingkat lulus per QC per produk", "",
         "| Produk | " + " | ".join(ids) + " | Render | Waktu (s) | Status |",
         "|---|" + "---|" * (len(ids) + 3)]
    for n, p in lap["produk"].items():
        if "error" in p:
            L.append(f"| {n} | " + " | ".join("-" for _ in ids) + " | - | - | ERROR |")
            continue
        sel = [f"{p['per_qc'][i]['lulus']}/{p['per_qc'][i]['cek']}" if i in p["per_qc"] else "-" for i in ids]
        L.append(f"| {n} | " + " | ".join(sel) + f" | {p['jumlah_render']} | {p['waktu_detik']} | "
                 f"{'LULUS' if p['lulus'] else 'GAGAL'} |")
    L += ["", "## Kegagalan", ""]
    gagal = [(n, g) for n, p in lap["produk"].items() for g in p.get("kegagalan", [])]
    L += [f"- **{n}** {g['id']} `{g['nama']}` = {g['nilai']} (ambang {g['ambang']}): {g['konteks']}" for n, g in gagal] \
        or ["Tidak ada."]
    errs = [(n, p["error"]) for n, p in lap["produk"].items() if "error" in p]
    L += [f"- **{n}** ERROR: `{e.splitlines()[-1]}`" for n, e in errs]
    L += ["", "File per produk: `<produk>/contact_sheet.jpg` (juri), `<produk>/palet.jpg`, `<produk>/qc.json`."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main(argv):
    o = opsi_kurikulum(argv)
    t0 = time.time()
    os.makedirs(o["out"], exist_ok=True)
    palet = o["palet"].split(",")
    lap = dict(tanggal=time.strftime("%Y-%m-%d"), blender=bpy.app.version_string, kualitas=o["kualitas"],
               palet=palet, preset=list(PRESET_CAHAYA), produk={})
    oj = dict(kualitas=o["kualitas"], warna="merah,biru,hijau", out=o["out"], artefak=o["artefak"], satuan="m", depan="-Y", atas="+Z",
              preset="softbox", durasi="6", easing="ease_in_out", logo_u="", logo_z="")
    for nama in o["produk"].split(","):
        t1 = time.time()
        try:
            r = jalankan.jalankan_produk(nama, "uji:" + nama, oj)
            lap["perangkat"] = r["perangkat"]
            folder = os.path.join(o["out"], nama)
            cek_palet, _ = sapu_palet(nama, folder, palet, os.path.join(o["artefak"], nama))
            cek = r["cek"] + cek_palet
            lap["produk"][nama] = dict(
                nama=spesifikasi.SPEC[nama]["nama"], dimensi_mm=r["normalisasi"]["dimensi_mm"],
                lulus=all(c["lulus"] for c in cek), per_qc=rangkum(nama, cek), jumlah_cek=len(cek),
                jumlah_render=r["jumlah_render"] + len(PRESET_CAHAYA) * len(palet),
                kegagalan=[c for c in cek if not c["lulus"]], waktu_detik=round(time.time() - t1, 1),
                palet=[dict(preset=c["preset"], warna=c["warna"], id=c["id"], lulus=c["lulus"],
                            nilai=c["nilai"]["luma_rata"] if c["id"] == "QC-05" else c["nilai"]) for c in cek_palet],
                contact_sheet=f"{nama}/contact_sheet.jpg", palet_png=f"{nama}/palet.jpg")
        except Exception:
            lap["produk"][nama] = dict(lulus=False, error=traceback.format_exc(), waktu_detik=round(time.time() - t1, 1))
            print(lap["produk"][nama]["error"])
        print(f"KURIKULUM {nama}: {'LULUS' if lap['produk'][nama]['lulus'] else 'GAGAL'} "
              f"({lap['produk'][nama]['waktu_detik']} s)")
    ps = lap["produk"].values()
    lap.update(lulus=all(p["lulus"] for p in ps), jumlah_cek=sum(p.get("jumlah_cek", 0) for p in ps),
               jumlah_gagal=sum(len(p.get("kegagalan", [])) + ("error" in p) for p in ps),
               waktu_detik=round(time.time() - t0, 1), ambang=AMBANG)
    lap.setdefault("perangkat", "?")
    with open(os.path.join(o["out"], "laporan.json"), "w", encoding="utf-8") as f:
        json.dump(lap, f, ensure_ascii=False, indent=1)
    tulis_md(lap, os.path.join(o["out"], "LAPORAN.md"))
    print(f"KURIKULUM {'LULUS' if lap['lulus'] else 'GAGAL'}: {lap['jumlah_cek']} cek, {lap['jumlah_gagal']} gagal, "
          f"{lap['waktu_detik']} s")
    return 0 if lap["lulus"] else 1

