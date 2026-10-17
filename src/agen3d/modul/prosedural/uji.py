"""Uji generator pohon: QC-001/002/005/006 (ATURAN_QC.md) di 3 pohon contoh, regresi terhadap acuan_pohon.json
(generator deterministik), uji negatif QC-001 (pencegah titik dobel dimatikan = perilaku v1 harus tertangkap).

  blender -b --factory-startup -P blender_cli.py -- prosedural uji [--out <folder>]
QC-004 (ujung ranting <= 0,015 m) masih ⚠ (0,022 m, Tugas 1 diparkir): dilaporkan, tidak menggagalkan uji.
"""
import json
import os

import bpy

from ...inti import io
from ...inti.qc import Pencatat
from . import pohon

ACUAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "acuan_pohon.json")


def kosongkan():
    for o in list(bpy.data.objects):
        if o.type != "CAMERA":
            bpy.data.objects.remove(o)


def main(argv):
    out = os.path.abspath(io.opsi(argv, dict(out=io.artefak("uji", "prosedural")))["out"])
    P = Pencatat()
    with open(ACUAN, encoding="utf-8") as f:
        acuan = json.load(f)
    kosongkan()
    pohon.STAT["duplikat_dicegah"] = 0
    lap = [pohon.bangun_pohon(*t) for t in pohon.POHON]
    for x in lap:
        n = x["pohon"]
        P.uji(f"QC-001 {n}: titik menumpuk = 0", x["QC_titik_menumpuk"] == 0, x["QC_titik_menumpuk"])
        P.uji(f"QC-002 {n}: gumpalan daun <= 8 x median", x["QC_gumpalan_daun_maks_x_median"] <= 8,
              x["QC_gumpalan_daun_maks_x_median"])
        P.uji(f"QC-005 {n}: daun >= 15 x ujung ranting", x["daun"] >= 15 * x["ujung_ranting"],
              f"{x['daun']} vs {15 * x['ujung_ranting']}")
        P.uji(f"QC-006 {n}: daun di bawah tanah = 0", x["QC_daun_di_bawah_tanah"] == 0, x["QC_daun_di_bawah_tanah"])
        print(f"  CATATAN QC-004 {n}: radius ujung {x['radius_cabang_min_max_m'][0]} m (ambang 0,015; status ⚠)")
    P.uji("regresi: laporan 3 pohon = acuan_pohon.json", lap == acuan["laporan"],
          [x["titik_cabang"] for x in lap])
    P.uji("regresi: duplikat dicegah = acuan", pohon.STAT == acuan["stat"], pohon.STAT)
    kosongkan()
    x = pohon.bangun_pohon(*pohon.POHON[0], cegah_duplikat=False)
    P.uji("NEGATIF QC-001: pencegah titik dobel dimatikan (v1) tertangkap", x["QC_titik_menumpuk"] > 0,
          x["QC_titik_menumpuk"])
    print(f"UJI POHON {'LULUS' if P.semua_lulus else 'GAGAL'} {P.lulus}/{len(P.hasil)} ({P.durasi:.0f} s)")
    P.tulis(os.path.join(out, "uji_pohon.json"), blender=bpy.app.version_string, laporan=lap)
    return 0 if P.semua_lulus else 1
